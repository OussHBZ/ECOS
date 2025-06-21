from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json
import random
import logging

logger = logging.getLogger(__name__)

db = SQLAlchemy()

class SessionMixin:
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


class Student(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    # Updated: Changed from 4 digits to 6-7 digits for Numéro d'Apogée
    student_code = db.Column(db.String(7), unique=True, nullable=False)  # Changed from String(4) to String(7)
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
    
    def get_competition_history(self):
        """Get student's competition participation history"""
        competitions = db.session.query(
            CompetitionSession, StudentCompetitionSession
        ).join(
            StudentCompetitionSession, CompetitionSession.id == StudentCompetitionSession.session_id
        ).filter(
            StudentCompetitionSession.student_id == self.id
        ).order_by(CompetitionSession.start_time.desc()).all()
        
        history = []
        for comp_session, student_session in competitions:
            history.append({
                'competition_id': comp_session.id,
                'competition_name': comp_session.name,
                'start_time': comp_session.start_time,
                'status': student_session.status,
                'progress': student_session.get_progress_percentage(),
                'average_score': student_session.get_average_score(),
                'completed_stations': student_session.get_completed_stations_count(),
                'total_stations': comp_session.stations_per_session
            })
        
        return history
    
    def get_competition_stats(self):
        """Get overall competition statistics for this student"""
        student_sessions = StudentCompetitionSession.query.filter_by(student_id=self.id).all()
        
        if not student_sessions:
            return {
                'total_competitions': 0,
                'completed_competitions': 0,
                'average_score': 0,
                'total_stations_completed': 0
            }
        
        completed_sessions = [s for s in student_sessions if s.status == 'completed']
        total_stations = sum(s.get_completed_stations_count() for s in student_sessions)
        
        avg_score = 0
        if completed_sessions:
            total_score = sum(s.get_average_score() for s in completed_sessions)
            avg_score = round(total_score / len(completed_sessions), 1)
        
        return {
            'total_competitions': len(student_sessions),
            'completed_competitions': len(completed_sessions),
            'average_score': avg_score,
            'total_stations_completed': total_stations,
            'competition_completion_rate': round((len(completed_sessions) / len(student_sessions)) * 100, 1)
        }
    
    # ADD THE NEW METHOD HERE - RIGHT BEFORE __repr__
    @classmethod
    def validate_apogee_number(cls, apogee_number):
        """Validate Numéro d'Apogée format (6-7 digits)"""
        if not apogee_number:
            return False, "Le numéro d'Apogée est requis"
        
        # Remove any whitespace
        apogee_number = str(apogee_number).strip()
        
        # Check if it's numeric
        if not apogee_number.isdigit():
            return False, "Le numéro d'Apogée ne doit contenir que des chiffres"
        
        # Check length (6-7 digits)
        if len(apogee_number) < 6 or len(apogee_number) > 7:
            return False, "Le numéro d'Apogée doit contenir entre 6 et 7 chiffres"
        
        return True, apogee_number
    
    def __repr__(self):
        return f'<Student {self.student_code}: {self.name}>'

class TeacherAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(20), unique=True, nullable=False)
    last_used = db.Column(db.DateTime)

class AdminAccess(db.Model):
    """Model for Administrator access tracking"""
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(20), unique=True, nullable=False)
    last_used = db.Column(db.DateTime)

class OSCESession(db.Model, SessionMixin):
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
    def get_completion_count(self):
        """Get the number of times this case has been completed"""
        from models import StudentPerformance
        return StudentPerformance.query.filter_by(case_number=self.case_number).count()

    def get_average_score(self):
        """Get the average score for this case"""
        from models import StudentPerformance
        performances = StudentPerformance.query.filter_by(case_number=self.case_number).all()
        if not performances:
            return 0
        return round(sum(perf.percentage_score for perf in performances) / len(performances))

    # Add to Student class:
    def get_total_workouts(self):
        """Get total number of consultations for this student"""
        from models import StudentPerformance
        return StudentPerformance.query.filter_by(student_id=self.id).count()

    def get_unique_stations_played(self):
        """Get number of unique stations this student has played"""
        from models import StudentPerformance, db
        return db.session.query(StudentPerformance.case_number).filter_by(student_id=self.id).distinct().count()

    def get_average_score(self):
        """Get average score for this student"""
        from models import StudentPerformance
        performances = StudentPerformance.query.filter_by(student_id=self.id).all()
        if not performances:
            return 0
        return round(sum(perf.percentage_score for perf in performances) / len(performances))
    def get_competition_usage_stats(self):
        """Get usage statistics for this case in competitions"""
        # Count how many times this case was used in competitions
        competition_assignments = StudentStationAssignment.query.filter_by(
            case_number=self.case_number
        ).all()
        
        total_uses = len(competition_assignments)
        completed_uses = len([a for a in competition_assignments if a.status == 'completed'])
        
        # Calculate average score in competitions
        avg_score = 0
        if completed_uses > 0:
            scores = []
            for assignment in competition_assignments:
                if assignment.status == 'completed':
                    score = assignment.get_performance_score()
                    if score > 0:
                        scores.append(score)
            
            if scores:
                avg_score = round(sum(scores) / len(scores), 1)
        
        return {
            'total_competition_uses': total_uses,
            'completed_uses': completed_uses,
            'average_competition_score': avg_score,
            'completion_rate': round((completed_uses / total_uses) * 100, 1) if total_uses > 0 else 0
        }
    
    def __repr__(self):
        """String representation"""
        return f'<PatientCase {self.case_number}: {self.specialty}>'

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

    @property
    def conversation_transcript(self):
        if self.conversation_transcript_json:
            try:
                return json.loads(self.conversation_transcript_json)
            except:
                return []
        return []

    @conversation_transcript.setter
    def conversation_transcript(self, conversation_list):
        """Set conversation transcript as JSON"""
        self.conversation_transcript_json = json.dumps(conversation_list, ensure_ascii=False)
    
    
    def get_performance_status(self):
        """Get performance status in French"""
        if self.percentage_score >= 85:
            return 'Excellent'
        elif self.percentage_score >= 75:
            return 'Bon'
        elif self.percentage_score >= 65:
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
        
        performance.evaluation_results = evaluation_results
        if recommendations:
            performance.recommendations = recommendations
        if conversation_transcript:
            performance.conversation_transcript = conversation_transcript
        
        return performance

class CompetitionSession(db.Model):
    """Model for OSCE competition sessions"""
    __tablename__ = 'competition_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(50))
    status = db.Column(db.String(20), default='scheduled')  # scheduled, active, completed, cancelled
    
    # Competition-specific fields
    stations_per_session = db.Column(db.Integer, nullable=False, default=3)
    time_per_station = db.Column(db.Integer, nullable=False, default=10)  # minutes
    time_between_stations = db.Column(db.Integer, nullable=False, default=2)  # minutes
    randomize_stations = db.Column(db.Boolean, default=True)
    
    # Relationships
    participants = db.relationship('CompetitionParticipant', backref='session', lazy=True, cascade='all, delete-orphan')
    station_assignments = db.relationship('CompetitionStationBank', backref='session', lazy=True, cascade='all, delete-orphan')
    student_sessions = db.relationship('StudentCompetitionSession', backref='session', lazy=True, cascade='all, delete-orphan')
    
    def get_participant_count(self):
        """Get number of participants in this session"""
        return len(self.participants)
    
    def get_assigned_stations_count(self):
        """Get number of stations in the station bank"""
        return len(self.station_assignments)
    
    def get_logged_in_count(self):
        """Get number of students currently logged into the session"""
        return StudentCompetitionSession.query.filter_by(
            session_id=self.id, 
            status='logged_in'
        ).count()
    
    def get_active_students_count(self):
        """Get number of students actively participating (in stations)"""
        try:
            return StudentCompetitionSession.query.filter(
                StudentCompetitionSession.session_id == self.id,
                StudentCompetitionSession.status.in_(['active', 'between_stations'])
            ).count()
        except Exception as e:
            logger.error(f"Error getting active students count for competition {self.id}: {str(e)}")
            return 0
    
    def get_completed_students_count(self):
        """Get number of students who completed the competition"""
        try:
            return StudentCompetitionSession.query.filter_by(
                session_id=self.id,
                status='completed'
            ).count()
        except Exception as e:
            logger.error(f"Error getting completed students count for competition {self.id}: {str(e)}")
            return 0
    
    def can_start_competition(self):
        """Check if competition can start (all participants logged in)"""
        logged_in_count = self.get_logged_in_count()
        total_participants = self.get_participant_count()
        station_count = self.get_assigned_stations_count()
        
        return (logged_in_count >= total_participants and 
                total_participants > 0 and 
                station_count >= self.stations_per_session and
                self.status == 'scheduled')
    
    def start_competition(self):
        """Start the competition by assigning stations to all participants"""
        try:
            if not self.can_start_competition():
                logger.error(f"Cannot start competition {self.id}: requirements not met")
                return False
                
            # Get all available stations from the station bank
            available_stations = [assignment.case_number for assignment in self.station_assignments]
            
            if len(available_stations) < self.stations_per_session:
                logger.error(f"Not enough stations in bank: {len(available_stations)} < {self.stations_per_session}")
                return False
            
            # Get all logged-in students
            logged_in_students = StudentCompetitionSession.query.filter_by(
                session_id=self.id,
                status='logged_in'
            ).all()
            
            logger.info(f"Starting competition for {len(logged_in_students)} students")
            
            for student_session in logged_in_students:
                # Randomly select stations for this student
                if self.randomize_stations:
                    import random
                    selected_stations = random.sample(available_stations, 
                                                    min(self.stations_per_session, len(available_stations)))
                else:
                    selected_stations = available_stations[:self.stations_per_session]
                
                # Create station assignments for this student
                for order, case_number in enumerate(selected_stations, 1):
                    assignment = StudentStationAssignment(
                        student_session_id=student_session.id,
                        case_number=case_number,
                        station_order=order,
                        status='pending'
                    )
                    db.session.add(assignment)
                
                # Update student status to active and set first station
                student_session.status = 'active'
                student_session.current_station_order = 1
                student_session.started_at = datetime.utcnow()
                
                logger.info(f"Assigned {len(selected_stations)} stations to student {student_session.student_id}")
            
            # Update session status
            self.status = 'active'
            db.session.commit()
            
            logger.info(f"Competition {self.id} started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error starting competition {self.id}: {str(e)}")
            db.session.rollback()
            return False

    def _calculate_duration_minutes(self, student_session):
        """Calculate duration in minutes for a student session"""
        if not student_session.started_at:
            return 0
        
        end_time = student_session.completed_at or datetime.utcnow()
        duration = end_time - student_session.started_at
        return round(duration.total_seconds() / 60, 1)

    def get_competition_statistics(self):
        """Get comprehensive competition statistics"""
        try:
            # Get all student sessions for this competition
            student_sessions = StudentCompetitionSession.query.filter_by(session_id=self.id).all()
            
            total_participants = len(student_sessions)
            completed_participants = len([s for s in student_sessions if s.status == 'completed'])
            active_participants = len([s for s in student_sessions if s.status in ['active', 'between_stations']])
            
            # Calculate scores
            completed_sessions = [s for s in student_sessions if s.status == 'completed']
            avg_score = 0
            if completed_sessions:
                total_scores = sum(s.get_average_score() for s in completed_sessions)
                avg_score = round(total_scores / len(completed_sessions), 1)
            
            # Calculate completion rate
            completion_rate = self._get_average_completion_rate()
            
            # Calculate average duration
            avg_duration = 0
            if completed_sessions:
                durations = [self._calculate_duration_minutes(s) for s in completed_sessions]
                avg_duration = round(sum(durations) / len(durations), 1)
            
            return {
                'total_participants': total_participants,
                'completed_participants': completed_participants,
                'active_participants': active_participants,
                'completion_percentage': round((completed_participants / total_participants) * 100, 1) if total_participants > 0 else 0,
                'average_score': avg_score,
                'average_completion_rate': completion_rate,
                'average_duration_minutes': avg_duration,
                'status': self.status,
                'stations_per_session': self.stations_per_session,
                'time_per_station': self.time_per_station
            }
        except Exception as e:
            logger.error(f"Error calculating competition statistics: {str(e)}")
            return {}

    def _get_average_completion_rate(self):
        """Calculate average completion rate across all participants"""
        try:
            student_sessions = StudentCompetitionSession.query.filter_by(session_id=self.id).all()
            
            if not student_sessions:
                return 0
            
            total_completion_rate = 0
            for student_session in student_sessions:
                completion_rate = (student_session.get_completed_stations_count() / self.stations_per_session) * 100
                total_completion_rate += completion_rate
            
            return round(total_completion_rate / len(student_sessions), 1)
        except Exception as e:
            logger.error(f"Error calculating average completion rate: {str(e)}")
            return 0

    def pause_competition(self):
        """Pause an active competition"""
        try:
            if self.status != 'active':
                logger.warning(f"Cannot pause competition {self.id}: status is {self.status}")
                return False
            
            # Mark session as paused
            self.status = 'paused'
            
            # You could also pause individual student timers here if needed
            # For now, we'll just change the status
            
            db.session.commit()
            logger.info(f"Competition {self.id} paused successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error pausing competition {self.id}: {str(e)}")
            db.session.rollback()
            return False

    def resume_competition(self):
        """Resume a paused competition"""
        try:
            if self.status != 'paused':
                logger.warning(f"Cannot resume competition {self.id}: status is {self.status}")
                return False
            
            # Mark session as active again
            self.status = 'active'
            
            db.session.commit()
            logger.info(f"Competition {self.id} resumed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error resuming competition {self.id}: {str(e)}")
            db.session.rollback()
            return False

    def end_competition(self):
        """Manually end a competition"""
        try:
            if self.status not in ['active', 'paused']:
                logger.warning(f"Cannot end competition {self.id}: status is {self.status}")
                return False
            
            # Mark all active student sessions as completed
            active_sessions = StudentCompetitionSession.query.filter_by(
                session_id=self.id
            ).filter(
                StudentCompetitionSession.status.in_(['active', 'between_stations', 'logged_in'])
            ).all()
            
            for student_session in active_sessions:
                if not student_session.completed_at:
                    student_session.completed_at = datetime.utcnow()
                student_session.status = 'completed'
            
            # Mark competition as completed
            self.status = 'completed'
            
            db.session.commit()
            logger.info(f"Competition {self.id} ended successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error ending competition {self.id}: {str(e)}")
            db.session.rollback()
            return False

    def __repr__(self):
        """String representation of the competition session"""
        return f'<CompetitionSession {self.id}: {self.name} ({self.status})>'


    def get_leaderboard(self):
        """Get competition leaderboard with rankings"""
        completed_sessions = StudentCompetitionSession.query.filter_by(
            session_id=self.id,
            status='completed'
        ).all()
        
        leaderboard = []
        for student_session in completed_sessions:
            avg_score = student_session.get_average_score()
            
            leaderboard.append({
                'student_id': student_session.student_id,
                'student_name': student_session.student.name,
                'student_code': student_session.student.student_code,
                'average_score': avg_score,
                'stations_completed': student_session.get_completed_stations_count(),
                'completion_time': student_session.completed_at
            })
        
        # Sort by average score (descending), then by completion time (ascending)
        leaderboard.sort(key=lambda x: (-x['average_score'], x['completion_time'] or datetime.utcnow()))
        
        # Add rankings
        for i, entry in enumerate(leaderboard, 1):
            entry['rank'] = i
            
        return leaderboard
            
    def get_status_display(self):
        """Get display-friendly status"""
        status_map = {
            'scheduled': 'Programmée',
            'active': 'En cours',
            'completed': 'Terminée',
            'cancelled': 'Annulée'
        }
        return status_map.get(self.status, self.status)
    
    def check_and_complete_competition(self):
        """Check if all students are done and mark competition as completed"""
        try:
            all_student_sessions = StudentCompetitionSession.query.filter_by(session_id=self.id).all()
            
            if not all_student_sessions:
                return False
            
            completed_students = [s for s in all_student_sessions if s.status == 'completed']
            
            if len(completed_students) >= len(all_student_sessions):
                self.status = 'completed'
                db.session.commit()
                logger.info(f"Competition {self.id} automatically completed")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking competition completion: {str(e)}")
            return False
        
    def safe_delete(self):
        """Safely delete a competition session and all related data"""
        try:
            # Check if session can be deleted
            if self.status == 'active':
                active_participants = StudentCompetitionSession.query.filter(
                    StudentCompetitionSession.session_id == self.id,
                    StudentCompetitionSession.status.in_(['active', 'between_stations'])
                ).count()
                
                if active_participants > 0:
                    return False, f"Cannot delete session with {active_participants} active participants"
            
            # Delete in correct order to avoid foreign key constraints
            
            # 1. Delete student station assignments first
            student_sessions = StudentCompetitionSession.query.filter_by(session_id=self.id).all()
            for student_session in student_sessions:
                # Delete station assignments for this student session
                StudentStationAssignment.query.filter_by(student_session_id=student_session.id).delete()
            
            # 2. Delete student competition sessions
            StudentCompetitionSession.query.filter_by(session_id=self.id).delete()
            
            # 3. Delete competition participants
            CompetitionParticipant.query.filter_by(session_id=self.id).delete()
            
            # 4. Delete station bank assignments
            CompetitionStationBank.query.filter_by(session_id=self.id).delete()
            
            # 5. Finally delete the session itself
            db.session.delete(self)
            
            return True, "Session deleted successfully"
            
        except Exception as e:
            return False, f"Error during deletion: {str(e)}"

    def can_be_deleted(self):
        """Check if the session can be safely deleted"""
        if self.status == 'active':
            active_participants = StudentCompetitionSession.query.filter(
                StudentCompetitionSession.session_id == self.id,
                StudentCompetitionSession.status.in_(['active', 'between_stations'])
            ).count()
            
            if active_participants > 0:
                return False, f"Session has {active_participants} active participants"
        
        return True, "Session can be deleted"

    def get_deletion_info(self):
        """Get information about what will be deleted"""
        participant_count = CompetitionParticipant.query.filter_by(session_id=self.id).count()
        station_count = CompetitionStationBank.query.filter_by(session_id=self.id).count()
        student_sessions_count = StudentCompetitionSession.query.filter_by(session_id=self.id).count()
        
        # Count completed performances
        completed_performances = StudentCompetitionSession.query.filter_by(
            session_id=self.id,
            status='completed'
        ).count()
        
        return {
            'participants': participant_count,
            'stations': station_count,
            'student_sessions': student_sessions_count,
            'completed_performances': completed_performances,
            'has_results': completed_performances > 0
        }
    
class CompetitionParticipant(db.Model):
    """Model for tracking which students are in which competition sessions"""
    __tablename__ = 'competition_participants'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('competition_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate participants
    __table_args__ = (db.UniqueConstraint('session_id', 'student_id', name='unique_session_participant'),)
    def __repr__(self):
        """String representation"""
        return f'<CompetitionParticipant: Student {self.student_id} in Session {self.session_id}>'

class CompetitionStationBank(db.Model):
    """Model for tracking which stations are available in a competition session"""
    __tablename__ = 'competition_station_bank'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('competition_sessions.id'), nullable=False)
    case_number = db.Column(db.String(50), db.ForeignKey('patient_case1.case_number'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate stations
    __table_args__ = (db.UniqueConstraint('session_id', 'case_number', name='unique_session_station'),)
    def __repr__(self):
        """String representation"""
        return f'<CompetitionStationBank: Case {self.case_number} in Session {self.session_id}>'

class StudentCompetitionSession(db.Model):
    """Model for tracking individual student participation in competition sessions"""
    __tablename__ = 'student_competition_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('competition_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default='registered')  # registered, logged_in, active, between_stations, completed
    current_station_order = db.Column(db.Integer, default=0)
    
    # Timing
    logged_in_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    station_assignments = db.relationship('StudentStationAssignment', backref='student_session', lazy=True, cascade='all, delete-orphan')
    student = db.relationship('Student', backref='competition_sessions')
    
    def get_current_station_assignment(self):
        """Get the current station assignment"""
        if self.current_station_order <= 0:
            return None
            
        return StudentStationAssignment.query.filter_by(
            student_session_id=self.id,
            station_order=self.current_station_order
        ).first()
    
    def get_next_station_assignment(self):
        """Get the next station assignment"""
        next_order = self.current_station_order + 1
        return StudentStationAssignment.query.filter_by(
            student_session_id=self.id,
            station_order=next_order
        ).first()


    def login_to_session(self):
        """Mark student as logged into the session"""
        self.status = 'logged_in'
        self.logged_in_at = datetime.utcnow()
        db.session.commit()
    
    def get_current_station(self):
        """Get the current station assignment"""
        return StudentStationAssignment.query.filter_by(
            student_session_id=self.id,
            station_order=self.current_station_order
        ).first()
    
    def complete_current_station(self, evaluation_results, conversation_transcript=None):
        """Complete the current station and move to next"""
        try:
            current_station = self.get_current_station_assignment()
            if not current_station:
                logger.error(f"No current station found for student session {self.id}")
                return False
            
            # Mark current station as completed
            current_station.status = 'completed'
            current_station.completed_at = datetime.utcnow()
            current_station.performance_data = json.dumps({
                'conversation_transcript': conversation_transcript or [],  # Use parameter instead of session
                'evaluation_results': evaluation_results,
                'percentage_score': evaluation_results.get('percentage', 0),
                'points_earned': evaluation_results.get('points_earned', 0),
                'points_total': evaluation_results.get('points_total', 0),
                'completed_at': datetime.utcnow().isoformat()
            }, ensure_ascii=False)
            
            # Check if this was the last station
            if self.current_station_order >= self.session.stations_per_session:
                # Competition completed
                self.status = 'completed'
                self.completed_at = datetime.utcnow()
                logger.info(f"Student {self.student_id} completed competition session {self.session_id}")
                # Check if all students are done and auto-complete competition
                self.session.check_and_complete_competition()
            else:
                # Move to next station
                self.current_station_order += 1
                self.status = 'between_stations'
                logger.info(f"Student {self.student_id} moved to station {self.current_station_order}")

            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error completing station for student session {self.id}: {str(e)}")
            db.session.rollback()
            return False
    
    def start_next_station(self):
        """Start the next station"""
        try:
            if self.status != 'between_stations':
                logger.error(f"Cannot start next station: wrong status {self.status}")
                return False
                
            self.status = 'active'
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error starting next station for student session {self.id}: {str(e)}")
            db.session.rollback()
            return False
    
    def get_total_score(self):
        """Get total score across all completed stations"""
        total = 0
        completed_assignments = [a for a in self.station_assignments if a.status == 'completed']
        
        for assignment in completed_assignments:
            if assignment.performance_data:
                try:
                    if isinstance(assignment.performance_data, str):
                        data = json.loads(assignment.performance_data)
                    else:
                        data = assignment.performance_data
                        
                    score = data.get('percentage_score', 0)
                    total += score
                except (json.JSONDecodeError, TypeError):
                    logger.error(f"Error parsing performance data for assignment {assignment.id}")
        
        return total
    
    def get_average_score(self):
        """Get average score across all completed stations"""
        completed = self.get_completed_stations_count()
        if completed == 0:
            return 0
        return round(self.get_total_score() / completed, 1)
    
    def get_completed_stations_count(self):
        """Get number of completed stations"""
        return len([a for a in self.station_assignments if a.status == 'completed'])
    
    def get_progress_percentage(self):
        """Get completion progress as percentage"""
        if not hasattr(self, 'session') or not self.session:
            return 0
        
        total_stations = self.session.stations_per_session
        completed = self.get_completed_stations_count()
        return round((completed / total_stations) * 100, 1) if total_stations > 0 else 0

    def get_time_spent_minutes(self):
        """Get total time spent in competition (in minutes)"""
        if not self.started_at:
            return 0
        
        end_time = self.completed_at or datetime.utcnow()
        duration = end_time - self.started_at
        return round(duration.total_seconds() / 60, 1)
    
    def get_current_station_info(self):
        """Get detailed info about current station"""
        current_assignment = self.get_current_station_assignment()
        if not current_assignment:
            return None
        
        case = PatientCase.query.filter_by(case_number=current_assignment.case_number).first()
        if not case:
            return None
        
        return {
            'assignment_id': current_assignment.id,
            'case_number': current_assignment.case_number,
            'station_order': current_assignment.station_order,
            'specialty': case.specialty,
            'consultation_time': case.consultation_time,
            'status': current_assignment.status,
            'started_at': current_assignment.started_at.isoformat() if current_assignment.started_at else None
        }
    
    def get_detailed_progress(self):
        """Get detailed progress information"""
        completed_stations = []
        pending_stations = []
        
        for assignment in self.station_assignments:
            station_info = {
                'station_order': assignment.station_order,
                'case_number': assignment.case_number,
                'status': assignment.status
            }
            
            if assignment.status == 'completed':
                if assignment.performance_data:
                    try:
                        perf_data = json.loads(assignment.performance_data)
                        station_info['score'] = perf_data.get('percentage_score', 0)
                    except:
                        station_info['score'] = 0
                completed_stations.append(station_info)
            else:
                pending_stations.append(station_info)
        
        return {
            'completed_stations': sorted(completed_stations, key=lambda x: x['station_order']),
            'pending_stations': sorted(pending_stations, key=lambda x: x['station_order']),
            'overall_progress': self.get_progress_percentage(),
            'current_station_order': self.current_station_order,
            'status': self.status
        }
    
    def __repr__(self):
        """String representation"""
        return f'<StudentCompetitionSession {self.id}: Student {self.student_id} in Session {self.session_id} ({self.status})>'

    def get_rank(self):
        """Get the student's rank in the competition"""
        try:
            if self.status != 'completed':
                return 'N/A'
            
            # Get the competition session
            competition = CompetitionSession.query.get(self.session_id)
            if not competition:
                return 'N/A'
            
            # Get leaderboard
            leaderboard = competition.get_leaderboard()
            
            # Find this student's rank
            for entry in leaderboard:
                if entry['student_id'] == self.student_id:
                    return entry['rank']
            
            return 'N/A'
        except Exception as e:
            logger.error(f"Error getting rank for student competition session: {str(e)}")
            return 'N/A'

class StudentStationAssignment(db.Model):
    """Model for tracking individual station assignments within a student's competition session"""
    __tablename__ = 'student_station_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_session_id = db.Column(db.Integer, db.ForeignKey('student_competition_sessions.id'), nullable=False)
    case_number = db.Column(db.String(50), db.ForeignKey('patient_case1.case_number'), nullable=False)
    station_order = db.Column(db.Integer, nullable=False)  # Order within the student's session
    
    # Status and timing
    status = db.Column(db.String(20), default='pending')  # pending, active, completed
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Performance data (JSON)
    performance_data = db.Column(db.Text)  # Store evaluation results, score, etc.
    
    # Relationships
    case = db.relationship('PatientCase', backref='competition_assignments')
    
    def start_station(self):
        """Start this station"""
        self.status = 'active'
        self.started_at = datetime.utcnow()
        db.session.commit()
    
    def get_performance_summary(self):
        """Get performance summary for this station"""
        if self.performance_data:
            try:
                return json.loads(self.performance_data)
            except:
                pass
        return None
    def get_duration_minutes(self):
        """Get duration of this station in minutes"""
        if not self.started_at:
            return 0
        
        end_time = self.completed_at or datetime.utcnow()
        duration = end_time - self.started_at
        return round(duration.total_seconds() / 60, 1)
    
    def get_case_info(self):
        """Get case information for this assignment"""
        case = PatientCase.query.filter_by(case_number=self.case_number).first()
        if not case:
            return None
        
        return {
            'case_number': case.case_number,
            'specialty': case.specialty,
            'consultation_time': case.consultation_time,
            'directives': case.directives
        }
    
    def get_performance_score(self):
        """Get performance score for this station"""
        if not self.performance_data:
            return 0
        
        try:
            if isinstance(self.performance_data, str):
                data = json.loads(self.performance_data)
            else:
                data = self.performance_data
            
            return data.get('percentage_score', 0)
        except:
            return 0
    
    def __repr__(self):
        """String representation"""
        return f'<StudentStationAssignment {self.id}: Case {self.case_number} Order {self.station_order} ({self.status})>'