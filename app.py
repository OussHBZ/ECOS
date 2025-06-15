from flask import Flask, render_template, request, jsonify, session, send_from_directory, url_for, redirect
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import os, re
import json
import logging
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import tempfile
from datetime import datetime
import shutil
from werkzeug.utils import secure_filename
from document_processor import DocumentExtractionAgent
from evaluation_agent import EvaluationAgent
from simple_pdf_generator import create_simple_consultation_pdf
from flask_login import LoginManager, login_required, current_user
from models import db, Student, AdminAccess, OSCESession, SessionParticipant, SessionStationAssignment
from auth import auth_bp
from models import (
    db, Student, TeacherAccess, AdminAccess, PatientCase, StudentPerformance, CaseImage,
    CompetitionSession, CompetitionParticipant, CompetitionStationBank, 
    StudentCompetitionSession, StudentStationAssignment
)
from datetime import datetime, timedelta

# Import blueprints
from blueprints.admin import admin_bp
from blueprints.student import student_bp
from blueprints.teacher import teacher_bp

import time
import concurrent.futures

# Import reporting modules
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Frame, BaseDocTemplate, PageTemplate

# Import HTTP client
from httpx import Client

def setup_enhanced_logging():
    """Set up enhanced logging with filtering for reduced noise"""
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    
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

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
setup_enhanced_logging()
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__, 
                static_folder='static',
                template_folder='templates')
    
    # Enhanced session configuration for better AJAX support
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(32)
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_NAME'] = 'ecos_session'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
    
    # Add CORS headers for AJAX requests (if needed)
    app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
    
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
    
    # Enhanced error handlers for AJAX and competition routes
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors with a simple response instead of template"""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Page Not Found - ECOS</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
                .error-container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .error-code { font-size: 72px; color: #ff6b6b; margin-bottom: 20px; }
                .error-message { font-size: 24px; margin-bottom: 20px; }
                .back-link { display: inline-block; background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="error-container">
                <div class="error-code">404</div>
                <div class="error-message">Page Not Found</div>
                <p>The page you're looking for doesn't exist.</p>
                <a href="/" class="back-link">Go to Homepage</a>
            </div>
        </body>
        </html>
        ''', 404
    
    @app.errorhandler(401)
    def unauthorized_error(error):
        """Handle 401 Unauthorized errors"""
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'error': 'Authentication required',
                'redirect': url_for('auth.login'),
                'auth_required': True
            }), 401
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Unauthorized - ECOS</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f8f9fa; }
                .error-container { max-width: 600px; margin: 0 auto; padding: 30px; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                .error-code { font-size: 72px; color: #dc3545; margin-bottom: 20px; font-weight: bold; }
                .error-message { font-size: 24px; margin-bottom: 20px; color: #333; }
                .back-link { display: inline-block; background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px; }
            </style>
        </head>
        <body>
            <div class="error-container">
                <div class="error-code">401</div>
                <div class="error-message">Unauthorized</div>
                <p>You need to be logged in to access this page.</p>
                <a href="/login" class="back-link">Login</a>
                <a href="/" class="back-link">Go to Homepage</a>
            </div>
        </body>
        </html>
        ''', 401
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors with proper rollback and response"""
        db.session.rollback()
        logger.error(f"Internal server error: {str(error)}")
        
        # For AJAX requests, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'error': 'Internal server error',
                'message': 'An unexpected error occurred'
            }), 500
        
        # For regular requests, return HTML without template dependency
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Internal Server Error - ECOS</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    text-align: center; 
                    margin-top: 50px; 
                    background-color: #f8f9fa; 
                }
                .error-container { 
                    max-width: 600px; 
                    margin: 0 auto; 
                    padding: 30px; 
                    background: white; 
                    border-radius: 10px; 
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
                }
                .error-code { 
                    font-size: 72px; 
                    color: #dc3545; 
                    margin-bottom: 20px; 
                    font-weight: bold; 
                }
                .error-message { 
                    font-size: 24px; 
                    margin-bottom: 20px; 
                    color: #333; 
                }
                .error-description { 
                    color: #666; 
                    margin-bottom: 30px; 
                    line-height: 1.6; 
                }
                .back-link { 
                    display: inline-block; 
                    background: #007bff; 
                    color: white; 
                    padding: 12px 24px; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin: 10px; 
                    transition: background-color 0.3s; 
                }
                .back-link:hover { 
                    background: #0056b3; 
                }
                .refresh-link { 
                    background: #28a745; 
                }
                .refresh-link:hover { 
                    background: #1e7e34; 
                }
            </style>
        </head>
        <body>
            <div class="error-container">
                <div class="error-code">500</div>
                <div class="error-message">Internal Server Error</div>
                <div class="error-description">
                    Something went wrong on our end. We're working to fix this issue.
                    <br><br>
                    If this problem persists, please try refreshing the page or contact support.
                </div>
                <a href="/" class="back-link">Go to Homepage</a>
                <a href="javascript:location.reload()" class="back-link refresh-link">Refresh Page</a>
            </div>
        </body>
        </html>
        ''', 500
    
    @login_manager.user_loader
    def load_user(user_id):
        if user_id and user_id.startswith('student_'):
            try:
                student_id = int(user_id.replace('student_', ''))
                return Student.query.get(student_id)
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
        client = ChatGroq(
            api_key=api_key,
            model="llama3-8b-8192",
            temperature=0,  # Keeping temperature at 0 for more consistent responses
            max_tokens=256,  # Limit maximum token output for faster responses            
            http_client=http_client
        )
        logger.info("ChatGroq client initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing ChatGroq client: {str(e)}")
        raise
        
    # Initialize document processor
    document_agent = DocumentExtractionAgent(llm_client=client)
    
    # Initialize evaluation agent 
    evaluation_agent = EvaluationAgent(llm_client=client)

    # Store instances in app config for access by other modules
    app.config['DOCUMENT_AGENT'] = document_agent
    app.config['EVALUATION_AGENT'] = evaluation_agent
    app.config['GROQ_CLIENT'] = client
        

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
        """Initialize a new conversation with system prompt and patient data"""
        try:
            patient_data = load_patient_case(case_number)
            system_template = load_system_template()
            
            # Format initial system message
            initial_system_message = (
                f"{system_template['content']}\n\n"
                f"Données du patient:\n"
            )
            
            # Add patient info to message
            for key, value in patient_data.items():
                if key != 'images':  # Skip images array in the system message
                    initial_system_message += f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
            
            # Create conversation with system message only
            conversation = [SystemMessage(content=initial_system_message)]
            
            logger.info(f"Initialized conversation for case {case_number}")
            return conversation
                
        except Exception as e:
            logger.error(f"Error initializing conversation: {str(e)}")
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
                    except:
                        logger.warning(f"Could not format message: {msg}")
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
        """Handle chat messages"""
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
            
            logger.info(f"Current conversation format: {type(conversation)} with {len(conversation)} messages")
            if conversation:
                logger.info(f"Sample message format: {type(conversation[0])} - {conversation[0] if conversation else 'Empty'}")
            
            # Add user message to conversation (ensure dict format)
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
                        # Handle string format (shouldn't happen with this fix)
                        logger.warning(f"Unexpected conversation format: {type(msg)} - {msg}")
                        langchain_messages.append(SystemMessage(content=str(msg)))
                
                # Get response from Groq
                response = client.invoke(langchain_messages)
                ai_reply = response.content
                
                # Add AI response to conversation (ensure dict format)
                ai_message = {'role': 'assistant', 'content': ai_reply}
                conversation.append(ai_message)
                
                # Update session with dict format
                session['current_conversation'] = conversation
                
                logger.info(f"Updated conversation with {len(conversation)} messages")
                
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

    @app.route('/end_chat', methods=['POST'])
    def end_chat():
        """End chat session and evaluate"""
        try:
            conversation = session.get('current_conversation', [])
            case_number = session.get('current_case')
            
            logger.info(f"=== ENDING CHAT DEBUG INFO ===")
            logger.info(f"Case number: {case_number}")
            logger.info(f"Conversation length: {len(conversation) if conversation else 0}")
            logger.info(f"Session keys: {list(session.keys())}")
            
            if not case_number:
                logger.error("No case number found in session")
                return jsonify({'error': 'No active case session'}), 400
            
            if not conversation:
                logger.warning("Empty conversation found")
                conversation = [{'role': 'system', 'content': 'No conversation recorded'}]
            
            # Evaluate conversation
            logger.info("Starting conversation evaluation...")
            evaluation_results = evaluate_conversation(conversation, case_number)
            logger.info(f"Evaluation completed: {evaluation_results.get('percentage', 0)}%")
            
            # Generate PDF report with detailed logging
            pdf_filename = None
            pdf_url = None
            
            try:
                logger.info("=== STARTING PDF GENERATION ===")
                
                # Check if simple_pdf_generator function exists
                if 'create_simple_consultation_pdf' not in globals():
                    logger.error("create_simple_consultation_pdf function not found!")
                    raise ImportError("PDF generation function not available")
                
                # Check temp directory
                import tempfile
                temp_dir = tempfile.gettempdir()
                logger.info(f"Temp directory: {temp_dir}")
                logger.info(f"Temp directory exists: {os.path.exists(temp_dir)}")
                logger.info(f"Temp directory writable: {os.access(temp_dir, os.W_OK)}")
                
                # Generate PDF
                logger.info("Calling create_simple_consultation_pdf...")
                pdf_filename = create_simple_consultation_pdf(
                    conversation,
                    case_number,
                    evaluation_results,
                    evaluation_results.get('recommendations', [])
                )
                
                logger.info(f"PDF generation returned: {pdf_filename}")
                
                if pdf_filename:
                    # Check if file actually exists
                    pdf_path = os.path.join(temp_dir, pdf_filename)
                    logger.info(f"Checking PDF file at: {pdf_path}")
                    
                    if os.path.exists(pdf_path):
                        file_size = os.path.getsize(pdf_path)
                        logger.info(f"PDF file exists, size: {file_size} bytes")
                        
                        if file_size > 0:
                            pdf_url = f'/download_pdf/{pdf_filename}'
                            session['last_pdf'] = pdf_filename
                            logger.info(f"PDF URL created: {pdf_url}")
                        else:
                            logger.error("PDF file is empty (0 bytes)")
                            pdf_filename = None
                    else:
                        logger.error(f"PDF file does not exist at expected path: {pdf_path}")
                        pdf_filename = None
                else:
                    logger.error("PDF generation returned None")
                    
            except Exception as e:
                logger.error(f"=== PDF GENERATION ERROR ===")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                import traceback
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                pdf_filename = None
                pdf_url = None
            
            # Save performance if user is logged in
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
                    logger.info(f"Saved performance for student {current_user.id}")
                except Exception as e:
                    logger.error(f"Error saving performance: {str(e)}")
            
            # Clear session
            session.pop('current_conversation', None)
            session.pop('current_case', None)
            
            response_data = {
                'success': True,
                'evaluation': evaluation_results,
                'recommendations': evaluation_results.get('recommendations', []),
                'pdf_url': pdf_url,
                'pdf_available': pdf_filename is not None,
                'debug_info': {  # Add debug info to response
                    'pdf_filename': pdf_filename,
                    'conversation_length': len(conversation),
                    'case_number': case_number
                }
            }
            
            logger.info(f"=== FINAL RESPONSE ===")
            logger.info(f"PDF URL: {pdf_url}")
            logger.info(f"PDF Available: {pdf_filename is not None}")
            logger.info(f"Response keys: {list(response_data.keys())}")
            
            return jsonify(response_data)
            
        except Exception as e:
            logger.error(f"=== FATAL ERROR IN END_CHAT ===")
            logger.error(f"Error: {str(e)}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return jsonify({'error': str(e)}), 500



    @app.route('/download_pdf/<filename>')
    def download_pdf(filename):
        """Download generated PDF with comprehensive error handling"""
        try:
            import tempfile
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, filename)
            
            logger.info(f"=== PDF DOWNLOAD DEBUG ===")
            logger.info(f"Requested filename: {filename}")
            logger.info(f"Full file path: {file_path}")
            logger.info(f"File exists: {os.path.exists(file_path)}")
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                logger.info(f"File size: {file_size} bytes")
                
                if file_size == 0:
                    logger.error("PDF file is empty")
                    return jsonify({'error': 'PDF file is empty'}), 404
            else:
                logger.error(f"PDF file not found at: {file_path}")
                
                # List all files in temp directory for debugging
                try:
                    temp_files = os.listdir(temp_dir)
                    pdf_files = [f for f in temp_files if f.endswith('.pdf')]
                    logger.info(f"Available PDF files in temp dir: {pdf_files}")
                except Exception as list_error:
                    logger.error(f"Could not list temp directory: {list_error}")
                
                return jsonify({'error': 'PDF file not found'}), 404
            
            return send_from_directory(
                temp_dir, 
                filename, 
                as_attachment=True,
                download_name=f'consultation_evaluation_{filename}',
                mimetype='application/pdf'
            )
            
        except Exception as e:
            logger.error(f"Error in download_pdf: {str(e)}")
            import traceback
            logger.error(f"Download traceback:\n{traceback.format_exc()}")
            return jsonify({'error': f'Error downloading PDF: {str(e)}'}), 500
        
    @app.route('/check_pdf_status')
    def check_pdf_status():
        """Check if PDF is ready for download"""
        try:
            pdf_filename = session.get('last_pdf')
            if not pdf_filename:
                return jsonify({'pdf_ready': False})
            
            import tempfile
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
        from flask import jsonify, session
        from flask_login import current_user
        
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