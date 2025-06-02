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
    access_code = db.Column(db.String(20), unique=True, nullable=False) # Consider encrypting this
    last_used = db.Column(db.DateTime)

# New Models
class PatientCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(50), unique=True, nullable=False)
    specialty = db.Column(db.String(100), nullable=False, default="Non spécifié")
    
    # Patient Info (stored as JSON)
 
    patient_info_json = db.Column(db.Text, nullable=True) 
    


    symptoms_json = db.Column(db.Text, nullable=True) # Store as JSON list of strings
    evaluation_checklist_json = db.Column(db.Text, nullable=True) # Store as JSON list of objects
    diagnosis = db.Column(db.Text, nullable=True)
    differential_diagnosis_json = db.Column(db.Text, nullable=True) # Store as JSON list of strings
    directives = db.Column(db.Text, nullable=True)
    consultation_time = db.Column(db.Integer, default=10)
    additional_notes = db.Column(db.Text, nullable=True)
    lab_results = db.Column(db.Text, nullable=True)
    custom_sections_json = db.Column(db.Text, nullable=True) # Store as JSON list of objects

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to images
    images = db.relationship('MedicalImage', backref='patient_case', lazy=True, cascade="all, delete-orphan")

    # Helper methods for JSON fields (if using JSON storage for patient_info, symptoms etc.)
    @property
    def patient_info(self):
        if self.patient_info_json:
            return json.loads(self.patient_info_json)
        return {}

    @patient_info.setter
    def patient_info(self, value):
        self.patient_info_json = json.dumps(value) if value else None
        
    @property
    def symptoms(self):
        if self.symptoms_json:
            return json.loads(self.symptoms_json)
        return []

    @symptoms.setter
    def symptoms(self, value):
        self.symptoms_json = json.dumps(value) if value else None

    @property
    def evaluation_checklist(self):
        if self.evaluation_checklist_json:
            return json.loads(self.evaluation_checklist_json)
        return []

    @evaluation_checklist.setter
    def evaluation_checklist(self, value):
        self.evaluation_checklist_json = json.dumps(value) if value else None
        
    @property
    def differential_diagnosis(self):
        if self.differential_diagnosis_json:
            return json.loads(self.differential_diagnosis_json)
        return []

    @differential_diagnosis.setter
    def differential_diagnosis(self, value):
        self.differential_diagnosis_json = json.dumps(value) if value else None

    @property
    def custom_sections(self):
        if self.custom_sections_json:
            return json.loads(self.custom_sections_json)
        return []

    @custom_sections.setter
    def custom_sections(self, value):
        self.custom_sections_json = json.dumps(value) if value else None


class MedicalImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('patient_case.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(512), nullable=False) # Web accessible path e.g., /static/images/cases/case_123_image.jpg
    description = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

