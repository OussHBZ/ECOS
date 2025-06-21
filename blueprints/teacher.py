from flask import Blueprint, render_template, request, jsonify, current_app, send_from_directory
from flask_login import current_user
from models import db, PatientCase, StudentPerformance, Student
from auth import teacher_required
import logging
import os
from werkzeug.utils import secure_filename
import json
import tempfile
from simple_pdf_generator import create_simple_consultation_pdf
from datetime import datetime

# CREATE THE BLUEPRINT - This must be at the top level
teacher_bp = Blueprint('teacher', __name__)
logger = logging.getLogger(__name__)

@teacher_bp.route('/')
@teacher_required
def teacher_interface():
    """Render the teacher interface"""
    # Get list of existing cases
    get_case_metadata = current_app.config.get('GET_CASE_METADATA')
    
    if not get_case_metadata:
        logger.error("GET_CASE_METADATA function not found in app config")
        cases = []
    else:
        cases = get_case_metadata()
    
    return render_template('teacher.html', cases=cases)

@teacher_bp.route('/process_case_file', methods=['POST'])
@teacher_required
def process_case_file():
    """Process uploaded case file and extract OSCE data with enhanced multi-image support"""
    document_agent = current_app.config.get('DOCUMENT_AGENT')
    
    if not document_agent:
        logger.error("DOCUMENT_AGENT not found in app config")
        return jsonify({"error": "Document processing not available"}), 500

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
        
        # Check if case already exists
        existing_case = PatientCase.query.filter_by(case_number=case_number).first()
        if existing_case:
            logger.warning(f"Case {case_number} already exists")
            return jsonify({"error": f"Case {case_number} already exists"}), 400
                
        # Save the file temporarily
        filename = secure_filename(case_file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        temp_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        case_file.save(temp_filepath)
            
        # Process image files if provided - ENHANCED FOR MULTIPLE IMAGES
        image_paths = []
        
        # Check for multiple image files
        if 'image_files' in request.files:
            image_files = request.files.getlist('image_files')
            
            for image_file in image_files:
                if image_file and image_file.filename != '':
                    image_filename = secure_filename(image_file.filename)
                    image_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)
                    image_file.save(image_filepath)
                    image_paths.append(image_filepath)
        
        # Process the main file - BUT DON'T SAVE TO DATABASE YET
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
        
        # DON'T SAVE THE DATA HERE - JUST RETURN IT FOR PREVIEW
        # document_agent.save_case_data(case_number, specialty, extracted_data)  # REMOVE THIS LINE
        
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

@teacher_bp.route('/process_manual_case', methods=['POST'])
@teacher_required
def process_manual_case():
    """Process manually entered case data"""
    try:
        # Get form data
        case_number = request.form.get('case_number')
        specialty = request.form.get('specialty')
        
        if not case_number or not specialty:
            return jsonify({"error": "Case number and specialty are required"}), 400
        
        # Check if case already exists
        existing_case = PatientCase.query.filter_by(case_number=case_number).first()
        if existing_case:
            return jsonify({"error": f"Case {case_number} already exists"}), 400
        
        # Build patient info
        patient_info = {}
        if request.form.get('patient_name'):
            patient_info['name'] = request.form.get('patient_name')
        if request.form.get('patient_age'):
            patient_info['age'] = int(request.form.get('patient_age'))
        if request.form.get('patient_gender'):
            patient_info['gender'] = request.form.get('patient_gender')
        if request.form.get('patient_occupation'):
            patient_info['occupation'] = request.form.get('patient_occupation')
        
        # Build medical history
        medical_history = []
        if request.form.get('medical_history'):
            medical_history.append(request.form.get('medical_history'))
        if request.form.get('surgical_history'):
            medical_history.append(f"Chirurgical: {request.form.get('surgical_history')}")
        if request.form.get('family_history'):
            medical_history.append(f"Familial: {request.form.get('family_history')}")
        if request.form.get('medications'):
            medical_history.append(f"Traitements: {request.form.get('medications')}")
        if request.form.get('allergies'):
            medical_history.append(f"Allergies: {request.form.get('allergies')}")
        
        if medical_history:
            patient_info['medical_history'] = medical_history
        
        # Build symptoms
        symptoms = []
        chief_complaint = request.form.get('chief_complaint')
        if chief_complaint:
            symptoms.append(f"Motif principal: {chief_complaint}")
        
        symptom_names = request.form.getlist('symptoms[]')
        symptom_durations = request.form.getlist('symptom_duration[]')
        symptom_descriptions = request.form.getlist('symptom_description[]')
        
        for i, symptom in enumerate(symptom_names):
            if symptom.strip():
                symptom_text = symptom.strip()
                if i < len(symptom_durations) and symptom_durations[i].strip():
                    symptom_text += f" (depuis {symptom_durations[i].strip()})"
                if i < len(symptom_descriptions) and symptom_descriptions[i].strip():
                    symptom_text += f" - {symptom_descriptions[i].strip()}"
                symptoms.append(symptom_text)
        
        # Build evaluation checklist
        checklist_descriptions = request.form.getlist('checklist_descriptions[]')
        checklist_points = request.form.getlist('checklist_points[]')
        checklist_categories = request.form.getlist('checklist_categories[]')
        
        evaluation_checklist = []
        for i, description in enumerate(checklist_descriptions):
            if description.strip():
                points = 1
                if i < len(checklist_points) and checklist_points[i]:
                    try:
                        points = int(checklist_points[i])
                    except ValueError:
                        points = 1
                
                category = 'Général'
                if i < len(checklist_categories) and checklist_categories[i]:
                    category = checklist_categories[i]
                
                evaluation_checklist.append({
                    'description': description.strip(),
                    'points': points,
                    'category': category,
                    'completed': False
                })
        
        # Handle custom sections
        custom_sections = []
        custom_sections_json = request.form.get('custom_sections')
        if custom_sections_json:
            try:
                custom_sections = json.loads(custom_sections_json)
            except json.JSONDecodeError:
                logger.warning("Invalid custom sections JSON")
        
        # Handle images
        images = []
        if 'manual_images' in request.files:
            image_files = request.files.getlist('manual_images')
            image_descriptions_text = request.form.get('image_descriptions', '')
            image_descriptions = [desc.strip() for desc in image_descriptions_text.split('\n') if desc.strip()]
            
            for i, image_file in enumerate(image_files):
                if image_file and image_file.filename:
                    filename = secure_filename(image_file.filename)
                    # Save to static/images/cases/ directory
                    images_dir = os.path.join(current_app.static_folder, 'images', 'cases')
                    os.makedirs(images_dir, exist_ok=True)
                    
                    # Create unique filename
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    file_ext = os.path.splitext(filename)[1]
                    unique_filename = f"case_{case_number}_{timestamp}_{i}{file_ext}"
                    
                    image_path = os.path.join(images_dir, unique_filename)
                    image_file.save(image_path)
                    
                    # Store relative path for web access
                    web_path = f"/static/images/cases/{unique_filename}"
                    
                    description = image_descriptions[i] if i < len(image_descriptions) else f"Image {i+1}"
                    
                    images.append({
                        'path': web_path,
                        'description': description,
                        'filename': unique_filename
                    })
        
        # Create new case
        new_case = PatientCase(
            case_number=case_number,
            specialty=specialty,
            patient_info=patient_info,
            symptoms=symptoms,
            evaluation_checklist=evaluation_checklist,
            diagnosis=request.form.get('diagnosis', ''),
            differential_diagnosis=request.form.get('differential_diagnosis', ''),
            directives=request.form.get('case_directives', ''),
            consultation_time=int(request.form.get('consultation_time', 10)),
            additional_notes=request.form.get('additional_notes', ''),
            custom_sections=custom_sections
        )
        
        db.session.add(new_case)
        db.session.commit()  # Commit first to get the case persisted
        
        # Add images to database using case_number (not case_id)
        from models import CaseImage
        for img in images:
            case_image = CaseImage(
                case_number=case_number,  # Use case_number, not case_id
                path=img['path'],
                description=img['description'],
                filename=img['filename']
            )
            db.session.add(case_image)
        
        db.session.commit()
        
        logger.info(f"Successfully created manual case: {case_number}")
        return jsonify({
            "status": "success",
            "case_number": case_number,
            "specialty": specialty,
            "patient_info": patient_info,
            "symptoms": symptoms,
            "evaluation_checklist": evaluation_checklist,
            "images": images,
            "custom_sections": custom_sections
        })
        
    except Exception as e:
        logger.error(f"Error processing manual case: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/save_edited_case', methods=['POST'])
@teacher_required
def save_edited_case():
    """Save edited case data from extraction preview"""
    try:
        # Log the incoming request
        logger.info("save_edited_case route called")
        logger.info(f"Request content type: {request.content_type}")
        
        data = request.get_json()
        logger.info(f"Parsed JSON data keys: {list(data.keys()) if data else 'None'}")
        
        if not data:
            logger.error("No JSON data received")
            return jsonify({"error": "No data received"}), 400
        
        edited_data = data.get('edited_data')
        case_number = data.get('case_number')
        specialty = data.get('specialty')
        
        logger.info(f"extracted values - case_number: {case_number}, specialty: {specialty}")
        logger.info(f"edited_data keys: {list(edited_data.keys()) if edited_data else 'None'}")
        
        if not edited_data:
            logger.error("No edited_data in request")
            return jsonify({"error": "Missing edited_data"}), 400
            
        if not case_number:
            logger.error("No case_number in request")
            return jsonify({"error": "Missing case_number"}), 400
            
        if not specialty:
            logger.error("No specialty in request")
            return jsonify({"error": "Missing specialty"}), 400
        
        # Check if case already exists
        existing_case = PatientCase.query.filter_by(case_number=case_number).first()
        if existing_case:
            logger.warning(f"Case {case_number} already exists - updating instead of creating")
            # UPDATE THE EXISTING CASE INSTEAD OF CREATING A NEW ONE
            existing_case.specialty = specialty  # Update specialty as well
            existing_case.patient_info = edited_data.get('patient_info', existing_case.patient_info)
            existing_case.symptoms = edited_data.get('symptoms', existing_case.symptoms)
            existing_case.evaluation_checklist = edited_data.get('evaluation_checklist', existing_case.evaluation_checklist)
            existing_case.diagnosis = edited_data.get('diagnosis', existing_case.diagnosis)
            existing_case.differential_diagnosis = edited_data.get('differential_diagnosis', existing_case.differential_diagnosis)
            existing_case.directives = edited_data.get('directives', existing_case.directives)
            existing_case.consultation_time = edited_data.get('consultation_time', existing_case.consultation_time)
            existing_case.additional_notes = edited_data.get('additional_notes', existing_case.additional_notes)
            existing_case.custom_sections = edited_data.get('custom_sections', existing_case.custom_sections)
            existing_case.updated_at = datetime.utcnow()
            
            # Handle images - remove old ones and add new ones
            from models import CaseImage
            
            # Remove existing images for this case
            old_images = CaseImage.query.filter_by(case_number=case_number).all()
            for img in old_images:
                # Delete physical file if it exists
                if img.path.startswith('/static/'):
                    file_path = os.path.join(current_app.static_folder, img.path[8:])
                    if os.path.exists(file_path):
                        os.remove(file_path)
                db.session.delete(img)
            
            # Add new images using case_number (not case_id)
            images_data = edited_data.get('images', [])
            for img_data in images_data:
                case_image = CaseImage(
                    case_number=case_number,  # Use case_number, not case_id
                    path=img_data.get('path', ''),
                    description=img_data.get('description', ''),
                    filename=img_data.get('filename', '')
                )
                db.session.add(case_image)
            
            db.session.commit()
            logger.info(f"Successfully updated existing case: {case_number}")
            return jsonify({"status": "success", "case_number": case_number, "action": "updated"})
        
        else:
            # CREATE NEW CASE
            new_case = PatientCase(
                case_number=case_number,
                specialty=specialty,
                patient_info=edited_data.get('patient_info', {}),
                symptoms=edited_data.get('symptoms', []),
                evaluation_checklist=edited_data.get('evaluation_checklist', []),
                diagnosis=edited_data.get('diagnosis', ''),
                differential_diagnosis=edited_data.get('differential_diagnosis', ''),
                directives=edited_data.get('directives', ''),
                consultation_time=edited_data.get('consultation_time', 10),
                additional_notes=edited_data.get('additional_notes', ''),
                custom_sections=edited_data.get('custom_sections', [])
            )
            
            db.session.add(new_case)
            db.session.commit()  # Commit first to get the case persisted
            
            logger.info(f"New case created with case_number: {new_case.case_number}")
            
            # Handle images using case_number (not case_id)
            from models import CaseImage
            images_data = edited_data.get('images', [])
            logger.info(f"Processing {len(images_data)} images")
            
            for img_data in images_data:
                case_image = CaseImage(
                    case_number=case_number,  # Use case_number, not case_id
                    path=img_data.get('path', ''),
                    description=img_data.get('description', ''),
                    filename=img_data.get('filename', '')
                )
                db.session.add(case_image)
            
            db.session.commit()
            logger.info(f"Successfully created new case: {case_number}")
            return jsonify({"status": "success", "case_number": case_number, "action": "created"})
        
    except Exception as e:
        logger.error(f"Error saving edited case: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/edit_case/<case_number>', methods=['POST'])
@teacher_required
def edit_case(case_number):
    """Edit existing case"""
    try:
        data = request.get_json()
        edited_data = data.get('edited_data')
        
        if not edited_data:
            return jsonify({"error": "No edited data provided"}), 400
        
        # Find existing case
        existing_case = PatientCase.query.filter_by(case_number=case_number).first()
        if not existing_case:
            return jsonify({"error": f"Case {case_number} not found"}), 404
        
        # Update case data
        existing_case.specialty = edited_data.get('specialty', existing_case.specialty)
        existing_case.patient_info = edited_data.get('patient_info', existing_case.patient_info)
        existing_case.symptoms = edited_data.get('symptoms', existing_case.symptoms)
        existing_case.evaluation_checklist = edited_data.get('evaluation_checklist', existing_case.evaluation_checklist)
        existing_case.diagnosis = edited_data.get('diagnosis', existing_case.diagnosis)
        existing_case.differential_diagnosis = edited_data.get('differential_diagnosis', existing_case.differential_diagnosis)
        existing_case.directives = edited_data.get('directives', existing_case.directives)
        existing_case.consultation_time = edited_data.get('consultation_time', existing_case.consultation_time)
        existing_case.additional_notes = edited_data.get('additional_notes', existing_case.additional_notes)
        existing_case.custom_sections = edited_data.get('custom_sections', existing_case.custom_sections)
        existing_case.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logger.info(f"Successfully updated case: {case_number}")
        return jsonify({"status": "success", "case_number": case_number})
        
    except Exception as e:
        logger.error(f"Error editing case {case_number}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/delete_case/<case_number>', methods=['DELETE'])
@teacher_required
def delete_case(case_number):
    """Delete a case"""
    try:
        existing_case = PatientCase.query.filter_by(case_number=case_number).first()
        if not existing_case:
            return jsonify({"error": f"Case {case_number} not found"}), 404
        
        # Delete associated images using case_number (not case_id)
        from models import CaseImage
        case_images = CaseImage.query.filter_by(case_number=case_number).all()
        for img in case_images:
            # Delete physical file
            if img.path.startswith('/static/'):
                file_path = os.path.join(current_app.static_folder, img.path[8:])  # Remove '/static/'
                if os.path.exists(file_path):
                    os.remove(file_path)
            db.session.delete(img)
        
        # Delete case
        db.session.delete(existing_case)
        db.session.commit()
        
        logger.info(f"Successfully deleted case: {case_number}")
        return jsonify({"success": True, "message": f"Case {case_number} deleted successfully"})
        
    except Exception as e:
        logger.error(f"Error deleting case {case_number}: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/stations')
@teacher_required
def teacher_stations():
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
            # Get completion count and average score
            performances = StudentPerformance.query.filter_by(case_number=case.case_number).all()
            completion_count = len(performances)
            average_score = sum(perf.percentage_score for perf in performances) / len(performances) if performances else 0
            
            stations.append({
                'case_number': case.case_number,
                'specialty': case.specialty,
                'consultation_time': case.consultation_time,
                'created_at': case.created_at.strftime('%d/%m/%Y'),
                'updated_at': case.updated_at.strftime('%d/%m/%Y') if case.updated_at else case.created_at.strftime('%d/%m/%Y'),
                'completion_count': completion_count,
                'average_score': round(average_score)
            })
        
        return jsonify({
            'stations': stations,
            'total': len(stations)
        })
        
    except Exception as e:
        logger.error(f"Error getting teacher stations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/students/performance')
@teacher_required
def teacher_students_performance():
    """Get student performance data for teacher"""
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
        
        student_data = []
        for student in students:
            # Get student performances
            performances = StudentPerformance.query.filter_by(student_id=student.id).all()
            
            total_workouts = len(performances)
            unique_stations = len(set(perf.case_number for perf in performances))
            average_score = sum(perf.percentage_score for perf in performances) / len(performances) if performances else 0
            
            student_data.append({
                'student_id': student.id,
                'student_code': student.student_code,
                'name': student.name,
                'total_workouts': total_workouts,
                'unique_stations': unique_stations,
                'average_score': round(average_score),
                'last_login': student.last_login.strftime('%d/%m/%Y %H:%M') if student.last_login else 'Jamais'
            })
        
        return jsonify({
            'students': student_data,
            'total': len(student_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting student performance: {str(e)}")
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/students/<int:student_id>/detailed_performance')
@teacher_required
def teacher_student_detailed_performance(student_id):
    """Get detailed performance for a specific student"""
    try:
        student = Student.query.get_or_404(student_id)
        
        # Get student performances
        performances = StudentPerformance.query.filter_by(student_id=student_id)\
            .order_by(StudentPerformance.completed_at.desc()).all()
        
        # Calculate summary stats
        total_workouts = len(performances)
        unique_stations = len(set(perf.case_number for perf in performances))
        average_score = sum(perf.percentage_score for perf in performances) / len(performances) if performances else 0
        
        # Format detailed performances
        performance_data = []
        for perf in performances:
            case = PatientCase.query.filter_by(case_number=perf.case_number).first()
            performance_data.append({
                'id': perf.id,
                'case_number': perf.case_number,
                'specialty': case.specialty if case else 'Unknown',
                'score': perf.percentage_score,
                'points_earned': perf.points_earned or 0,
                'points_total': perf.points_total or 0,
                'status': perf.get_performance_status(),
                'completed_at': perf.completed_at.strftime('%d/%m/%Y %H:%M'),
                'consultation_duration': f"{perf.consultation_duration // 60}:{perf.consultation_duration % 60:02d}" if perf.consultation_duration else "N/A"
            })
        
        return jsonify({
            'student': {
                'total_workouts': total_workouts,
                'unique_stations': unique_stations,
                'average_score': round(average_score)
            },
            'performances': performance_data
        })
        
    except Exception as e:
        logger.error(f"Error getting detailed student performance: {str(e)}")
        return jsonify({"error": str(e)}), 500

@teacher_bp.route('/download_student_report/<int:performance_id>')
@teacher_required
def teacher_download_student_report(performance_id):
    """Download student performance report (teacher version)"""
    try:
        performance = db.session.get(StudentPerformance, performance_id)
        
        if not performance:
            logger.error(f"Performance record not found for ID: {performance_id}")
            return jsonify({"error": "Rapport de performance non trouvé"}), 404

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
        
        temp_dir = tempfile.gettempdir()
        return send_from_directory(
            temp_dir,
            pdf_filename,
            as_attachment=True,
            download_name=f"teacher_student_report_{performance.student.student_code}_case_{case_number}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        logger.error(f"Error generating teacher student report PDF for performance ID {performance_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Erreur lors de la génération du rapport PDF"}), 500
    
@teacher_bp.route('/create_case_manual', methods=['POST'])
@teacher_required
def create_case_manual():
    """Create a case manually from JSON data (for API/testing purposes)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        case_number = data.get('case_number')
        specialty = data.get('specialty')
        
        if not case_number or not specialty:
            return jsonify({"error": "Case number and specialty are required"}), 400
        
        # Check if case already exists
        existing_case = PatientCase.query.filter_by(case_number=case_number).first()
        if existing_case:
            return jsonify({"error": f"Case {case_number} already exists"}), 400
        
        # Create new case from JSON data
        new_case = PatientCase(
            case_number=case_number,
            specialty=specialty,
            patient_info_json=json.dumps(data.get('patient_info', {}), ensure_ascii=False),
            symptoms_json=json.dumps(data.get('symptoms', []), ensure_ascii=False),
            evaluation_checklist_json=json.dumps(data.get('evaluation_checklist', []), ensure_ascii=False),
            diagnosis=data.get('diagnosis', ''),
            differential_diagnosis_json=json.dumps(data.get('differential_diagnosis', []), ensure_ascii=False) if data.get('differential_diagnosis') else None,
            directives=data.get('directives', ''),
            consultation_time=data.get('consultation_time', 10),
            additional_notes=data.get('additional_notes', ''),
            custom_sections_json=json.dumps(data.get('custom_sections', []), ensure_ascii=False)
        )
        
        db.session.add(new_case)
        db.session.commit()
        
        logger.info(f"Successfully created case via API: {case_number}")
        
        return jsonify({
            "status": "success",
            "case_number": case_number,
            "specialty": specialty,
            "message": f"Case {case_number} created successfully"
        })
        
    except Exception as e:
        logger.error(f"Error creating case via API: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500