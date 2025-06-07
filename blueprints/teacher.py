from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from models import db, PatientCase, StudentPerformance, Student
from auth import teacher_required
import logging
import os
from werkzeug.utils import secure_filename
import json

teacher_bp = Blueprint('teacher', __name__)
logger = logging.getLogger(__name__)

@teacher_bp.route('/')
@teacher_required
def teacher_interface():
    """Render the teacher interface"""
    # Get list of existing cases
    from flask import current_app
    get_case_metadata = current_app.injected_functions['get_case_metadata']
    cases = get_case_metadata()
    return render_template('teacher.html', cases=cases)

@teacher_bp.route('/process_case_file', methods=['POST'])
@teacher_required
def process_case_file():
    """Process uploaded case file and extract OSCE data with enhanced multi-image support"""
    from flask import current_app
    document_agent = current_app.injected_functions['document_agent']
    app = current_app._get_current_object()

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
        document_agent.save_case_data(
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

# ... (move other teacher routes here)
