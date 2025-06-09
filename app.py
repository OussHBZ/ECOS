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

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__, 
                static_folder='static',
                template_folder='templates')
    app.secret_key = os.urandom(24)  # For session management
    
    # Configure database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///osce_simulator.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    db.init_app(app)
    
    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        if user_id.startswith('student_'):
            student_id = int(user_id.replace('student_', ''))
            return Student.query.get(student_id)
        return None
    
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
            
            # Check if we have an empty conversation (just started)
            if not any(msg['role'] == 'human' for msg in conversation):
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
                    'percentage': 0
                }
                
            # For short conversations (fewer than 3 messages), use a simpler evaluation
            if sum(1 for msg in conversation if msg['role'] == 'human') < 3:
                logger.info("Brief conversation detected, using pattern-based evaluation")
                evaluation_agent.state = {
                    "conversation": conversation,
                    "case_data": case_data,
                    "checklist": case_data.get('evaluation_checklist', []),
                    "results": {},
                    "recommendations": [],
                    "evaluation_complete": False
                }
                evaluation_agent._prepare_transcript()
                evaluation_agent._evaluate_with_patterns()
                evaluation_agent._generate_basic_recommendations()
                evaluation_results = evaluation_agent.state["results"]
            else:
                # Full evaluation for normal conversations
                evaluation_results = evaluation_agent.evaluate_conversation(conversation, case_data)
            
            # Log completion time
            elapsed = time.time() - start_time
            logger.info(f"Evaluation completed in {elapsed:.2f} seconds")
            
            # Return the evaluation results
            return evaluation_results
                    
        except Exception as e:
            logger.error(f"Error evaluating conversation: {str(e)}")
            return {'checklist': [], 'feedback': f"Erreur lors de l'évaluation: {str(e)}"}

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

    # Add these new routes to handle missing functionality
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
            
            # Store conversation in session
            session['current_conversation'] = [msg.content if hasattr(msg, 'content') else str(msg) for msg in conversation]
            session['current_case'] = case_number
            
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
            
            # Add user message to conversation
            conversation.append({'role': 'human', 'content': message})
            
            # Get AI response using the Groq client
            try:
                # Convert conversation to LangChain format
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
                        langchain_messages.append(SystemMessage(content=str(msg)))
                
                # Add the current user message
                langchain_messages.append(HumanMessage(content=message))
                
                # Get response from Groq
                response = client.invoke(langchain_messages)
                ai_reply = response.content
                
                # Add AI response to conversation
                conversation.append({'role': 'assistant', 'content': ai_reply})
                
                # Update session
                session['current_conversation'] = conversation
                
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
            
            if not case_number:
                return jsonify({'error': 'No active case session'}), 400
            
            # Evaluate conversation
            evaluation_results = evaluate_conversation(conversation, case_number)
            
            # Generate PDF report
            try:
                pdf_filename = create_simple_consultation_pdf(
                    conversation,
                    case_number,
                    evaluation_results,
                    evaluation_results.get('recommendations', [])
                )
                
                # Store in session for later download
                session['last_pdf'] = pdf_filename
                
            except Exception as e:
                logger.error(f"Error generating PDF: {str(e)}")
                pdf_filename = None
            
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
            
            return jsonify({
                'success': True,
                'evaluation': evaluation_results,
                'recommendations': evaluation_results.get('recommendations', []),
                'pdf_url': f'/download_pdf/{pdf_filename}' if pdf_filename else None
            })
            
        except Exception as e:
            logger.error(f"Error ending chat: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/download_pdf/<filename>')
    def download_pdf(filename):
        """Download generated PDF"""
        try:
            temp_dir = tempfile.gettempdir()
            return send_from_directory(temp_dir, filename, as_attachment=True)
        except Exception as e:
            logger.error(f"Error downloading PDF: {str(e)}")
            return jsonify({'error': 'PDF not found'}), 404

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
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)