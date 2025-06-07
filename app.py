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
        db.create_all()
        
        # Check if competition tables exist, if not create them
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
            db.create_all()

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


    # Routes
    @app.route('/')
    def index():
        """Render the main landing page with role selection"""
        return render_template('home.html')

    @app.context_processor
    def inject_globals():
        return {
            'load_patient_case': load_patient_case,
            'get_case_metadata': get_case_metadata,
            'get_unique_specialties': get_unique_specialties,
            'initialize_conversation': initialize_conversation,
            'evaluate_conversation': evaluate_conversation,
            'document_agent': document_agent,
            'evaluation_agent': evaluation_agent,
            'client': client,
        }

    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
