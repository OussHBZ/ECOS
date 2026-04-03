import os
import json
import logging
import time
import tempfile

from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, send_from_directory, url_for, redirect
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from httpx import Client

from document_processor import DocumentExtractionAgent
from enhanced_evaluation_agent import EnhancedEvaluationAgent
from simple_pdf_generator import create_simple_consultation_pdf
from models import (
    db, Student, Teacher, AdminAccess, PatientCase, StudentPerformance, CaseImage,
    OSCESession, SessionParticipant, SessionStationAssignment,
    CompetitionSession, CompetitionParticipant, CompetitionStationBank,
    StudentCompetitionSession, StudentStationAssignment
)
from auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.student import student_bp
from blueprints.teacher import teacher_bp

# Model Configuration
LLAMA_MODELS = {
    'primary': 'meta-llama/llama-4-scout-17b-16e-instruct',
    'fallback': 'llama3-8b-8192',
    'config': {
        'temperature': 0.1,  # Low for consistent patient responses
        'max_tokens': 150,   # Concise patient responses
        'timeout': 30        # Increased for larger model
    }
}

def create_groq_client(api_key, http_client):
    """Create Groq client with model fallback capability"""
    
    # Try primary model first
    try:
        client = ChatGroq(
            api_key=api_key,
            model=LLAMA_MODELS['primary'],
            temperature=LLAMA_MODELS['config']['temperature'],
            max_tokens=LLAMA_MODELS['config']['max_tokens'],
            timeout=LLAMA_MODELS['config']['timeout'],
            http_client=http_client
        )
        
        # Test the client with a simple request
        test_messages = [SystemMessage(content="Test")]
        test_response = client.invoke(test_messages)
        
        logger.info(f"Successfully initialized {LLAMA_MODELS['primary']}")
        return client, LLAMA_MODELS['primary']
        
    except Exception as e:
        logger.warning(f"Primary model {LLAMA_MODELS['primary']} failed: {str(e)}")
        
        # Fallback to secondary model
        try:
            client = ChatGroq(
                api_key=api_key,
                model=LLAMA_MODELS['fallback'],
                temperature=0,
                max_tokens=256,
                http_client=http_client
            )
            
            logger.info(f"Fallback to {LLAMA_MODELS['fallback']} successful")
            return client, LLAMA_MODELS['fallback']
            
        except Exception as fallback_error:
            logger.error(f"Fallback model also failed: {str(fallback_error)}")
            raise Exception(f"Both models failed. Primary: {str(e)}, Fallback: {str(fallback_error)}")

def setup_enhanced_logging():
    """Set up enhanced logging with filtering for reduced noise"""
    from logging.handlers import RotatingFileHandler

    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # Custom filter to reduce noise from Chrome DevTools and other unwanted requests
    class RequestFilter(logging.Filter):
        def filter(self, record):
            if hasattr(record, 'getMessage'):
                message = record.getMessage()
                # Filter out noisy requests
                noise_patterns = [
                    '.well-known/appspecific',
                    'favicon.ico',
                    '/undefined/',
                    'Chrome-Lighthouse',
                    'GET /static/',  # Reduce static file logging
                    '200 -'  # Reduce successful request logging
                ]
                if any(pattern in message for pattern in noise_patterns):
                    return False
            return True
    
    # Set up file handler with rotation
    file_handler = RotatingFileHandler('logs/osce_app.log', maxBytes=10240000, backupCount=5)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    file_handler.addFilter(RequestFilter())
    
    # Set up console handler for development - only show warnings and errors
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console
    console_handler.addFilter(RequestFilter())
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )
    
    # Reduce werkzeug logging noise
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.WARNING)
    werkzeug_logger.addFilter(RequestFilter())

setup_enhanced_logging()
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')

    # Session configuration
    # Note: nginx handles /ecos/ prefix via sub_filter and proxy_redirect
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ecos-fmpm-secret-key-2026')
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = True
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_NAME'] = 'ecos_session'
    app.config['SESSION_COOKIE_PATH'] = '/ecos'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['APP_VERSION'] = '20260403d'

    @app.context_processor
    def inject_version():
        return {'app_version': app.config['APP_VERSION']}

    # Configure database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///osce_simulator.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    login_manager.session_protection = 'basic'
    
    # Error handlers - return JSON for AJAX, HTML template otherwise
    def _is_ajax():
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    @app.errorhandler(404)
    def not_found_error(error):
        if _is_ajax():
            return jsonify({'error': 'Not found'}), 404
        return render_template('error.html',
            code=404, color='#ff6b6b', title='Page Not Found',
            message='Page Not Found',
            description="The page you're looking for doesn't exist."
        ), 404

    @app.errorhandler(401)
    def unauthorized_error(error):
        if _is_ajax():
            return jsonify({'error': 'Authentication required', 'redirect': url_for('auth.login'), 'auth_required': True}), 401
        return render_template('error.html',
            code=401, color='#dc3545', title='Unauthorized',
            message='Unauthorized',
            description='You need to be logged in to access this page.'
        ), 401

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logger.error(f"Internal server error: {error}")
        if _is_ajax():
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('error.html',
            code=500, color='#dc3545', title='Internal Server Error',
            message='Internal Server Error',
            description='Something went wrong on our end. Please try refreshing the page.'
        ), 500
    
    @login_manager.user_loader
    def load_user(user_id):
        if user_id and user_id.startswith('student_'):
            try:
                student_id = int(user_id.replace('student_', ''))
                return Student.query.get(student_id)
            except (ValueError, AttributeError):
                return None
        if user_id and user_id.startswith('teacher_'):
            try:
                teacher_id = int(user_id.replace('teacher_', ''))
                return Teacher.query.get(teacher_id)
            except (ValueError, AttributeError):
                return None
        return None
    
    # Add request logging for debugging competition issues
    @app.before_request
    def log_request_info():
        # Skip logging for static files and Chrome DevTools
        if (request.endpoint == 'static' or 
            request.path.startswith('/.well-known/') or
            'favicon.ico' in request.path):
            return
        
        # Log competition-related requests for debugging
        if '/competition/' in request.path:
            logger.info(f"Competition request: {request.method} {request.path}")
            if current_user.is_authenticated:
                logger.info(f"  User: {current_user.id} ({current_user.name})")
    
    @app.after_request
    def log_response_info(response):
        # Log error responses for debugging
        if response.status_code >= 400 and '/competition/' in request.path:
            logger.warning(f"Competition error: {response.status_code} for {request.method} {request.path}")
        return response
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    
    # Create tables if they don't exist
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            
            # Check if competition tables exist, if not create them specifically
            inspector = db.inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            competition_tables = [
                'competition_sessions', 'competition_participants', 
                'competition_station_bank', 'student_competition_sessions', 
                'student_station_assignments'
            ]
            
            missing_tables = [table for table in competition_tables if table not in existing_tables]
            
            if missing_tables:
                logger.info(f"Creating missing competition tables: {missing_tables}")
                # Force create all tables again to ensure competition tables are created
                db.create_all()
                
                # Verify tables were created
                updated_tables = db.inspect(db.engine).get_table_names()
                still_missing = [table for table in competition_tables if table not in updated_tables]
                
                if still_missing:
                    logger.error(f"Failed to create tables: {still_missing}")
                else:
                    logger.info("All competition tables created successfully")
            else:
                logger.info("All competition tables already exist")

            # Add password_hash column to student table if missing (migration)
            try:
                from sqlalchemy import text
                inspector2 = db.inspect(db.engine)
                student_columns = [c['name'] for c in inspector2.get_columns('student')]
                if 'password_hash' not in student_columns:
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE student ADD COLUMN password_hash VARCHAR(255)'))
                        conn.commit()
                    logger.info("Added password_hash column to student table")
            except Exception as migration_err:
                logger.warning(f"Migration note for student.password_hash: {migration_err}")

        except Exception as e:
            logger.error(f"Error creating database tables: {str(e)}")

    # Create upload folder if it doesn't exist
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    
    # Create a persistent HTTP client
    http_client = Client(timeout=10.0, verify=True)

    # Load environment variables
    load_dotenv()
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        logger.error("GROQ_API_KEY not found in environment variables")
        raise ValueError("GROQ_API_KEY not found in environment variables")

    # Initialize ChatGroq client
    try:
        client, active_model = create_groq_client(api_key, http_client)
        app.config['ACTIVE_MODEL'] = active_model
        logger.info(f"ChatGroq client initialized successfully with model: {active_model}")
    except Exception as e:
        logger.error(f"Error initializing ChatGroq client: {str(e)}")
        raise
        
    # Initialize document processor
    document_agent = DocumentExtractionAgent(llm_client=client)
    
    # Initialize evaluation agent 
    evaluation_agent = EnhancedEvaluationAgent(llm_client=client)


    EVALUATION_CONFIG = {
        'min_conversation_length': 3,  # Minimum messages for LLM evaluation
        'max_tokens_per_evaluation': 150,  # Tokens per criterion evaluation
        'evaluation_temperature': 0.1,  # Low temperature for consistent results
        'cache_enabled': True,  # Enable caching for repeated evaluations
        'fallback_to_patterns': True  # Use pattern matching as fallback
    }

    # Store instances in app config for access by other modules
    app.config['DOCUMENT_AGENT'] = document_agent
    app.config['EVALUATION_AGENT'] = evaluation_agent
    app.config['GROQ_CLIENT'] = client
    app.config['EVALUATION_CONFIG'] = EVALUATION_CONFIG

    def load_patient_case(case_number):
        """Load patient case data from the database"""
        try:
            # First try to load from database
            case_data_db = PatientCase.query.filter_by(case_number=str(case_number)).first()

            if case_data_db:
                # Convert the SQLAlchemy object to a dictionary-like structure
                data = {
                    "case_number": case_data_db.case_number,
                    "specialty": case_data_db.specialty,
                    "patient_info": case_data_db.patient_info,
                    "symptoms": case_data_db.symptoms,
                    "evaluation_checklist": case_data_db.evaluation_checklist,
                    "diagnosis": case_data_db.diagnosis,
                    "differential_diagnosis": case_data_db.differential_diagnosis,
                    "directives": case_data_db.directives,
                    "consultation_time": case_data_db.consultation_time,
                    "additional_notes": case_data_db.additional_notes,
                    "lab_results": case_data_db.lab_results,
                    "custom_sections": case_data_db.custom_sections,
                    "images": []
                }
                
                # Add images from database relationship
                if hasattr(case_data_db, 'images') and case_data_db.images:
                    for img in case_data_db.images:
                        data["images"].append({
                            "path": img.path,
                            "description": img.description,
                            "filename": img.filename
                        })
                
                logger.info(f"Successfully loaded patient case {case_number} from database")
                return data
                
            else:
                raise FileNotFoundError(f"Patient case {case_number} not found in database.")
                
        except Exception as e:
            logger.error(f"Error loading patient case {case_number} from database: {str(e)}")
            raise

    def load_system_template():
        """Load system prompt template"""
        try:
            template_path = "response_template.json"
            logger.debug(f"Loading system template from: {template_path}")
            
            if not os.path.exists(template_path):
                raise FileNotFoundError("Response template file not found")
                
            with open(template_path, "r", encoding="utf-8") as f:
                template = json.load(f)
                logger.info("Successfully loaded system template")
                return template
        except Exception as e:
            logger.error(f"Error loading system template: {str(e)}")
            raise

    def initialize_conversation(case_number):
        """Initialize a new conversation with enhanced patient simulation prompt"""
        try:
            patient_data = load_patient_case(case_number)
            system_template = load_system_template()
            
            # Create enhanced system message for realistic patient simulation
            enhanced_system_message = f"{system_template['content']}\n\n"

            # Build patient identity card
            patient_info = patient_data.get('patient_info', {})
            enhanced_system_message += "=== VOTRE IDENTITÉ (informations internes — ne les révélez que si on vous les demande) ===\n"

            if patient_info:
                name = patient_info.get('name', 'Non précisé')
                age = patient_info.get('age', '')
                gender = patient_info.get('gender', '')
                occupation = patient_info.get('occupation', '')
                medical_history = patient_info.get('medical_history', [])

                enhanced_system_message += f"- Vous vous appelez : {name}\n"
                if age:
                    enhanced_system_message += f"- Vous avez {age} ans\n"
                if gender:
                    enhanced_system_message += f"- Sexe : {gender}\n"
                if occupation:
                    enhanced_system_message += f"- Vous travaillez comme : {occupation}\n"
                if medical_history:
                    history_str = ', '.join(medical_history) if isinstance(medical_history, list) else medical_history
                    enhanced_system_message += f"- Vos antécédents médicaux (à mentionner SEULEMENT si l'étudiant vous interroge dessus) : {history_str}\n"

            # Add symptoms with OSCE-appropriate disclosure rules
            symptoms = patient_data.get('symptoms', [])
            if symptoms:
                enhanced_system_message += (
                    "\n=== VOS SYMPTÔMES (ce que vous ressentez) ===\n"
                    "Révélez chaque symptôme UNIQUEMENT quand l'étudiant pose la question correspondante.\n"
                    "Le motif de consultation (premier symptôme) peut être mentionné si on vous demande pourquoi vous consultez.\n"
                )
                for i, symptom in enumerate(symptoms):
                    if i == 0:
                        enhanced_system_message += f"- MOTIF PRINCIPAL : {symptom}\n"
                    else:
                        enhanced_system_message += f"- {symptom}\n"

            # Add diagnosis — strictly hidden from student
            diagnosis = patient_data.get('diagnosis', '')
            if diagnosis:
                enhanced_system_message += (
                    f"\n=== DIAGNOSTIC RÉEL (STRICTEMENT CONFIDENTIEL) ===\n"
                    f"{diagnosis}\n"
                    f"⚠ Ne mentionnez JAMAIS ce diagnostic. Vous êtes un patient, vous ne connaissez pas votre diagnostic.\n"
                )
            
            # Create conversation with enhanced system message
            conversation = [SystemMessage(content=enhanced_system_message)]
            
            logger.info(f"Initialized enhanced conversation for case {case_number}")
            return conversation
                
        except Exception as e:
            logger.error(f"Error initializing enhanced conversation: {str(e)}")
            raise
            
    def get_case_metadata():
        cases_metadata = []
        try:
            cases = PatientCase.query.all()
            for case in cases:
                cases_metadata.append({
                    "case_number": case.case_number,
                    "specialty": case.specialty,
                    "created_at": case.created_at,
                    "updated_at": case.updated_at
                })
        except Exception as e:
            logger.error(f"Error fetching case metadata: {e}")
        return cases_metadata
            
    def get_unique_specialties():
        """Get list of unique specialties from all cases in the database"""
        specialties = set()
        try:
            # Query distinct specialties directly from the database
            distinct_specialties = db.session.query(PatientCase.specialty).distinct().all()
            for spec_tuple in distinct_specialties:
                if spec_tuple[0]: # Ensure specialty is not None or empty
                    specialties.add(spec_tuple[0])
            return sorted(list(specialties))
        except Exception as e:
            logger.error(f"Error getting unique specialties from database: {str(e)}")
            return []
    
    def evaluate_conversation(conversation, case_number):
        """Evaluate the conversation using the EvaluationAgent with optimizations"""
        try:
            # Load case data to get evaluation checklist
            case_data = load_patient_case(case_number)
            
            # Log evaluation start time
            start_time = time.time()
            
            # Ensure conversation is in the right format
            formatted_conversation = []
            for msg in conversation:
                if isinstance(msg, dict):
                    formatted_conversation.append(msg)
                elif isinstance(msg, str):
                    # If it's a string, assume it's a system message
                    formatted_conversation.append({'role': 'system', 'content': msg})
                else:
                    # Try to convert to dict
                    try:
                        formatted_conversation.append({'role': 'system', 'content': str(msg)})
                    except Exception:
                        logger.warning(f"Could not format message: {type(msg)}")
                        continue
            
            # Check if we have an empty conversation (just started)
            human_messages = [msg for msg in formatted_conversation if isinstance(msg, dict) and msg.get('role') == 'human']
            
            if not human_messages:
                # Return a default minimal evaluation for empty conversations
                logger.info("Empty conversation detected, returning minimal evaluation")
                checklist = case_data.get('evaluation_checklist', [])
                return {
                    'checklist': [
                        {**item, 'completed': False, 'justification': "La consultation n'a pas commencé."} 
                        for item in checklist
                    ],
                    'feedback': "La consultation n'a pas été réalisée ou vient juste de commencer.",
                    'points_total': sum(item.get('points', 1) for item in checklist),
                    'points_earned': 0,
                    'percentage': 0,
                    'recommendations': ["Commencez la consultation en posant des questions au patient."]
                }
            
            # For short conversations (fewer than 3 messages), use a simpler evaluation
            if len(human_messages) < 3:
                logger.info("Brief conversation detected, using simplified evaluation")
                checklist = case_data.get('evaluation_checklist', [])
                
                # Simple pattern matching for basic evaluation
                completed_items = []
                for item in checklist:
                    item_copy = item.copy()
                    item_copy['completed'] = False
                    item_copy['justification'] = "Conversation trop courte pour évaluer cet élément."
                    completed_items.append(item_copy)
                
                return {
                    'checklist': completed_items,
                    'feedback': "La consultation est trop courte pour une évaluation complète.",
                    'points_total': sum(item.get('points', 1) for item in checklist),
                    'points_earned': 0,
                    'percentage': 0,
                    'recommendations': [
                        "Posez plus de questions sur les symptômes du patient.",
                        "Explorez les antécédents médicaux.",
                        "Effectuez un examen clinique approprié."
                    ]
                }
            
            # Full evaluation for normal conversations
            try:
                evaluation_results = evaluation_agent.evaluate_conversation(formatted_conversation, case_data)
            except Exception as e:
                logger.error(f"Error in evaluation agent: {str(e)}")
                # Return a basic evaluation on error
                checklist = case_data.get('evaluation_checklist', [])
                return {
                    'checklist': [
                        {**item, 'completed': False, 'justification': "Erreur lors de l'évaluation."} 
                        for item in checklist
                    ],
                    'feedback': f"Erreur lors de l'évaluation automatique: {str(e)}",
                    'points_total': sum(item.get('points', 1) for item in checklist),
                    'points_earned': 0,
                    'percentage': 0,
                    'recommendations': ["Veuillez réessayer ou contacter le support."]
                }
            
            # Log completion time
            elapsed = time.time() - start_time
            logger.info(f"Evaluation completed in {elapsed:.2f} seconds")
            
            # Ensure the evaluation results have all required fields
            if 'recommendations' not in evaluation_results:
                evaluation_results['recommendations'] = []
            
            return evaluation_results
                    
        except Exception as e:
            logger.error(f"Error evaluating conversation: {str(e)}", exc_info=True)
            return {
                'checklist': [], 
                'feedback': f"Erreur lors de l'évaluation: {str(e)}",
                'points_total': 0,
                'points_earned': 0,
                'percentage': 0,
                'recommendations': []
            }

    # Store functions in app config
    app.config['LOAD_PATIENT_CASE'] = load_patient_case
    app.config['GET_CASE_METADATA'] = get_case_metadata
    app.config['GET_UNIQUE_SPECIALTIES'] = get_unique_specialties
    app.config['INITIALIZE_CONVERSATION'] = initialize_conversation
    app.config['EVALUATE_CONVERSATION'] = evaluate_conversation

    # Routes
    @app.route('/')
    def index():
        """Render the main landing page with role selection"""
        return render_template('home.html')

    @app.route('/initialize_chat', methods=['POST'])
    def initialize_chat():
        """Initialize chat session"""
        try:
            data = request.get_json()
            case_number = data.get('case_number')
            
            if not case_number:
                return jsonify({'error': 'Case number is required'}), 400
            
            # Load case data
            case_data = load_patient_case(case_number)
            
            # Initialize conversation
            conversation = initialize_conversation(case_number)
            
            # IMPORTANT: Store conversation as a list of dictionaries
            # Convert LangChain messages to dict format for session storage
            conversation_dicts = []
            for msg in conversation:
                if hasattr(msg, 'content') and hasattr(msg, 'type'):
                    # LangChain message object
                    if msg.type == 'system':
                        conversation_dicts.append({'role': 'system', 'content': msg.content})
                    elif msg.type == 'human':
                        conversation_dicts.append({'role': 'human', 'content': msg.content})
                    elif msg.type == 'ai':
                        conversation_dicts.append({'role': 'assistant', 'content': msg.content})
                elif isinstance(msg, dict):
                    # Already in dict format
                    conversation_dicts.append(msg)
                else:
                    # String or other format - convert to system message
                    conversation_dicts.append({'role': 'system', 'content': str(msg)})
            
            # Store in session as list of dictionaries
            session['current_conversation'] = conversation_dicts
            session['current_case'] = case_number
            
            logger.info(f"Initialized conversation with {len(conversation_dicts)} messages")
            logger.info(f"Sample conversation format: {conversation_dicts[0] if conversation_dicts else 'Empty'}")
            
            return jsonify({
                'success': True,
                'case_data': case_data,
                'directives': case_data.get('directives', ''),
                'consultation_time': case_data.get('consultation_time', 10),
                'images': case_data.get('images', [])
            })
            
        except Exception as e:
            logger.error(f"Error initializing chat: {str(e)}")
            return jsonify({'error': str(e)}), 500


    @app.route('/chat', methods=['POST'])
    def chat():
        """Handle chat messages with enhanced patient simulation"""
        try:
            data = request.get_json()
            message = data.get('message')
            
            if not message:
                return jsonify({'error': 'Message is required'}), 400
            
            # Get current conversation from session
            conversation = session.get('current_conversation', [])
            case_number = session.get('current_case')
            
            if not case_number:
                return jsonify({'error': 'No active case session'}), 400
            
            logger.info(f"Processing message for case {case_number}: {message[:50]}...")
            
            # Add user message to conversation
            user_message = {'role': 'human', 'content': message}
            conversation.append(user_message)
            
            # Get AI response using the Groq client
            try:
                # Convert conversation to LangChain format for AI processing
                langchain_messages = []
                for msg in conversation:
                    if isinstance(msg, dict):
                        if msg['role'] == 'system':
                            langchain_messages.append(SystemMessage(content=msg['content']))
                        elif msg['role'] == 'human':
                            langchain_messages.append(HumanMessage(content=msg['content']))
                        elif msg['role'] == 'assistant':
                            langchain_messages.append(AIMessage(content=msg['content']))
                    else:
                        logger.warning(f"Unexpected conversation format: {type(msg)} - {msg}")
                        langchain_messages.append(SystemMessage(content=str(msg)))
                
                # Get response from Groq with enhanced parameters
                response = client.invoke(langchain_messages)
                ai_reply = response.content
                
                # Validate and enhance the response
                ai_reply = validate_patient_response(ai_reply, message)
                
                # Add AI response to conversation
                ai_message = {'role': 'assistant', 'content': ai_reply}
                conversation.append(ai_message)
                
                # Update session
                session['current_conversation'] = conversation
                
                logger.info(f"Generated patient response: {ai_reply[:50]}...")
                
                return jsonify({
                    'success': True,
                    'reply': ai_reply
                })
                
            except Exception as e:
                logger.error(f"Error getting AI response: {str(e)}")
                return jsonify({'error': 'Error getting AI response'}), 500
            
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
            return jsonify({'error': str(e)}), 500

    def validate_patient_response(ai_reply, user_message):
        """Validate and modify the AI response to ensure realistic patient simulation"""

        # Phrases that break patient immersion
        immersion_breaking = [
            "en tant qu'ia", "je suis une intelligence artificielle",
            "comme assistant", "en tant qu'assistant", "en tant que modèle",
            "je ne suis pas un vrai patient", "je suis un simulateur",
            "je suis programmé", "mon rôle est de", "dans le cadre de cet exercice",
            "en tant que patient simulé"
        ]

        # Phrases where AI gives medical advice (patient should never do this)
        medical_advice = [
            "consultez un médecin", "je vous recommande de", "vous devriez",
            "il serait préférable de", "je vous conseille", "il faut que vous",
            "le traitement serait", "le diagnostic est", "vous avez probablement"
        ]

        reply_lower = ai_reply.lower()

        for phrase in immersion_breaking:
            if phrase in reply_lower:
                logger.warning(f"AI broke immersion with: {phrase}")
                return "Pardon docteur, je n'ai pas bien compris votre question."

        for phrase in medical_advice:
            if phrase in reply_lower:
                logger.warning(f"AI gave medical advice: {phrase}")
                return "Je ne sais pas trop, docteur. C'est vous le spécialiste."

        # Enforce brevity — max 3 sentences for patient realism
        sentences = [s.strip() for s in ai_reply.split('.') if s.strip()]
        if len(sentences) > 3:
            ai_reply = '. '.join(sentences[:3]) + '.'
            logger.info("Truncated long response for patient simulation")

        return ai_reply

    @app.route('/end_chat', methods=['POST'])
    def end_chat():
        """End chat session and evaluate"""
        try:
            conversation = session.get('current_conversation', [])
            case_number = session.get('current_case')
            
            if not case_number:
                logger.error("No case number found in session")
                return jsonify({'error': 'No active case session'}), 400
            
            if not conversation:
                logger.warning("Empty conversation found")
                conversation = [{'role': 'system', 'content': 'No conversation recorded'}]
            
            evaluation_results = evaluate_conversation(conversation, case_number)

            pdf_url = None
            performance_id = None

            # Save performance first (if authenticated) so we can build a stable PDF URL
            if current_user.is_authenticated:
                try:
                    performance = StudentPerformance(
                        student_id=current_user.id,
                        case_number=case_number,
                        conversation_transcript=conversation,
                        evaluation_results=evaluation_results,
                        percentage_score=evaluation_results.get('percentage', 0),
                        points_earned=evaluation_results.get('points_earned', 0),
                        points_total=evaluation_results.get('points_total', 0),
                        recommendations=evaluation_results.get('recommendations', [])
                    )
                    db.session.add(performance)
                    db.session.commit()
                    performance_id = performance.id
                    pdf_url = f'/student/download_report/{performance_id}'
                    logger.info(f"Saved performance {performance_id} for student {current_user.id}")
                except Exception as e:
                    logger.error(f"Error saving performance: {str(e)}")

            # Clear session
            session.pop('current_conversation', None)
            session.pop('current_case', None)

            return jsonify({
                'success': True,
                'evaluation': evaluation_results,
                'recommendations': evaluation_results.get('recommendations', []),
                'pdf_url': pdf_url,
                'pdf_available': pdf_url is not None
            })
            
        except Exception as e:
            logger.error(f"Error in end_chat: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500



    @app.route('/download_pdf/<filename>')
    def download_pdf(filename):
        """Download generated PDF"""
        try:
            # Security: prevent path traversal
            if '..' in filename or '/' in filename or '\\' in filename:
                return jsonify({'error': 'Invalid filename'}), 400

            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, filename)

            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                return jsonify({'error': 'PDF file not found'}), 404

            return send_from_directory(
                temp_dir,
                filename,
                as_attachment=True,
                download_name=f'consultation_evaluation_{filename}',
                mimetype='application/pdf'
            )

        except Exception as e:
            logger.error(f"Error downloading PDF: {e}", exc_info=True)
            return jsonify({'error': 'Error downloading PDF'}), 500
        
    @app.route('/check_pdf_status')
    def check_pdf_status():
        """Check if PDF is ready for download"""
        try:
            pdf_filename = session.get('last_pdf')
            if not pdf_filename:
                return jsonify({'pdf_ready': False})

            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, pdf_filename)
            
            if os.path.exists(file_path):
                return jsonify({
                    'pdf_ready': True,
                    'pdf_url': f'/download_pdf/{pdf_filename}'
                })
            else:
                return jsonify({'pdf_ready': False})
                
        except Exception as e:
            logger.error(f"Error checking PDF status: {str(e)}")
            return jsonify({'pdf_ready': False})


    @app.route('/get_case/<case_number>')
    def get_case(case_number):
        """Get case data"""
        try:
            case_data = load_patient_case(case_number)
            return jsonify(case_data)
        except Exception as e:
            logger.error(f"Error getting case: {str(e)}")
            return jsonify({'error': str(e)}), 404

    @app.route('/check_case_number/<case_number>')
    def check_case_number(case_number):
        """Check if case number exists"""
        try:
            existing_case = PatientCase.query.filter_by(case_number=case_number).first()
            if existing_case:
                return jsonify({
                    'exists': True,
                    'message': f'Le cas {case_number} existe déjà'
                })
            else:
                return jsonify({
                    'exists': False,
                    'message': f'Le cas {case_number} est disponible'
                })
        except Exception as e:
            logger.error(f"Error checking case number: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/check_session')
    def check_session():
        """Check if user is authenticated and return session info"""
        if current_user.is_authenticated:
            return jsonify({
                'authenticated': True,
                'user_type': session.get('user_type'),
                'user_id': current_user.get_id() if hasattr(current_user, 'get_id') else None,
                'username': current_user.name if hasattr(current_user, 'name') else None
            })
        elif session.get('user_type') in ['teacher', 'admin']:
            # Handle non-student users who might not use Flask-Login
            return jsonify({
                'authenticated': True,
                'user_type': session.get('user_type'),
                'user_id': None,
                'username': session.get('username') or session.get('user_type')
            })
        else:
            return jsonify({
                'authenticated': False,
                'user_type': None,
                'user_id': None,
                'username': None
            })
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)