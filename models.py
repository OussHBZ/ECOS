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
    
    # Relationships
    performances = db.relationship('StudentPerformance', backref='student', lazy=True, cascade='all, delete-orphan')
    session_participants = db.relationship('SessionParticipant', backref='student', lazy=True, cascade='all, delete-orphan')
    
    def get_id(self):
        return f"student_{self.id}"
    
    def get_total_workouts(self):
        """Get total number of completed consultations"""
        return StudentPerformance.query.filter_by(student_id=self.id).count()
    
    def get_unique_stations_played(self):
        """Get number of unique stations/cases played"""
        return db.session.query(StudentPerformance.case_number).filter_by(student_id=self.id).distinct().count()
    
    def get_average_score(self):
        """Get average percentage score across all performances"""
        performances = StudentPerformance.query.filter_by(student_id=self.id).all()
        if not performances:
            return 0
        total_score = sum(p.percentage_score for p in performances)
        return round(total_score / len(performances), 1)
    
    def get_recent_performances(self, limit=5):
        """Get recent performances"""
        return StudentPerformance.query.filter_by(student_id=self.id)\
            .order_by(StudentPerformance.completed_at.desc()).limit(limit).all()

class TeacherAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(20), unique=True, nullable=False)
    last_used = db.Column(db.DateTime)

class AdminAccess(db.Model):
    """Model for Administrator access tracking"""
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(20), unique=True, nullable=False)
    last_used = db.Column(db.DateTime)

class OSCESession(db.Model):
    """Model for OSCE examination sessions"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(50))  # Who created the session
    status = db.Column(db.String(20), default='scheduled')  # scheduled, active, completed, cancelled
    
    # Relationships
    participants = db.relationship('SessionParticipant', backref='session', lazy=True, cascade='all, delete-orphan')
    station_assignments = db.relationship('SessionStationAssignment', backref='session', lazy=True, cascade='all, delete-orphan')
    
    def get_participant_count(self):
        """Get number of participants in this session"""
        return len(self.participants)
    
    def get_assigned_stations_count(self):
        """Get number of stations assigned to this session"""
        return len(self.station_assignments)
    
    def get_status_display(self):
        """Get display-friendly status"""
        status_map = {
            'scheduled': 'Programmé',
            'active': 'En cours',
            'completed': 'Terminé',
            'cancelled': 'Annulé'
        }
        return status_map.get(self.status, self.status)

class SessionParticipant(db.Model):
    """Model for tracking which students are in which sessions"""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('osce_session.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate participants
    __table_args__ = (db.UniqueConstraint('session_id', 'student_id', name='unique_session_student'),)

class SessionStationAssignment(db.Model):
    """Model for tracking which stations are assigned to which sessions"""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('osce_session.id'), nullable=False)
    case_number = db.Column(db.String(50), db.ForeignKey('patient_case1.case_number'), nullable=False)
    station_order = db.Column(db.Integer)  # Order of stations in the session
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate station assignments
    __table_args__ = (db.UniqueConstraint('session_id', 'case_number', name='unique_session_station'),)

# Image model for patient cases
class CaseImage(db.Model):
    __tablename__ = 'case_images'
    
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(50), db.ForeignKey('patient_case1.case_number'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<CaseImage {self.filename} for Case {self.case_number}>'

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
    
    # Relationships
    performances = db.relationship('StudentPerformance', backref='case', lazy=True)
    images = db.relationship('CaseImage', backref='case', lazy=True, cascade='all, delete-orphan')
    session_assignments = db.relationship('SessionStationAssignment', backref='case', lazy=True, cascade='all, delete-orphan')
    
    @property
    def patient_info(self):
        if self.patient_info_json:
            try:
                return json.loads(self.patient_info_json)
            except:
                return {}
        return {}
    
    @patient_info.setter
    def patient_info(self, value):
        if value is None:
            self.patient_info_json = None
        else:
            self.patient_info_json = json.dumps(value, ensure_ascii=False)
    
    @property
    def symptoms(self):
        if self.symptoms_json:
            try:
                return json.loads(self.symptoms_json)
            except:
                return []
        return []
    
    @symptoms.setter
    def symptoms(self, value):
        if value is None:
            self.symptoms_json = None
        else:
            self.symptoms_json = json.dumps(value, ensure_ascii=False)
    
    @property
    def evaluation_checklist(self):
        if self.evaluation_checklist_json:
            try:
                return json.loads(self.evaluation_checklist_json)
            except:
                return []
        return []
    
    @evaluation_checklist.setter
    def evaluation_checklist(self, value):
        if value is None:
            self.evaluation_checklist_json = None
        else:
            self.evaluation_checklist_json = json.dumps(value, ensure_ascii=False)
    
    @property
    def differential_diagnosis(self):
        if self.differential_diagnosis_json:
            try:
                return json.loads(self.differential_diagnosis_json)
            except:
                return []
        return []
    
    @differential_diagnosis.setter
    def differential_diagnosis(self, value):
        if value is None:
            self.differential_diagnosis_json = None
        else:
            if isinstance(value, list):
                self.differential_diagnosis_json = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, str) and value.strip():
                # If it's a string, split by commas and create a list
                diff_list = [item.strip() for item in value.split(',') if item.strip()]
                self.differential_diagnosis_json = json.dumps(diff_list, ensure_ascii=False) if diff_list else None
            else:
                self.differential_diagnosis_json = None
    
    @property
    def custom_sections(self):
        if self.custom_sections_json:
            try:
                return json.loads(self.custom_sections_json)
            except:
                return []
        return []
    
    @custom_sections.setter
    def custom_sections(self, value):
        if value is None:
            self.custom_sections_json = None
        else:
            self.custom_sections_json = json.dumps(value, ensure_ascii=False)
    
    def __repr__(self):
        return f'<PatientCase {self.case_number}>'
    
    def get_average_score(self):
        """Get average score for this case across all students"""
        performances = StudentPerformance.query.filter_by(case_number=self.case_number).all()
        if not performances:
            return 0
        total_score = sum(p.percentage_score for p in performances)
        return round(total_score / len(performances), 1)
    
    def get_completion_count(self):
        """Get number of times this case has been completed"""
        return StudentPerformance.query.filter_by(case_number=self.case_number).count()
    
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
        
        case = cls(
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
        
        return case
    
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
                'images': []  # Will be populated with actual images
            }
            
            # Add images from relationship
            if hasattr(self, 'images') and self.images:
                for image in self.images:
                    case_data['images'].append({
                        'path': image.path,
                        'description': image.description or 'Image médicale',
                        'filename': image.filename
                    })
            
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

# Student Performance Tracking
class StudentPerformance(db.Model):
    __tablename__ = 'student_performance'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    case_number = db.Column(db.String(50), db.ForeignKey('patient_case1.case_number'), nullable=False)
    
    # Performance metrics
    points_earned = db.Column(db.Integer, default=0)
    points_total = db.Column(db.Integer, default=0)
    percentage_score = db.Column(db.Float, default=0.0)
    
    # Timing information
    consultation_duration = db.Column(db.Integer)  # in seconds
    time_remaining = db.Column(db.Integer)  # in seconds
    
    # Detailed evaluation data (JSON)
    evaluation_results_json = db.Column(db.Text)  # Store full evaluation results
    recommendations_json = db.Column(db.Text)  # Store recommendations
    
    # Add this line to store the conversation transcript
    conversation_transcript_json = db.Column(db.Text) # Stores the list of message dicts as JSON

    # Timestamps
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<StudentPerformance {self.student.name} - Case {self.case_number} - {self.percentage_score}%>'
    
    @property
    def evaluation_results(self):
        if self.evaluation_results_json:
            try:
                return json.loads(self.evaluation_results_json)
            except:
                return {}
        return {}
    
    @evaluation_results.setter
    def evaluation_results(self, results):
        """Set evaluation results as JSON"""
        self.evaluation_results_json = json.dumps(results, ensure_ascii=False)

    @property
    def recommendations(self):
        if self.recommendations_json:
            try:
                return json.loads(self.recommendations_json)
            except:
                return []
        return []

    @recommendations.setter
    def recommendations(self, recommendations_list):
        """Set recommendations as JSON"""
        self.recommendations_json = json.dumps(recommendations_list, ensure_ascii=False)

    # Add this property to access the conversation transcript
    @property
    def conversation_transcript(self):
        if self.conversation_transcript_json:
            try:
                return json.loads(self.conversation_transcript_json)
            except:
                return [] # Return empty list if JSON is invalid
        return [] # Return empty list if no transcript stored

    @conversation_transcript.setter
    def conversation_transcript(self, conversation_list):
        """Set conversation transcript as JSON"""
        self.conversation_transcript_json = json.dumps(conversation_list, ensure_ascii=False)
    
    def get_performance_grade(self):
        """Get letter grade based on percentage score"""
        if self.percentage_score >= 90:
            return 'A'
        elif self.percentage_score >= 80:
            return 'B'
        elif self.percentage_score >= 70:
            return 'C'
        elif self.percentage_score >= 60:
            return 'D'
        else:
            return 'F'
    
    def get_performance_status(self):
        """Get performance status description"""
        if self.percentage_score >= 80:
            return 'Excellent'
        elif self.percentage_score >= 70:
            return 'Bon'
        elif self.percentage_score >= 60:
            return 'Satisfaisant'
        else:
            return 'À améliorer'
    
    @classmethod
    def create_from_evaluation(cls, student_id, case_number, evaluation_results, recommendations=None, consultation_duration=None, time_remaining=None, conversation_transcript=None):
        """Create a new performance record from evaluation results"""
        performance = cls(
            student_id=student_id,
            case_number=case_number,
            points_earned=evaluation_results.get('points_earned', 0),
            points_total=evaluation_results.get('points_total', 0),
            percentage_score=evaluation_results.get('percentage', 0.0),
            consultation_duration=consultation_duration,
            time_remaining=time_remaining
        )
        
        performance.evaluation_results = evaluation_results # Use setter
        if recommendations:
            performance.recommendations = recommendations # Use setter
        if conversation_transcript:
            performance.conversation_transcript = conversation_transcript # Use setter
        
        return performance