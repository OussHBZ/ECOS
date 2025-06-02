import os
import re
import json
import logging
import docx2txt
import PyPDF2
import shutil
from PIL import Image
from io import BytesIO
from langchain_core.messages import HumanMessage
from models import db, PatientCase

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentExtractionAgent:
    """Agent-based document processor that extracts structured information from medical case files"""
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.supported_extensions = ['.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png']
        # Create images directory if it doesn't exist
        self.images_dir = os.path.join('static', 'images', 'cases')
        os.makedirs(self.images_dir, exist_ok=True)
        # Initialize state
        self.state = {}
    
    def _extract_directives(self, text):
        """Extract directives from text using regex patterns"""
        import re
        
        # Define patterns to match directive sections
        directive_patterns = [
            r"Directives\s*:(.*?)(?:\n\s*\n|$)",
            r"Instructions\s*:(.*?)(?:\n\s*\n|$)",
            r"Consignes\s*:(.*?)(?:\n\s*\n|$)",
            r"Type de station(.*?)(?=\n\s*Script|\n\s*Grille|\n\s*Directives|$)"
        ]
        
        # Try each pattern
        for pattern in directive_patterns:
            matches = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                directive_text = matches.group(1).strip()
                return directive_text
        
        return None
        
    def process_file(self, file_path, file_type, case_number=None, specialty=None):
        """Main entry point to process a file with the agent"""
        logger.info(f"Agent processing file: {file_path} of type {file_type}")
        
        # Initialize state for this run
        self.state = {
            "file_path": file_path,
            "file_type": file_type,
            "case_number": case_number,
            "specialty": specialty,  # Store specialty in the state
            "raw_text": "",
            "images": [],
            "extracted_data": {},
            "validation_issues": [],
            "extraction_complete": False,
            "validation_complete": False
        }
        
        # Run the agent's main loop
        self._run_extraction_loop()
        
        # Return the final extracted data
        return self.state["extracted_data"]
    
    def _run_extraction_loop(self):
        """Main agent loop that coordinates the extraction process"""
        try:
            # Step 1: Extract content based on file type
            self._extract_content()
            
            # Step 2: Process the content with LLM if available
            if self.llm_client:
                self._extract_structured_data_with_llm()
            else:
                self._extract_structured_data_with_patterns()
            
            # Step 3: Validate the extracted data
            self._validate_extraction()
            
            logger.info("Document extraction process completed successfully")
            
        except Exception as e:
            logger.error(f"Error during extraction process: {str(e)}")
            # Set a fallback result if extraction fails
            if not self.state.get("extracted_data"):
                self.state["extracted_data"] = {
                    "patient_info": {},
                    "symptoms": [],
                    "evaluation_checklist": [],
                    "images": self.state.get("images", [])
                }
    
    def _extract_content(self):
        """Extract raw content based on file type"""
        file_type = self.state["file_type"]
        file_path = self.state["file_path"]
        
        try:
            if file_type in ['.pdf']:
                self._extract_from_pdf(file_path)
            elif file_type in ['.docx', '.doc']:
                self._extract_from_word(file_path)
            elif file_type in ['.jpg', '.jpeg', '.png']:
                self._process_image(file_path, self.state["case_number"])
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
                
            logger.info(f"Successfully extracted content from {file_path}")
            self.state["extraction_complete"] = True
            
        except Exception as e:
            logger.error(f"Error extracting content from {file_path}: {str(e)}")
            raise
    
    def _extract_from_pdf(self, file_path):
        """Extract text and images from PDF files"""
        logger.debug(f"Extracting from PDF: {file_path}")
        
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                
                # Extract text from each page
                text = ""
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() + "\n\n"
                
                self.state["raw_text"] = text
                
                # ADD THIS SECTION - Extract directives
                directives = self._extract_directives(text)
                if directives:
                    self.state["directives"] = directives

                # Extract images if present
                case_number = self.state["case_number"]
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    
                    if '/Resources' in page and '/XObject' in page['/Resources']:
                        xObject = page['/Resources']['/XObject']
                        for obj in xObject:
                            if xObject[obj]['/Subtype'] == '/Image':
                                # For PDFs with images, we'll just note that images exist
                                image_index = len(self.state["images"])
                                image_filename = f"case_{case_number}_image_{page_num}_{image_index}.jpg"
                                
                                # Add image reference to extracted data
                                self.state["images"].append({
                                    'filename': image_filename,
                                    'description': f"Image from page {page_num + 1}",
                                    'path': f"/static/images/cases/{image_filename}"
                                })
        except Exception as e:
            logger.error(f"Error in PDF extraction: {str(e)}")
            raise
    
    def _extract_from_word(self, file_path):
        """Extract text from Word documents"""
        logger.debug(f"Extracting from Word: {file_path}")
        
        try:
            # Extract text content
            text = docx2txt.process(file_path)
            self.state["raw_text"] = text
            
            directives = self._extract_directives(text)
            if directives:
                self.state["directives"] = directives

        except Exception as e:
            logger.error(f"Error in Word extraction: {str(e)}")
            raise
    
    def _process_image(self, file_path, case_number):
        """Process and store an image file"""
        logger.debug(f"Processing image: {file_path}")
        
        try:
            # Get original filename and create new name with case number
            original_filename = os.path.basename(file_path)
            image_ext = os.path.splitext(original_filename)[1].lower()
            new_filename = f"case_{case_number}_image_{os.path.splitext(original_filename)[0]}{image_ext}"
            
            # Define the path where the image will be stored
            new_image_path = os.path.join(self.images_dir, new_filename)
            
            # Copy the image to the static folder
            shutil.copy2(file_path, new_image_path)
            
            # Add image information to state
            web_path = f"/static/images/cases/{new_filename}"
            self.state["images"].append({
                'filename': new_filename,
                'description': "Medical image (radiography/scan)",
                'path': web_path
            })
            
            logger.info(f"Successfully processed and stored image: {new_filename}")
            
        except Exception as e:
            logger.error(f"Error processing image {file_path}: {str(e)}")
            raise
    
    def _extract_structured_data_with_llm(self):
        """Use LLM to extract structured data from the raw text"""
        logger.info("Extracting structured data using LLM")
        
        raw_text = self.state.get("raw_text", "")
        if not raw_text and not self.state.get("images"):
            logger.warning("No text or images to extract from")
            self.state["extracted_data"] = self._get_default_extracted_data() # Ensure extracted_data is initialized
            return
        
        prompt = self._create_extraction_prompt(raw_text)
        raw_llm_response_content = "" # Initialize to store raw LLM output

        try:
            response = self.llm_client.invoke([HumanMessage(content=prompt)])
            raw_llm_response_content = response.content # Store raw response
            
            # Attempt to extract JSON from the response
            json_match = re.search(r'```json\s*({.*?})\s*```', raw_llm_response_content, re.DOTALL)
            if not json_match: # If not wrapped in markdown, try finding a raw JSON object
                json_match = re.search(r'({.*})', raw_llm_response_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
                logger.debug(f"Attempting to parse JSON from LLM: {json_str[:500]}...") # Log start of JSON
                try:
                    data = json.loads(json_str)
                    logger.info("Successfully extracted structured data using LLM.")
                    self._finalize_extracted_data(data)
                    return # Success
                except json.JSONDecodeError as e:
                    logger.error(f"Initial JSON parsing error: {str(e)}. Original JSON string part: {json_str[:500]}")
                    logger.info("Attempting to clean and re-parse JSON...")
                    cleaned_json_str = self._clean_json_string(json_str)
                    try:
                        data = json.loads(cleaned_json_str)
                        logger.info("Successfully parsed JSON after cleaning.")
                        self._finalize_extracted_data(data)
                        return # Success after cleaning
                    except json.JSONDecodeError as e2:
                        logger.error(f"Failed to parse JSON even after cleaning: {str(e2)}. Cleaned JSON string part: {cleaned_json_str[:500]}")
                        # Log the full raw response if cleaning fails, for deeper inspection
                        logger.error(f"Full problematic raw LLM response was: {raw_llm_response_content}")
            else:
                logger.error("Failed to extract any JSON-like structure from LLM response.")
                logger.error(f"Full raw LLM response was: {raw_llm_response_content}")

        except Exception as e:
            logger.error(f"Error during LLM call or initial processing: {str(e)}")
            if raw_llm_response_content: # Log if we have it
                 logger.error(f"Full raw LLM response during error was: {raw_llm_response_content}")
        
        # Fallback if LLM extraction fails at any point
        logger.warning("Falling back to pattern-based extraction due to LLM JSON issues.")
        self._extract_structured_data_with_patterns()
    
    def _finalize_extracted_data(self, data_from_llm):
        """Helper to add images and set state after successful LLM extraction."""
        if "images" not in data_from_llm:
            data_from_llm["images"] = []
        # Ensure existing images from file processing are preserved/merged correctly
        # This logic might need refinement based on whether LLM can also identify images.
        # Assuming LLM doesn't list file-system images, so we add them.
        existing_images = self.state.get("images", [])
        llm_image_paths = {img.get("path") for img in data_from_llm["images"] if img.get("path")}
        for img in existing_images:
            if img.get("path") not in llm_image_paths:
                data_from_llm["images"].append(img)
        
        self.state["extracted_data"] = data_from_llm

    def _get_default_extracted_data(self):
        """Provides a default structure for extracted_data if extraction fails early."""
        return {
            'patient_info': {},
            'symptoms': [],
            'evaluation_checklist': [],
            'images': self.state.get("images", []), # Preserve any images processed so far
            'specialty': self.state.get("specialty", "Non spécifié"),
            'case_number': self.state.get("case_number", "unknown"),
            'diagnosis': None,
            'directives': None,
            'custom_sections': []
        }

    def _create_extraction_prompt(self, text):
        """Create a detailed prompt for the LLM to extract structured data"""
        case_number = self.state.get("case_number", "unknown")
        
        prompt = f"""
        En tant qu'expert médical, analysez ce document de cas OSCE {case_number} et extrayez les informations suivantes dans un format JSON structuré:

        1. Informations du patient (patient_info):
           - Nom (name)
           - Âge précis (age) - en nombre entier
           - Sexe (gender) - "Masculin" ou "Féminin"
           - Profession (occupation)
           - Autres informations médicales pertinentes (medical_history) - sous forme de liste

        2. Symptômes (symptoms):
           - Liste de tous les symptômes mentionnés
           - Incluez la durée et l'intensité si mentionnées

        3. Grille d'évaluation (evaluation_checklist):
           - Chaque élément avec:
             * description: description exacte de ce que l'étudiant doit faire
             * points: nombre de points (par défaut 1 si non spécifié)
             * category: catégorie (anamnèse, examen physique, communication, diagnostic, etc.)
             * completed: false (toujours initialisé à false)

        4. Diagnostic (diagnosis):
           - Le diagnostic correct pour ce cas

        5. Directives (directives):
           - Instructions pour l'étudiant sur comment procéder avec le cas
           - Durée de consultation, tâches à accomplir, etc.

        6. Sections personnalisées (custom_sections):
           - Une liste d'objets avec title et content pour toute information supplémentaire

        Voici le texte du cas:
        {text}

        Répondez avec UNIQUEMENT un objet JSON valide sans aucun texte supplémentaire.
        """
        
        return prompt
    
    def _extract_structured_data_with_patterns(self):
        """Extract structured data using regex patterns as fallback"""
        logger.info("Extracting structured data using pattern matching")
        
        text = self.state.get("raw_text", "")
        
        # Extract patient info
        patient_info = self._extract_patient_info(text)
        
        # Ensure age is an integer if present
        if 'age' in patient_info and patient_info['age']:
            try:
                patient_info['age'] = int(patient_info['age'])
            except (ValueError, TypeError):
                # If conversion fails, keep the original value
                pass
        
        # Ensure gender is properly set
        if 'gender' in patient_info and patient_info['gender']:
            # Normalize gender values
            gender = patient_info['gender'].strip()
            if gender.lower() in ['m', 'homme', 'masculin', 'male']:
                patient_info['gender'] = 'Masculin'
            elif gender.lower() in ['f', 'femme', 'féminin', 'female']:
                patient_info['gender'] = 'Féminin'
        
        extracted_data = {
            'patient_info': patient_info,
            'symptoms': self._extract_symptoms(text) or [],  # Ensure we have at least an empty list
            'evaluation_checklist': self._extract_evaluation_checklist(text) or [],
            'images': self.state.get("images", []),
            'specialty': self.state.get("specialty", "Non spécifié")
        }
        if "directives" in self.state:
            extracted_data['directives'] = self.state["directives"]
        
        self.state["extracted_data"] = extracted_data
    
    def _extract_patient_info(self, text):
        """Extract patient information from text using patterns"""
        patient_info = {}
        
        # Look for age
        age_match = re.search(r'patient\s+de\s+(\d+)\s+ans', text, re.IGNORECASE)
        if age_match:
            patient_info['age'] = int(age_match.group(1))
        
        # Look for gender indicators
        if re.search(r'\b(il|homme|monsieur|m\.)\b', text, re.IGNORECASE):
            patient_info['gender'] = 'Masculin'
        elif re.search(r'\b(elle|femme|madame|mme)\b', text, re.IGNORECASE):
            patient_info['gender'] = 'Féminin'
        
        # Look for name
        name_match = re.search(r'vous\s+(?:vous\s+)?appel(?:ez|le[sz])\s+([A-Za-zÀ-ÿ]+)', text, re.IGNORECASE)
        if name_match:
            patient_info['name'] = name_match.group(1)
        
        return patient_info
    
    def _extract_symptoms(self, text):
        """Extract symptoms from text using patterns"""
        symptoms = []
        
        # Common symptom-related phrases in French
        symptom_indicators = [
            r'souffr(?:e|ez) de (.*?)\.',
            r'présent(?:e|ez) (.*?) depuis',
            r'(douleur|fatigue|fièvre|toux|nausée|vomissement|diarrhée|constipation|maux|difficultés|problèmes) (.*?)\.',
            r'(?:vous vous|se) plaign(?:ez|t) de (.*?)\.'
        ]
        
        for pattern in symptom_indicators:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) > 0:
                    symptom_text = ' '.join(match.groups()).strip()
                    if symptom_text and len(symptom_text) > 3:  # Avoid very short matches
                        symptoms.append(symptom_text)
        
        return list(set(symptoms))  # Remove duplicates
    
    def _extract_evaluation_checklist(self, text):
        """Extract evaluation checklist items from text using patterns"""
        checklist = []
        
        # Look for common evaluation section headers
        section_headers = [
            r"Grille\s+d['']évaluation",
            r"Critères\s+d['']évaluation",
            r"Évaluation\s+de\s+la\s+consultation",
            r"Items\s+à\s+vérifier",
            r"Liste\s+de\s+contrôle",
            r"Checklist",
            r"Barème",
            r"Notation",
            r"Points\s+à\s+évaluer"
        ]
        
        section_pattern = '|'.join(section_headers)
        eval_section_match = re.search(f'({section_pattern}).*?(?=\n\n\n|\n\n[A-Z]|\Z)', text, re.DOTALL | re.IGNORECASE)
        
        if eval_section_match:
            eval_section = eval_section_match.group(0)
            logger.debug(f"Found evaluation section: {eval_section[:100]}...")
            
            # Look for numbered or bulleted items with comprehensive patterns
            item_patterns = [
                # Numbered items (1., 1), etc.)
                r'(?:\d+\s*[-.):])\s*(.*?)(?=\n\s*\d+\s*[-.):]\s*|\n\n|\Z)',
                
                # Bulleted items (*, •, -, etc.)
                r'(?:[\*\•\-\–\■\□\▪]\s*)(.*?)(?=\n\s*[\*\•\-\–\■\□\▪]\s*|\n\n|\Z)',
                
                # Lettered items (a., A), etc.)
                r'(?:[A-Za-z]\s*[-.):])\s*(.*?)(?=\n\s*[A-Za-z]\s*[-.):]\s*|\n\n|\Z)',
                
                # Items with explicit point values
                r'([^\n:]+?)(?:\s*[:]\s*)(\d+)(?:\s*points?)(?=\n|\Z)',
            ]
            
            for pattern in item_patterns:
                item_matches = re.finditer(pattern, eval_section, re.DOTALL)
                
                for match in item_matches:
                    # Get the full match and handle different patterns
                    if len(match.groups()) == 1:
                        item_text = match.group(1).strip()
                        
                        # Try to extract points if available within the text
                        points_match = re.search(r'(\d+)\s*points?', item_text, re.IGNORECASE)
                        points = int(points_match.group(1)) if points_match else 1
                        
                        # Remove the points text from the description
                        description = re.sub(r'\d+\s*points?', '', item_text).strip()
                        
                    elif len(match.groups()) == 2:
                        # This is for patterns with explicit description and points
                        description = match.group(1).strip()
                        try:
                            points = int(match.group(2))
                        except (ValueError, TypeError):
                            points = 1
                            description = f"{description}: {match.group(2)}"
                    else:
                        continue
                    
                    # Only add if we have a meaningful description
                    if description and len(description) > 3:  # Avoid very short matches
                        # Determine category based on keywords
                        category = self._determine_checklist_category(description)
                        
                        # Check if this item is not already in the list (avoid duplicates)
                        if not any(item['description'].lower() == description.lower() for item in checklist):
                            checklist.append({
                                'description': description,
                                'points': points,
                                'category': category,
                                'completed': False  # Default to not completed
                            })
        
        # If we found too few items, apply a fallback approach
        if len(checklist) < 3:
            # Look for lines with medical examination keywords
            fallback_checklist = self._fallback_checklist_extraction(text)
            checklist.extend(fallback_checklist)
        
        return checklist
    
    def _determine_checklist_category(self, description):
        """Determine the category of a checklist item based on keywords"""
        description_lower = description.lower()
        
        if any(kw in description_lower for kw in ['demande', 'question', 'interroge', 'anamnèse', 'antécédent']):
            return 'Anamnèse'
        elif any(kw in description_lower for kw in ['examen', 'ausculte', 'palpe', 'percute', 'inspecte', 'mesure']):
            return 'Examen physique'
        elif any(kw in description_lower for kw in ['communique', 'explique', 'informe', 'rassure', 'écoute']):
            return 'Communication'
        elif any(kw in description_lower for kw in ['diagnostic', 'diagnose', 'diagnostic différentiel']):
            return 'Diagnostic'
        elif any(kw in description_lower for kw in ['traitement', 'prescription', 'ordonnance', 'thérapie']):
            return 'Prise en charge'
        else:
            return 'Général'
    
    def _fallback_checklist_extraction(self, text):
        """Fallback method to extract checklist items when structured format isn't found"""
        potential_items = []
        
        # Look for lines with specific medical examination keywords
        exam_keywords = [
            r'examin[eé]', r'demand[eé]', r'question[né]', r'explor[eé]', r'discut[eé]',
            r'vérifi[eé]', r'évaluat[eé]', r'effectu[eé]', r'réalis[eé]',
            r'anamnès[ei]', r'antécédent', r'symptôme', r'diagnostic', r'traitement'
        ]
        
        keyword_pattern = '|'.join(exam_keywords)
        
        # Find lines with these keywords that might be checklist items
        for line in text.split('\n'):
            line = line.strip()
            if re.search(keyword_pattern, line, re.IGNORECASE) and 10 < len(line) < 200:
                # Determine category based on keywords
                category = self._determine_checklist_category(line)
                
                potential_items.append({
                    'description': line,
                    'points': 1,
                    'category': category,
                    'completed': False
                })
        
        # Return limited number of items from fallback
        return potential_items[:15]  # Limit to 15 items
    
    def _validate_extraction(self):
        """Validate the extracted data and identify issues"""
        extracted_data = self.state.get("extracted_data", {})
        issues = []
        
        # Check patient info
        patient_info = extracted_data.get('patient_info', {})
        
        # Check age - consider both None and 0 as invalid, but accept any other value
        age_value = patient_info.get('age')
        if age_value is None or age_value == 0 or age_value == '':
            issues.append("L'âge du patient est manquant ou non valide")
        
        # Check gender - must be a non-empty string
        gender_value = patient_info.get('gender')
        if not gender_value or not isinstance(gender_value, str) or gender_value.strip() == '':
            issues.append("Le sexe du patient est manquant")
        
        # Check symptoms - must have at least one non-empty symptom
        symptoms = extracted_data.get('symptoms', [])
        if not symptoms or all(not symptom for symptom in symptoms):
            issues.append("Aucun symptôme n'a été détecté")
        
        # Check evaluation checklist - must have at least 3 items
        checklist = extracted_data.get('evaluation_checklist', [])
        if not checklist or len(checklist) < 3:
            issues.append("Grille d'évaluation incomplète ou manquante")
        
        # Store the validation results
        self.state["validation_issues"] = issues
        self.state["validation_complete"] = True
        
        logger.info(f"Validation completed with {len(issues)} issues")
        return issues
    
    def _clean_json_string(self, json_str):
        """Clean and fix common JSON formatting issues from LLM output."""
        logger.debug(f"Attempting to clean JSON string (original start): {json_str[:200]}")
        
        # Remove common LLM artifacts like ```json and ```
        json_str = re.sub(r'^```json\s*', '', json_str, flags=re.IGNORECASE)
        json_str = re.sub(r'\s*```$', '', json_str)
        json_str = json_str.strip()

        # Replace Pythonic None, True, False with JSON null, true, false
        json_str = re.sub(r'\bNone\b', 'null', json_str)
        json_str = re.sub(r'\bTrue\b', 'true', json_str)
        json_str = re.sub(r'\bFalse\b', 'false', json_str)
        
        # Replace single quotes with double quotes for keys and string values
        # Be careful not to replace single quotes within already double-quoted strings
        json_str = re.sub(r"(?<![\\])(?<!['\w])'(?!['\s])", '"', json_str) # Start of string/key
        json_str = re.sub(r"(?<![\\])'(?=['\s,{}\]:\)])", '"', json_str) # End of string/key

        # Remove trailing commas from objects and arrays
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        
        # Add quotes to unquoted keys (basic attempt)
        json_str = re.sub(r'([{,])\s*([a-zA-Z0-9_]+)\s*:', r'\1"\2":', json_str)

        # Remove comments (if LLM adds them)
        json_str = re.sub(r'//.*?($|\n)', '\n', json_str) # Remove // comments
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL) # Remove /* */ comments
        
        logger.debug(f"Cleaned JSON string (attempted start): {json_str[:200]}")
        return json_str
    
    def save_case_data(self, case_number, specialty, extracted_data):
        """Save extracted case data to the database instead of JSON file."""
        # Check if case already exists
        case = PatientCase.query.filter_by(case_number=case_number).first()
        if not case:
            case = PatientCase(case_number=case_number)
            db.session.add(case)
        # Set/Update fields
        case.specialty = specialty or extracted_data.get("specialty", "Non spécifié")
        case.patient_info = extracted_data.get("patient_info", {})
        case.symptoms = extracted_data.get("symptoms", [])
        case.evaluation_checklist = extracted_data.get("evaluation_checklist", [])
        case.diagnosis = extracted_data.get("diagnosis", "")
        case.directives = extracted_data.get("directives", "")
        case.consultation_time = extracted_data.get("consultation_time", 10)
        case.custom_sections = extracted_data.get("custom_sections", [])
        # Save images
        db.session.flush()  # Ensure case.id is available
        db.session.commit()
        return case

    def get_validation_issues(self):
        """Get the validation issues found in the extracted data"""
        return self.state.get("validation_issues", [])
    
    def process_image(self, image_path, case_number):
        """Process an image file (public method for direct image processing)"""
        logger.debug(f"Processing standalone image file: {image_path}")
        
        # Initialize minimal state for image processing
        self.state = {
            "file_path": image_path,
            "file_type": os.path.splitext(image_path)[1].lower(),
            "case_number": case_number,
            "images": []
        }
        
        # Process the image
        self._process_image(image_path, case_number)
        
        # Make a copy of the state images to avoid shared references
        result = {"images": self.state["images"].copy()}
        
        logger.debug(f"Image processing result: {result}")
        return result
    
    def process_multiple_images(self, image_paths, case_number):
        """Process multiple image files at once"""
        logger.debug(f"Processing {len(image_paths)} image files for case {case_number}")
        
        # Initialize minimal state for image processing
        self.state = {
            "case_number": case_number,
            "images": []
        }
        
        # Process each image
        for image_path in image_paths:
            try:
                # Get original filename and create new name with case number
                original_filename = os.path.basename(image_path)
                image_ext = os.path.splitext(original_filename)[1].lower()
                new_filename = f"case_{case_number}_image_{os.path.splitext(original_filename)[0]}{image_ext}"
                
                # Define the path where the image will be stored
                new_image_path = os.path.join(self.images_dir, new_filename)
                
                # Copy the image to the static folder
                shutil.copy2(image_path, new_image_path)
                
                # Add image information to state
                web_path = f"/static/images/cases/{new_filename}"
                self.state["images"].append({
                    'filename': new_filename,
                    'description': f"Image médicale {len(self.state['images']) + 1}",
                    'path': web_path
                })
                
                logger.info(f"Successfully processed and stored image: {new_filename}")
                
            except Exception as e:
                logger.error(f"Error processing image {image_path}: {str(e)}")
                # Continue with other images even if one fails
        
        # Make a copy of the state images to avoid shared references
        result = {"images": self.state["images"].copy()}
        
        logger.debug(f"Multiple image processing result: {result}")
        return result