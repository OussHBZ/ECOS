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
from models import db, Student
from auth import auth_bp, student_required, teacher_required
from models import db, Student, TeacherAccess, PatientCase, StudentPerformance



import time
import concurrent.futures

# Import reporting modules
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import inch
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
    
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()

    # Create upload folder if it doesn't exist
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    
    # Create patient_data folder if it doesn't exist
    PATIENT_DATA_FOLDER = os.path.join(os.getcwd(), 'patient_data')
    os.makedirs(PATIENT_DATA_FOLDER, exist_ok=True)
    
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
            model="meta-llama/llama-4-scout-17b-16e-instruct",
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
        """Load patient case data from the database with fallback to JSON files"""
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
                # Fallback to JSON file if not in database
                logger.warning(f"Case {case_number} not found in database, trying JSON file")
                return load_patient_case_from_json(case_number)
                
        except Exception as e:
            logger.error(f"Error loading patient case {case_number} from database: {str(e)}")
            # Fallback to JSON file
            try:
                return load_patient_case_from_json(case_number)
            except:
                raise FileNotFoundError(f"Patient case {case_number} not found in database or JSON files.")

    def load_patient_case_from_json(case_number):
        """Load patient case data from JSON files (fallback method)"""
        try:
            PATIENT_DATA_FOLDER = os.path.join(os.getcwd(), 'patient_data')
            file_path = os.path.join(PATIENT_DATA_FOLDER, f"patient_case_{case_number}.json")
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Patient case JSON file {case_number} not found.")

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Ensure images key exists
            if "images" not in data:
                data["images"] = []
                
            logger.info(f"Successfully loaded patient case {case_number} from JSON file")
            return data
            
        except Exception as e:
            logger.error(f"Error loading patient case {case_number} from JSON: {str(e)}")
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
            
            # Do NOT add any initial automatic exchanges about images
            # This ensures that user messages appear first in chronological order
            
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
        
    @app.route('/teacher')
    @teacher_required
    def teacher_interface():
        """Render the teacher interface"""
        # Get list of existing cases
        cases = get_case_metadata()
        return render_template('teacher.html', cases=cases)
        
    @app.route('/student')
    @student_required
    def student_interface():
        """Render the student interface"""
        # Add student name to context
        cases = get_case_metadata()
        specialties = get_unique_specialties()
        return render_template('student.html', 
                             cases=cases, 
                             specialties=specialties,
                             student_name=current_user.name)
        
    @app.route('/process_case_file', methods=['POST'])
    @teacher_required
    def process_case_file():
        """Process uploaded case file and extract OSCE data with enhanced multi-image support"""
        try:
            if 'case_file' not in request.files:
                logger.warning("No file part in the request")
                return jsonify({"error": "No file part"}), 400
                    
            case_file = request.files['case_file']
                
            if case_file.filename == '':
                logger.warning("No file selected")
                return jsonify({"error": "No file selected"}), 400
                    
            # Get form data
            case_number = request.form.get('case_number')
            specialty = request.form.get('specialty')
                
            if not case_number or not specialty:
                logger.warning("Missing required fields")
                return jsonify({"error": "Missing required fields"}), 400
                    
            # Save the file temporarily
            filename = secure_filename(case_file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            case_file.save(temp_filepath)
                
            # Process image files if provided - ENHANCED FOR MULTIPLE IMAGES
            image_paths = []
            
            # Check for multiple image files
            if 'image_files' in request.files:
                image_files = request.files.getlist('image_files')
                
                for image_file in image_files:
                    if image_file and image_file.filename != '':
                        image_filename = secure_filename(image_file.filename)
                        image_filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                        image_file.save(image_filepath)
                        image_paths.append(image_filepath)
            
            # Process the main file
            extracted_data = document_agent.process_file(temp_filepath, file_ext, case_number, specialty)
            
            # Process any uploaded images using the multi-image processor
            if image_paths:
                logger.info(f"Processing {len(image_paths)} additional images for case {case_number}")
                image_data = document_agent.process_multiple_images(image_paths, case_number)
                
                # Add the images to extracted data
                if 'images' not in extracted_data:
                    extracted_data['images'] = []
                
                if 'images' in image_data:
                    # Combine all images (existing + new)
                    all_images = extracted_data['images'] + image_data['images']
                    # Deduplicate by (filename, path)
                    unique = {}
                    for img in all_images:
                        key = (img.get('filename'), img.get('path'))
                        if key not in unique:
                            unique[key] = img
                    extracted_data['images'] = list(unique.values())
            
            # Save the extracted data using the agent
            json_filepath = document_agent.save_case_data(
                case_number, 
                specialty, 
                extracted_data
            )
            
            # Clean up temporary files
            os.remove(temp_filepath)
            for image_path in image_paths:
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            logger.info(f"Successfully processed case file: {case_number} with {len(extracted_data.get('images', []))} images")
            return jsonify({
                "status": "success",
                "case_number": case_number,
                "specialty": specialty,
                "extracted_data": extracted_data
            })
                
        except Exception as e:
            logger.error(f"Error processing case file: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
    @app.route('/delete_case/<case_number>', methods=['DELETE'])
    @teacher_required
    def delete_case(case_number):
        """Delete a case from both JSON files and database"""
        try:
            # Validate case number
            if not case_number or case_number == 'None' or case_number == 'null':
                return jsonify({"error": "Numéro de cas invalide"}), 400
                
            file_path = os.path.join(PATIENT_DATA_FOLDER, f"patient_case_{case_number}.json")
            
            # Delete from JSON files (existing code)
            if os.path.exists(file_path):
                # Load the case data to get image paths
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        case_data = json.load(f)
                        
                    # Delete associated images if they exist
                    if 'images' in case_data and len(case_data['images']) > 0:
                        for image in case_data['images']:
                            if 'path' in image:
                                image_path = os.path.join(os.getcwd(), 'static', image['path'].lstrip('/static/'))
                                if os.path.exists(image_path):
                                    try:
                                        os.remove(image_path)
                                        logger.info(f"Deleted image: {image_path}")
                                    except:
                                        logger.warning(f"Could not delete image: {image_path}")
                except:
                    logger.warning(f"Could not process images for case {case_number} before deletion")
                
                # Delete the JSON file
                os.remove(file_path)
                logger.info(f"Successfully deleted JSON file for case {case_number}")
            
            # NOW DELETE FROM DATABASE
            try:
                db_case = PatientCase.query.filter_by(case_number=case_number).first()
                if db_case:
                    db.session.delete(db_case)
                    db.session.commit()
                    logger.info(f"Successfully deleted database record for case {case_number}")
                else:
                    logger.warning(f"No database record found for case {case_number}")
            except Exception as e:
                logger.error(f"Error deleting from database: {str(e)}")
                db.session.rollback()
                # Continue execution even if database deletion fails
            
            logger.info(f"Successfully deleted case {case_number}")
            return jsonify({"success": True})
            
        except Exception as e:
            logger.error(f"Error deleting case {case_number}: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
    @app.route('/initialize_chat', methods=['POST'])
    @student_required
    def initialize_chat():
        """Initialize a new chat session with selected case"""
        try:
            data = request.get_json()
            case_number = data.get('case_number')
            
            if not case_number:
                logger.warning("Case number not provided")
                return jsonify({"error": "Case number not provided"}), 400

            # Initialize new conversation
            conversation = initialize_conversation(case_number)
            
            # Get case data to extract consultation time
            case_data = load_patient_case(case_number)
            consultation_time = case_data.get('consultation_time', 10)  # Default to 10 if not specified
            directives = case_data.get('directives', '')  # Get directives if available

            # Store in session
            session['conversation'] = [
                {"role": msg.type, "content": msg.content}
                for msg in conversation
            ]
            session['case_number'] = case_number
            session['consultation_time'] = consultation_time
            session['consultation_start_time'] = time.time()  # Track start time for performance tracking
            
            logger.info(f"Chat initialized for case {case_number}")
            return jsonify({
                "status": "success",
                "consultation_time": consultation_time,  # Include the consultation time
                "directives": directives
            })
            
        except FileNotFoundError as e:
            logger.error(f"File not found: {str(e)}")
            return jsonify({"error": "Case not found"}), 404
        except Exception as e:
            logger.error(f"Error initializing chat: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500

    @app.route('/chat', methods=['POST'])
    @student_required
    def chat():
        """Handle chat messages with optimizations for faster responses"""
        try:
            if 'conversation' not in session:
                logger.warning("No active conversation found")
                return jsonify({"error": "No active conversation"}), 400

            data = request.get_json()
            user_message = data.get('message', '')
            
            if not user_message:
                logger.warning("Empty message received")
                return jsonify({"error": "Message cannot be empty"}), 400

            # Check if this is first user message (greeting)
            is_first_message = all(msg['role'] != 'human' for msg in session['conversation'])
            
            # Add user message to session immediately
            session['conversation'].append({
                "role": "human",
                "content": user_message
            })
            
            # Optimize the conversation history to keep it concise for faster processing
            optimized_conversation = []
            
            # Always keep the system message
            for msg in session['conversation']:
                if msg['role'] == 'system':
                    optimized_conversation.append(msg)
                    
            # Add the most recent messages (keep last 8 messages for context)
            recent_messages = [msg for msg in session['conversation'] if msg['role'] != 'system']
            if len(recent_messages) > 8:
                recent_messages = recent_messages[-8:]
                
            optimized_conversation.extend(recent_messages)
            
            # Convert optimized conversation to message objects for LLM
            conversation = []
            for msg in optimized_conversation:
                if msg['role'] == 'system':
                    conversation.append(SystemMessage(content=msg['content']))
                elif msg['role'] == 'human':
                    conversation.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'ai':
                    conversation.append(AIMessage(content=msg['content']))
            
            try:
                # Get LLM response
                logger.debug("Sending request to Groq API")
                response = client.invoke(conversation)
                
                content = response.content
                
                # Check if we need to insert images into the response
                case_number = session.get('case_number')
                if case_number:
                    try:
                        # Get case data to access available images
                        case_data = load_patient_case(case_number)
                        images = case_data.get('images', [])
                        
                        # If there are available images and the message appears to be requesting images
                        # or the LLM has included text indicating an image should be shown
                        image_indicators = ["image", "radiographie", "radio", "voir", "montr", "voici", "apporté"]
                        is_image_related = (
                            any(indicator in user_message.lower() for indicator in image_indicators) or
                            any(indicator in content.lower() for indicator in image_indicators)
                        )
                        
                        if images and is_image_related:
                            # Check if the LLM response already contains an image path
                            contains_image_path = any(img.get('path', '') in content for img in images)
                            
                            if not contains_image_path:
                                # If the LLM hasn't already included an image, but should have
                                # Find relevant images based on the conversation context
                                relevant_images = []
                                
                                # First try to match based on descriptions mentioned in the conversation
                                for img in images:
                                    description = img.get('description', '').lower()
                                    if description and (description in user_message.lower() or description in content.lower()):
                                        relevant_images.append(img)
                                
                                # If no description matches, include all images as options
                                if not relevant_images:
                                    relevant_images = images
                                
                                # Modify the content to include image(s)
                                # If it's a direct image request, format it as a patient sharing the image
                                if any(indicator in user_message.lower() for indicator in image_indicators):
                                    img = relevant_images[0]  # Use the first relevant image
                                    description = img.get('description', 'Image médicale')
                                    path = img.get('path', '')
                                    content = f"Oui, voici {description}: {path}"
                    except Exception as img_error:
                        logger.error(f"Error handling images in response: {str(img_error)}")

                # Add AI response to session
                session['conversation'].append({
                    "role": "ai",
                    "content": content
                })
                
                # Force session update
                session.modified = True
                
                logger.info("Successfully processed chat message")
                return jsonify({"reply": content})
                
            except Exception as e:
                logger.error(f"Error with Groq API: {str(e)}")
                return jsonify({"error": "Error processing message"}), 500
                
        except Exception as e:
            logger.error(f"Error in chat endpoint: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500
        
    def optimize_conversation_history(full_conversation):
        """Optimize conversation history to reduce token usage and speed up responses"""
        # Always keep the system message
        system_messages = [msg for msg in full_conversation if msg['role'] == 'system']
        
        # Keep only the last 8 messages (4 exchanges) for context, plus any system messages
        recent_messages = full_conversation[-8:] if len(full_conversation) > 8 else full_conversation
        
        # Ensure system messages are at the beginning
        optimized = system_messages + [msg for msg in recent_messages if msg['role'] != 'system']
        
        return optimized


    @app.route('/end_chat', methods=['POST'])
    @student_required
    def end_chat():
        """End the current chat session, evaluate and generate PDF report"""
        try:
            if 'conversation' not in session:
                logger.warning("No active conversation found")
                return jsonify({"error": "No active conversation"}), 400
            
            conversation_from_session = session['conversation'] # Get conversation
            case_number = session.get('case_number', 'Unknown')
            
            consultation_duration = None
            time_remaining = None
            if 'consultation_start_time' in session:
                import time
                consultation_duration = int(time.time() - session['consultation_start_time'])
                if 'consultation_time' in session:
                    total_time = session['consultation_time'] * 60
                    time_remaining = max(0, total_time - consultation_duration)
            
            eval_start = time.time()
            evaluation = evaluate_conversation(conversation_from_session, case_number)
            recommendations = evaluation_agent.get_recommendations()
            eval_time = time.time() - eval_start
            logger.info(f"Evaluation completed in {eval_time:.2f} seconds")
            
            # Save student performance, now including the conversation transcript
            save_student_performance(
                evaluation, 
                recommendations, 
                case_number, 
                consultation_duration, 
                time_remaining,
                conversation_transcript=conversation_from_session # Pass the transcript
            )
            
            try:
                pdf_filename = create_simple_consultation_pdf(
                    conversation_from_session, 
                    case_number, 
                    evaluation,
                    recommendations
                )
                session.clear()
                return jsonify({
                    "status": "success",
                    "pdf_url": f"/download_pdf/{pdf_filename}",
                    "evaluation": evaluation,
                    "recommendations": recommendations
                })
            except Exception as pdf_error:
                logger.error(f"PDF generation error: {str(pdf_error)}")
                session.clear()
                return jsonify({
                    "status": "partial_success",
                    "error": "PDF generation failed, but evaluation completed successfully",
                    "evaluation": evaluation,
                    "recommendations": recommendations
                })
        except Exception as e:
            logger.error(f"Error in end_chat: {str(e)}")
            return jsonify({"error": "Error ending chat session"}), 500
    
    def save_student_performance(evaluation, recommendations, case_number, consultation_duration=None, time_remaining=None, conversation_transcript=None): # Add conversation_transcript parameter
        """Save student performance to database"""
        try:
            if hasattr(current_user, 'id'):
                performance = StudentPerformance.create_from_evaluation(
                    student_id=current_user.id,
                    case_number=case_number,
                    evaluation_results=evaluation,
                    recommendations=recommendations,
                    consultation_duration=consultation_duration,
                    time_remaining=time_remaining,
                    conversation_transcript=conversation_transcript # Pass it here
                )
                
                db.session.add(performance)
                db.session.commit()
                logger.info(f"Saved performance for student {current_user.id}, case {case_number}")
                
        except Exception as e:
            logger.error(f"Error saving student performance: {str(e)}")
            db.session.rollback()

    @app.route('/download_pdf/<filename>')
    def download_pdf(filename):
        """Handle PDF download requests"""
        try:
            # Validate filename to prevent directory traversal
            if '..' in filename or '/' in filename:
                logger.warning(f"Invalid filename requested: {filename}")
                return jsonify({
                    "error": "Invalid filename"
                }), 400
                
            # Get temporary directory path
            temp_dir = tempfile.gettempdir()
            
            # Check if file exists
            file_path = os.path.join(temp_dir, filename)
            if not os.path.exists(file_path):
                logger.error(f"PDF file not found: {file_path}")
                return jsonify({
                    "error": "PDF file not found"
                }), 404
                
            try:
                # Send file with proper headers
                response = send_from_directory(
                    temp_dir,
                    filename,
                    as_attachment=True,
                    download_name=f"consultation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mimetype='application/pdf'
                )
                
                # Add security headers
                response.headers["Content-Security-Policy"] = "default-src 'self'"
                response.headers["X-Content-Type-Options"] = "nosniff"
                
                logger.info(f"PDF downloaded successfully: {filename}")
                return response
                
            except Exception as send_error:
                logger.error(f"Error sending PDF file: {str(send_error)}")
                return jsonify({
                    "error": "Error downloading PDF",
                    "details": str(send_error)
                }), 500
                
        except Exception as e:
            logger.error(f"Unexpected error in download_pdf: {str(e)}")
            return jsonify({
                "error": "An unexpected error occurred",
                "details": str(e)
            }), 500
    @app.route('/process_manual_case', methods=['POST'])
    @teacher_required
    def process_manual_case():
        """Process manually entered case data with database synchronization"""
        try:
            # ... (keep all your existing form processing code until the save part)
            
            # Extract basic case information
            case_number = request.form.get('case_number')
            specialty = request.form.get('specialty', '')
            
            if not case_number:
                logger.warning("Missing required case number")
                return jsonify({"error": "Le numéro du cas est obligatoire"}), 400
            
            # ... (keep all your existing patient info, symptoms, checklist processing code)
            
            # Extract patient information (same as before)
            patient_info = {
                "name": request.form.get('patient_name', ''),
                "gender": request.form.get('patient_gender', '')
            }
            
            # Only add age if provided
            if request.form.get('patient_age') and request.form.get('patient_age').strip():
                try:
                    patient_info["age"] = int(request.form.get('patient_age'))
                except ValueError:
                    patient_info["age"] = request.form.get('patient_age')
            
            # Add occupation if provided
            if request.form.get('patient_occupation'):
                patient_info["occupation"] = request.form.get('patient_occupation')
            
            # Process symptoms (same as before)
            symptoms = []
            symptom_entries = request.form.getlist('symptoms[]')
            symptom_durations = request.form.getlist('symptom_duration[]')
            symptom_descriptions = request.form.getlist('symptom_description[]')
            
            for i in range(len(symptom_entries)):
                if symptom_entries[i] and symptom_entries[i].strip():
                    symptom = symptom_entries[i].strip()
                    if i < len(symptom_durations) and symptom_durations[i] and symptom_durations[i].strip():
                        symptom += f" depuis {symptom_durations[i].strip()}"
                    if i < len(symptom_descriptions) and symptom_descriptions[i] and symptom_descriptions[i].strip():
                        symptom += f" ({symptom_descriptions[i].strip()})"
                    symptoms.append(symptom)
            
            # Process main complaint (same as before)
            chief_complaint = request.form.get('chief_complaint', '').strip()
            if chief_complaint:
                symptoms.insert(0, f"Motif de consultation: {chief_complaint}")
            
            # Process medical history (same as before)
            medical_history = []
            if request.form.get('medical_history') and request.form.get('medical_history').strip():
                medical_history.append(f"Antécédents médicaux: {request.form.get('medical_history').strip()}")
            if request.form.get('surgical_history') and request.form.get('surgical_history').strip():
                medical_history.append(f"Antécédents chirurgicaux: {request.form.get('surgical_history').strip()}")
            if request.form.get('family_history') and request.form.get('family_history').strip():
                medical_history.append(f"Antécédents familiaux: {request.form.get('family_history').strip()}")
            if request.form.get('medications') and request.form.get('medications').strip():
                medical_history.append(f"Traitements actuels: {request.form.get('medications').strip()}")
            if request.form.get('allergies') and request.form.get('allergies').strip():
                medical_history.append(f"Allergies: {request.form.get('allergies').strip()}")
            
            if medical_history:
                patient_info['medical_history'] = medical_history
            
            # Process evaluation checklist (same as before)
            evaluation_checklist = []
            checklist_descriptions = request.form.getlist('checklist_descriptions[]')
            checklist_points = request.form.getlist('checklist_points[]')
            checklist_categories = request.form.getlist('checklist_categories[]')
            
            for i in range(len(checklist_descriptions)):
                if checklist_descriptions[i] and checklist_descriptions[i].strip():
                    item = {
                        'description': checklist_descriptions[i].strip(),
                        'completed': False
                    }
                    
                    if i < len(checklist_points) and checklist_points[i]:
                        try:
                            item['points'] = int(checklist_points[i])
                        except ValueError:
                            item['points'] = 1
                    else:
                        item['points'] = 1
                    
                    if i < len(checklist_categories) and checklist_categories[i]:
                        item['category'] = checklist_categories[i]
                    
                    evaluation_checklist.append(item)
            
            # Process additional information (same as before)
            diagnosis = request.form.get('diagnosis', '').strip()
            differential_diagnosis = request.form.get('differential_diagnosis', '').strip()
            additional_notes = request.form.get('additional_notes', '').strip()
            
            # Process lab results (same as before)
            lab_results = request.form.get('lab_results', '').strip()
            if lab_results:
                patient_info['lab_results'] = lab_results
            
            # Process custom sections (same as before)
            custom_sections = []
            custom_section_json = request.form.get('custom_sections', '')
            
            if custom_section_json:
                try:
                    import json
                    custom_sections = json.loads(custom_section_json)
                except Exception as e:
                    logger.error(f"Error parsing custom sections: {str(e)}")
            else:
                custom_section_titles = request.form.getlist('custom_section_titles[]')
                custom_section_contents = request.form.getlist('custom_section_contents[]')
                
                for i in range(min(len(custom_section_titles), len(custom_section_contents))):
                    if custom_section_titles[i].strip() and custom_section_contents[i].strip():
                        custom_sections.append({
                            'title': custom_section_titles[i].strip(),
                            'content': custom_section_contents[i].strip()
                        })
            
            # Process images (same as before - use your existing image processing code)
            images = []
            # ... (keep your existing image processing code)
            
            # Process consultation time (same as before)
            consultation_time = request.form.get('consultation_time')
            try:
                consultation_time = int(consultation_time) if consultation_time else 10
                if consultation_time < 1:
                    consultation_time = 1
                elif consultation_time > 60:
                    consultation_time = 60
            except ValueError:
                consultation_time = 10
            
            # Get directives for the case
            directives = request.form.get('case_directives', '').strip()

            # Create the final case data
            case_data = {
                'case_number': case_number,
                'specialty': specialty,
                'patient_info': patient_info,
                'symptoms': symptoms,
                'evaluation_checklist': evaluation_checklist,
                'images': images,
                'consultation_time': consultation_time,
                'custom_sections': custom_sections,
            }
            
            # Add directives if provided
            if directives:
                case_data['directives'] = directives
            # Add optional fields only if they have values
            if diagnosis:
                case_data['diagnosis'] = diagnosis
            if differential_diagnosis:
                case_data['differential_diagnosis'] = differential_diagnosis
            if additional_notes:
                case_data['additional_notes'] = additional_notes
            
            # Save to JSON file first
            file_path = os.path.join('patient_data', f'patient_case_{case_number}.json')
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(case_data, f, ensure_ascii=False, indent=2)
            
            # NOW SYNC WITH DATABASE
            try:
                # Check if case already exists in database
                existing_db_case = PatientCase.query.filter_by(case_number=case_number).first()
                
                if existing_db_case:
                    # Update existing database record
                    logger.info(f"Updating existing database record for case {case_number}")
                    existing_db_case.update_from_json_data(case_data)
                else:
                    # Create new database record
                    logger.info(f"Creating new database record for case {case_number}")
                    db_case = PatientCase.from_json_data(case_data)
                    db.session.add(db_case)
                
                # Commit database changes
                db.session.commit()
                logger.info(f"Successfully synchronized case {case_number} with database")
                
            except Exception as e:
                logger.error(f"Error synchronizing with database: {str(e)}")
                # Continue execution even if database sync fails
                db.session.rollback()
            
            logger.info(f"Successfully created case {case_number} with manual entry and {len(images)} images")
            return jsonify({
                "status": "success",
                "case_number": case_number,
                "specialty": specialty,
                "patient_info": patient_info,
                "symptoms": symptoms,
                "evaluation_checklist": evaluation_checklist,
                "images": images,
                "directives": directives,
                "custom_sections": custom_sections
            })
            
        except Exception as e:
            logger.error(f"Error processing manual case: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/preview_extraction', methods=['POST'])
    def preview_extraction():
        """Preview and allow editing of extracted data before final save"""
        try:
            data = request.get_json()
            extracted_data = data.get('extracted_data', {})
            case_number = data.get('case_number')
            specialty = data.get('specialty')
            
            if not case_number:
                return jsonify({"error": "Case number is required"}), 400
                    
            # Validate the extraction - directly pass the extracted data
            issues = document_agent._validate_extraction() if hasattr(document_agent, 'state') else []
            
            # Return the extracted data and any issues for user review
            return jsonify({
                "extracted_data": extracted_data,
                "issues": issues,
                "case_number": case_number,
                "specialty": specialty
            })
            
        except Exception as e:
            logger.error(f"Error in preview extraction: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
    @app.route('/save_edited_case', methods=['POST'])
    def save_edited_case():
        try:
            data = request.get_json()
            edited_data = data.get('edited_data', {})
            case_number = data.get('case_number')
            specialty = data.get('specialty')
            
            if not case_number:
                return jsonify({"error": "Case number is required"}), 400
            
            # Make sure specialty is included
            if specialty and 'specialty' not in edited_data:
                edited_data['specialty'] = specialty
            
            # Make sure custom_sections is part of the edited data
            if 'custom_sections' not in edited_data:
                edited_data['custom_sections'] = []
            
            # Save the edited data
            file_path = os.path.join('patient_data', f'patient_case_{case_number}.json')
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(edited_data, f, ensure_ascii=False, indent=2)
            
            return jsonify({
                "status": "success",
                "message": "Case saved successfully",
                "file_path": file_path
            })
            
        except Exception as e:
            logger.error(f"Error saving edited case: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/get_case/<case_number>', methods=['GET'])
    def get_case(case_number):
        """Get case details by case number with cache prevention"""
        try:
            # Validate case number
            if not case_number or case_number == 'None' or case_number == 'null':
                return jsonify({"error": "Numéro de cas invalide"}), 400
                
            # Construct the file path
            file_path = os.path.join(PATIENT_DATA_FOLDER, f"patient_case_{case_number}.json")
            
            # Check if the file exists
            if not os.path.exists(file_path):
                logger.warning(f"Case file not found: {file_path}")
                return jsonify({"error": "Cas non trouvé"}), 404
                
            # Load the case data with fresh read
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    case_data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in case file {file_path}: {str(e)}")
                return jsonify({"error": "Fichier de cas corrompu"}), 500
            except Exception as e:
                logger.error(f"Error reading case file {file_path}: {str(e)}")
                return jsonify({"error": "Erreur lors de la lecture du fichier"}), 500
                    
            logger.info(f"Successfully retrieved case {case_number}")
            
            # Create response with cache-prevention headers
            response = jsonify(case_data)
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            return response
            
        except Exception as e:
            logger.error(f"Error retrieving case {case_number}: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/get_case_images/<case_number>')
    def get_case_images(case_number):
        """Get all images for a specific case with enhanced metadata"""
        try:
            case_data = load_patient_case(case_number)
            
            # Extract images array from case data
            images = case_data.get('images', [])
            
            # Enhance image metadata
            enhanced_images = []
            for i, image in enumerate(images):
                enhanced_image = {
                    'path': image.get('path', ''),
                    'description': image.get('description', f'Image médicale {i+1}'),
                    'index': i,
                    'filename': image.get('filename', '')
                }
                enhanced_images.append(enhanced_image)
            
            # Get specialty for context
            specialty = case_data.get('specialty', 'Non spécifié')
            
            return jsonify({
                "status": "success", 
                "images": enhanced_images,
                "count": len(enhanced_images),
                "specialty": specialty,
                "case_number": case_number
            })
        except FileNotFoundError:
            logger.error(f"Case not found: {case_number}")
            return jsonify({"error": "Case not found"}), 404
        except Exception as e:
            logger.error(f"Error retrieving images for case {case_number}: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/edit_case/<case_number>', methods=['POST'])
    @teacher_required
    def edit_case(case_number):
        """Edit an existing case with database synchronization"""
        try:
            data = request.get_json()
            edited_data = data.get('edited_data', {})
            
            logger.info(f"Received edit request for case {case_number}")
            logger.debug(f"Edited data received: {json.dumps(edited_data, indent=2, ensure_ascii=False)}")
            
            if not case_number:
                return jsonify({"error": "Case number is required"}), 400
            
            # Validate that the case exists in JSON files
            file_path = os.path.join(PATIENT_DATA_FOLDER, f"patient_case_{case_number}.json")
            if not os.path.exists(file_path):
                logger.error(f"Case file not found: {file_path}")
                return jsonify({"error": "Case not found"}), 404
            
            # Load existing case data from JSON file to preserve images
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                logger.info(f"Loaded existing case data for case {case_number}")
            except Exception as e:
                logger.error(f"Error loading existing case data: {str(e)}")
                return jsonify({"error": "Error loading existing case data"}), 500
            
            # Merge edited data with existing data, preserving important fields
            updated_data = existing_data.copy()
            
            # Update basic information
            updated_data['case_number'] = case_number
            updated_data['specialty'] = edited_data.get('specialty', existing_data.get('specialty', 'Non spécifié'))
            updated_data['consultation_time'] = edited_data.get('consultation_time', existing_data.get('consultation_time', 10))
            
            # Update patient info - merge with existing
            existing_patient_info = existing_data.get('patient_info', {})
            new_patient_info = edited_data.get('patient_info', {})
            
            # Merge patient info carefully
            updated_patient_info = existing_patient_info.copy()
            updated_patient_info.update(new_patient_info)
            
            # Handle special cases for patient info
            if 'age' in new_patient_info:
                if new_patient_info['age'] is not None and new_patient_info['age'] != '':
                    try:
                        updated_patient_info['age'] = int(new_patient_info['age'])
                    except (ValueError, TypeError):
                        pass
            
            updated_data['patient_info'] = updated_patient_info
            
            # Update other fields
            updated_data['symptoms'] = edited_data.get('symptoms', existing_data.get('symptoms', []))
            updated_data['evaluation_checklist'] = edited_data.get('evaluation_checklist', existing_data.get('evaluation_checklist', []))
            updated_data['custom_sections'] = edited_data.get('custom_sections', existing_data.get('custom_sections', []))
            
            # Update optional fields
            for field in ['diagnosis', 'differential_diagnosis', 'directives', 'additional_notes']:
                if field in edited_data:
                    if edited_data[field]:
                        updated_data[field] = edited_data[field]
                    elif field in updated_data:
                        del updated_data[field]
            
            # Preserve images from existing data
            if 'images' in existing_data:
                updated_data['images'] = existing_data['images']
            elif 'images' not in updated_data:
                updated_data['images'] = []
            
            # Log the final data before saving
            logger.debug(f"Final data to save: {json.dumps(updated_data, indent=2, ensure_ascii=False)}")
            
            # Save to JSON file first
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(updated_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Successfully saved updated case data to {file_path}")
            except Exception as e:
                logger.error(f"Error saving case data to JSON: {str(e)}")
                return jsonify({"error": "Error saving case data to JSON"}), 500
            
            # NOW SYNC WITH DATABASE
            try:
                # Check if case exists in database
                db_case = PatientCase.query.filter_by(case_number=case_number).first()
                
                if db_case:
                    # Update existing database record
                    logger.info(f"Updating existing database record for case {case_number}")
                    db_case.update_from_json_data(updated_data)
                else:
                    # Create new database record
                    logger.info(f"Creating new database record for case {case_number}")
                    db_case = PatientCase.from_json_data(updated_data)
                    db.session.add(db_case)
                
                # Commit database changes
                db.session.commit()
                logger.info(f"Successfully synchronized case {case_number} with database")
                
            except Exception as e:
                logger.error(f"Error synchronizing with database: {str(e)}")
                # Rollback database changes but continue (JSON file is already saved)
                db.session.rollback()
                logger.warning("Database sync failed but JSON file was saved successfully")
            
            logger.info(f"Successfully edited case {case_number}")
            return jsonify({
                "status": "success",
                "message": "Case updated successfully",
                "case_number": case_number
            })
            
        except Exception as e:
            logger.error(f"Error editing case {case_number}: {str(e)}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    @app.route('/student/stats')
    @student_required
    def student_stats():
        """Get student statistics"""
        try:
            # Get current student stats
            stats = {
                'total_workouts': current_user.get_total_workouts(),
                'unique_stations': current_user.get_unique_stations_played(),
                'average_score': current_user.get_average_score(),
                'recent_performances': []
            }
            
            # Get recent performances with case details
            recent_performances = current_user.get_recent_performances(10)
            for perf in recent_performances:
                case = PatientCase.query.filter_by(case_number=perf.case_number).first()
                stats['recent_performances'].append({
                    'case_number': perf.case_number,
                    'specialty': case.specialty if case else 'Unknown',
                    'score': perf.percentage_score,
                    'grade': perf.get_performance_grade(),
                    'status': perf.get_performance_status(),
                    'completed_at': perf.completed_at.strftime('%d/%m/%Y %H:%M'),
                    'duration': f"{perf.consultation_duration // 60}:{perf.consultation_duration % 60:02d}" if perf.consultation_duration else "N/A"
                })
            
            return jsonify(stats)
            
        except Exception as e:
            logger.error(f"Error getting student stats: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/student/stations')
    @student_required
    def student_stations():
        """Get available stations for student with search"""
        try:
            search_query = request.args.get('search', '').strip()
            
            # Base query
            query = PatientCase.query
            
            # Apply search filter if provided
            if search_query:
                query = query.filter(
                    db.or_(
                        PatientCase.case_number.contains(search_query),
                        PatientCase.specialty.contains(search_query)
                    )
                )
            
            cases = query.order_by(PatientCase.case_number).all()
            
            stations = []
            for case in cases:
                # Get student's performance for this case
                student_performances = StudentPerformance.query.filter_by(
                    student_id=current_user.id,
                    case_number=case.case_number
                ).order_by(StudentPerformance.completed_at.desc()).all()
                
                best_score = 0
                attempts = len(student_performances)
                last_attempt = None
                
                if student_performances:
                    best_score = max(perf.percentage_score for perf in student_performances)
                    last_attempt = student_performances[0].completed_at.strftime('%d/%m/%Y')
                
                stations.append({
                    'case_number': case.case_number,
                    'specialty': case.specialty,
                    'consultation_time': case.consultation_time,
                    'attempts': attempts,
                    'best_score': best_score,
                    'last_attempt': last_attempt,
                    'grade': StudentPerformance().get_performance_grade() if best_score > 0 else None
                })
            
            return jsonify({
                'stations': stations,
                'total': len(stations)
            })
            
        except Exception as e:
            logger.error(f"Error getting student stations: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/teacher/stations')
    @teacher_required
    def teacher_stations_management():
        """Get stations for teacher management"""
        try:
            search_query = request.args.get('search', '').strip()
            
            # Base query
            query = PatientCase.query
            
            # Apply search filter if provided
            if search_query:
                query = query.filter(
                    db.or_(
                        PatientCase.case_number.contains(search_query),
                        PatientCase.specialty.contains(search_query)
                    )
                )
            
            cases = query.order_by(PatientCase.case_number).all()
            
            stations = []
            for case in cases:
                stations.append({
                    'case_number': case.case_number,
                    'specialty': case.specialty,
                    'consultation_time': case.consultation_time,
                    'created_at': case.created_at.strftime('%d/%m/%Y'),
                    'updated_at': case.updated_at.strftime('%d/%m/%Y'),
                    'completion_count': case.get_completion_count(),
                    'average_score': case.get_average_score()
                })
            
            return jsonify({
                'stations': stations,
                'total': len(stations)
            })
            
        except Exception as e:
            logger.error(f"Error getting teacher stations: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/teacher/students/performance')
    @teacher_required
    def teacher_student_performance():
        """Get student performance data for teachers"""
        try:
            search_query = request.args.get('search', '').strip()
            
            # Base query
            query = Student.query
            
            # Apply search filter if provided
            if search_query:
                query = query.filter(
                    db.or_(
                        Student.name.contains(search_query),
                        Student.student_code.contains(search_query)
                    )
                )
            
            students = query.order_by(Student.name).all()
            
            student_performance = []
            for student in students:
                performances = StudentPerformance.query.filter_by(student_id=student.id)\
                    .order_by(StudentPerformance.completed_at.desc()).all()
                
                recent_performances = []
                for perf in performances[:5]:  # Last 5 performances
                    case = PatientCase.query.filter_by(case_number=perf.case_number).first()
                    recent_performances.append({
                        'case_number': perf.case_number,
                        'specialty': case.specialty if case else 'Unknown',
                        'score': perf.percentage_score,
                        'grade': perf.get_performance_grade(),
                        'completed_at': perf.completed_at.strftime('%d/%m/%Y %H:%M')
                    })
                
                student_performance.append({
                    'student_id': student.id,
                    'student_code': student.student_code,
                    'name': student.name,
                    'total_workouts': student.get_total_workouts(),
                    'unique_stations': student.get_unique_stations_played(),
                    'average_score': student.get_average_score(),
                    'last_login': student.last_login.strftime('%d/%m/%Y %H:%M') if student.last_login else 'Never',
                    'recent_performances': recent_performances
                })
            
            return jsonify({
                'students': student_performance,
                'total': len(student_performance)
            })
            
        except Exception as e:
            logger.error(f"Error getting student performance: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/teacher/students/<int:student_id>/detailed_performance')
    @teacher_required
    def student_detailed_performance(student_id):
        """Get detailed performance for a specific student"""
        try:
            student = Student.query.get_or_404(student_id)
            
            performances = StudentPerformance.query.filter_by(student_id=student_id)\
                .order_by(StudentPerformance.completed_at.desc()).all()
            
            detailed_performances = []
            for perf in performances:
                case = PatientCase.query.filter_by(case_number=perf.case_number).first()
                detailed_performances.append({
                    'id': perf.id,
                    'case_number': perf.case_number,
                    'specialty': case.specialty if case else 'Unknown',
                    'score': perf.percentage_score,
                    'points_earned': perf.points_earned,
                    'points_total': perf.points_total,
                    'grade': perf.get_performance_grade(),
                    'status': perf.get_performance_status(),
                    'consultation_duration': f"{perf.consultation_duration // 60}:{perf.consultation_duration % 60:02d}" if perf.consultation_duration else "N/A",
                    'completed_at': perf.completed_at.strftime('%d/%m/%Y %H:%M'),
                    'evaluation_results': perf.evaluation_results,
                    'recommendations': perf.recommendations
                })
            
            return jsonify({
                'student': {
                    'id': student.id,
                    'name': student.name,
                    'student_code': student.student_code,
                    'total_workouts': student.get_total_workouts(),
                    'unique_stations': student.get_unique_stations_played(),
                    'average_score': student.get_average_score()
                },
                'performances': detailed_performances
            })
            
        except Exception as e:
            logger.error(f"Error getting detailed student performance: {str(e)}")
            return jsonify({"error": str(e)}), 500
        
    @app.route('/teacher/download_student_report/<int:performance_id>')
    @teacher_required # Assuming this decorator exists or use appropriate one
    def download_student_report(performance_id):
        try:
            # Use db.session.get for SQLAlchemy 2.0 compatibility, or stick to .get() if on 1.x
            # performance = StudentPerformance.query.get(performance_id) # Legacy
            performance = db.session.get(StudentPerformance, performance_id) # Preferred for SQLAlchemy 2.0+
            
            if not performance:
                logger.error(f"Performance record not found for ID: {performance_id}")
                return jsonify({"error": "Rapport de performance non trouvé"}), 404

            # Now 'performance.conversation_transcript' will call the property in models.py
            conversation_for_pdf = performance.conversation_transcript 
            
            if not conversation_for_pdf:
                logger.error(f"No conversation transcript found for performance ID: {performance_id}")
                return jsonify({"error": "Aucun historique de conversation trouvé pour ce rapport"}), 404

            case_number = performance.case_number
            evaluation_results = performance.evaluation_results
            recommendations = performance.recommendations

            pdf_filename = create_simple_consultation_pdf(
                conversation_for_pdf,
                case_number,
                evaluation_results,
                recommendations
            )
            
            # Assuming create_simple_consultation_pdf saves to a temp directory
            temp_dir = tempfile.gettempdir()
            return send_from_directory(
                temp_dir,
                pdf_filename,
                as_attachment=True,
                download_name=f"student_report_{performance.student.student_code}_case_{case_number}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mimetype='application/pdf'
            )

        except AttributeError as ae: # Catch the specific error if it persists for debugging
            logger.error(f"AttributeError generating student report PDF for performance ID {performance_id}: {str(ae)}", exc_info=True)
            return jsonify({"error": "Erreur d'attribut lors de la génération du rapport PDF"}), 500
        except Exception as e:
            logger.error(f"Error generating student report PDF for performance ID {performance_id}: {str(e)}", exc_info=True)
            return jsonify({"error": "Erreur lors de la génération du rapport PDF"}), 500
    
    @app.route('/check_case_number/<case_number>', methods=['GET'])
    @teacher_required
    def check_case_number(case_number):
        """Check if a case number already exists"""
        try:
            # Validate case number
            if not case_number or case_number.strip() == '':
                return jsonify({"error": "Numéro de cas invalide"}), 400
            
            # Check in database first
            db_case = PatientCase.query.filter_by(case_number=str(case_number)).first()
            if db_case:
                return jsonify({
                    "exists": True,
                    "message": f"Le numéro de cas {case_number} existe déjà dans la base de données"
                })
            
            # Check in JSON files as fallback
            file_path = os.path.join(PATIENT_DATA_FOLDER, f"patient_case_{case_number}.json")
            if os.path.exists(file_path):
                return jsonify({
                    "exists": True,
                    "message": f"Le numéro de cas {case_number} existe déjà dans les fichiers"
                })
            
            # Case number is available
            return jsonify({
                "exists": False,
                "message": f"Le numéro de cas {case_number} est disponible"
            })
            
        except Exception as e:
            logger.error(f"Error checking case number {case_number}: {str(e)}")
            return jsonify({"error": "Erreur lors de la vérification du numéro de cas"}), 500


    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)