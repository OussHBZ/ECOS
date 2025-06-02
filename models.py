from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class Student(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(4), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def get_id(self):
        return f"student_{self.id}"

class TeacherAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(20), unique=True, nullable=False)
    last_used = db.Column(db.DateTime)

# NEW: Add Case model for database synchronization
class PatientCase(db.Model):
    __tablename__ = 'patient_case1'
    
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(50), unique=True, nullable=False)
    specialty = db.Column(db.String(100))
    patient_info_json = db.Column(db.Text)
    symptoms_json = db.Column(db.Text)
    evaluation_checklist_json = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    differential_diagnosis_json = db.Column(db.Text)
    directives = db.Column(db.Text)
    consultation_time = db.Column(db.Integer, default=10)
    additional_notes = db.Column(db.Text)
    lab_results = db.Column(db.Text)
    custom_sections_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<PatientCase {self.case_number}>'
    
    @classmethod
    def from_json_data(cls, case_data):
        """Create a PatientCase instance from JSON case data"""
        
        # Extract patient info
        patient_info = case_data.get('patient_info', {})
        
        # Handle differential diagnosis - convert to JSON if it's a list or string
        diff_diagnosis = case_data.get('differential_diagnosis')
        if isinstance(diff_diagnosis, list):
            diff_diagnosis_json = json.dumps(diff_diagnosis, ensure_ascii=False)
        elif isinstance(diff_diagnosis, str) and diff_diagnosis.strip():
            # If it's a string, split by commas and create a list
            diff_list = [item.strip() for item in diff_diagnosis.split(',') if item.strip()]
            diff_diagnosis_json = json.dumps(diff_list, ensure_ascii=False) if diff_list else None
        else:
            diff_diagnosis_json = None
        
        return cls(
            case_number=str(case_data.get('case_number', '')),
            specialty=case_data.get('specialty', ''),
            patient_info_json=json.dumps(patient_info, ensure_ascii=False) if patient_info else None,
            symptoms_json=json.dumps(case_data.get('symptoms', []), ensure_ascii=False),
            evaluation_checklist_json=json.dumps(case_data.get('evaluation_checklist', []), ensure_ascii=False),
            diagnosis=case_data.get('diagnosis', ''),
            differential_diagnosis_json=diff_diagnosis_json,
            directives=case_data.get('directives', ''),
            consultation_time=case_data.get('consultation_time', 10),
            additional_notes=case_data.get('additional_notes', ''),
            lab_results=patient_info.get('lab_results', ''),
            custom_sections_json=json.dumps(case_data.get('custom_sections', []), ensure_ascii=False)
        )
    
    def update_from_json_data(self, case_data):
        """Update existing PatientCase instance from JSON case data"""
        
        # Extract patient info
        patient_info = case_data.get('patient_info', {})
        
        # Handle differential diagnosis
        diff_diagnosis = case_data.get('differential_diagnosis')
        if isinstance(diff_diagnosis, list):
            diff_diagnosis_json = json.dumps(diff_diagnosis, ensure_ascii=False)
        elif isinstance(diff_diagnosis, str) and diff_diagnosis.strip():
            diff_list = [item.strip() for item in diff_diagnosis.split(',') if item.strip()]
            diff_diagnosis_json = json.dumps(diff_list, ensure_ascii=False) if diff_list else None
        else:
            diff_diagnosis_json = None
        
        # Update all fields
        self.specialty = case_data.get('specialty', '')
        self.patient_info_json = json.dumps(patient_info, ensure_ascii=False) if patient_info else None
        self.symptoms_json = json.dumps(case_data.get('symptoms', []), ensure_ascii=False)
        self.evaluation_checklist_json = json.dumps(case_data.get('evaluation_checklist', []), ensure_ascii=False)
        self.diagnosis = case_data.get('diagnosis', '')
        self.differential_diagnosis_json = diff_diagnosis_json
        self.directives = case_data.get('directives', '')
        self.consultation_time = case_data.get('consultation_time', 10)
        self.additional_notes = case_data.get('additional_notes', '')
        self.lab_results = patient_info.get('lab_results', '')
        self.custom_sections_json = json.dumps(case_data.get('custom_sections', []), ensure_ascii=False)
        self.updated_at = datetime.utcnow()
    
    def to_json_data(self):
        """Convert PatientCase instance to JSON case data format"""
        try:
            patient_info = json.loads(self.patient_info_json) if self.patient_info_json else {}
            symptoms = json.loads(self.symptoms_json) if self.symptoms_json else []
            evaluation_checklist = json.loads(self.evaluation_checklist_json) if self.evaluation_checklist_json else []
            custom_sections = json.loads(self.custom_sections_json) if self.custom_sections_json else []
            
            # Handle differential diagnosis
            differential_diagnosis = None
            if self.differential_diagnosis_json:
                try:
                    differential_diagnosis = json.loads(self.differential_diagnosis_json)
                except:
                    differential_diagnosis = self.differential_diagnosis_json
            
            # Add lab results to patient info if available
            if self.lab_results:
                patient_info['lab_results'] = self.lab_results
            
            case_data = {
                'case_number': self.case_number,
                'specialty': self.specialty,
                'patient_info': patient_info,
                'symptoms': symptoms,
                'evaluation_checklist': evaluation_checklist,
                'consultation_time': self.consultation_time,
                'custom_sections': custom_sections,
                'images': []  # Images are stored separately in JSON files
            }
            
            # Add optional fields only if they have values
            if self.diagnosis:
                case_data['diagnosis'] = self.diagnosis
            if differential_diagnosis:
                case_data['differential_diagnosis'] = differential_diagnosis
            if self.directives:
                case_data['directives'] = self.directives
            if self.additional_notes:
                case_data['additional_notes'] = self.additional_notes
            
            return case_data
            
        except Exception as e:
            # Return minimal data if JSON parsing fails
            return {
                'case_number': self.case_number,
                'specialty': self.specialty or '',
                'patient_info': {},
                'symptoms': [],
                'evaluation_checklist': [],
                'consultation_time': self.consultation_time or 10,
                'custom_sections': [],
                'images': []
            }