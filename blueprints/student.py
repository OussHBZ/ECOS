from flask import Blueprint, render_template, request, jsonify, session, send_from_directory, current_app
from flask_login import current_user
from models import db, Student, PatientCase, StudentPerformance, CompetitionSession, CompetitionParticipant, StudentCompetitionSession
from auth import student_required
import logging
from datetime import datetime
import time

student_bp = Blueprint('student', __name__)
logger = logging.getLogger(__name__)

@student_bp.route('/')
@student_required
def student_interface():
    """Render the student interface"""
    # Get functions from app config
    get_case_metadata = current_app.config.get('GET_CASE_METADATA')
    get_unique_specialties = current_app.config.get('GET_UNIQUE_SPECIALTIES')
    
    if not get_case_metadata or not get_unique_specialties:
        logger.error("Required functions not found in app config")
        cases = []
        specialties = []
    else:
        cases = get_case_metadata()
        specialties = get_unique_specialties()
    
    return render_template('student.html', 
                         cases=cases, 
                         specialties=specialties,
                         student_name=current_user.name)

@student_bp.route('/available-competitions')
@student_required
def student_available_competitions():
    """Get available competition sessions for the current student"""
    try:
        # Find sessions where this student is a participant
        participant_sessions = db.session.query(
            CompetitionSession, CompetitionParticipant, StudentCompetitionSession
        ).join(
            CompetitionParticipant, CompetitionSession.id == CompetitionParticipant.session_id
        ).outerjoin(
            StudentCompetitionSession, 
            db.and_(
                StudentCompetitionSession.session_id == CompetitionSession.id,
                StudentCompetitionSession.student_id == current_user.id
            )
        ).filter(
            CompetitionParticipant.student_id == current_user.id,
            CompetitionSession.status.in_(['scheduled', 'active'])
        ).all()
        
        competitions = []
        for session_obj, participant, student_session in participant_sessions:
            competition_data = {
                'id': session_obj.id,
                'name': session_obj.name,
                'description': session_obj.description,
                'start_time': session_obj.start_time.strftime('%d/%m/%Y %H:%M'),
                'end_time': session_obj.end_time.strftime('%d/%m/%Y %H:%M'),
                'status': session_obj.status,
                'status_display': session_obj.get_status_display(),
                'stations_per_session': session_obj.stations_per_session,
                'time_per_station': session_obj.time_per_station,
                'time_between_stations': session_obj.time_between_stations,
                'participant_count': session_obj.get_participant_count(),
                'logged_in_count': session_obj.get_logged_in_count(),
                'can_join': session_obj.status == 'scheduled',
                'can_continue': session_obj.status == 'active',
                'student_status': student_session.status if student_session else 'registered',
                'current_station': student_session.current_station_order if student_session else 0,
                'progress': student_session.get_progress_percentage() if student_session else 0
            }
            competitions.append(competition_data)
        
        return jsonify({'competitions': competitions})
        
    except Exception as e:
        logger.error(f"Error getting available competitions: {str(e)}")
        return jsonify({"error": str(e)}), 500

@student_bp.route('/join-competition/<int:session_id>', methods=['POST'])
@student_required
def student_join_competition(session_id):
    """Student joins/logs into a competition session"""
    try:
        session_obj = CompetitionSession.query.get_or_404(session_id)
        
        # Check if student is a participant
        participant = CompetitionParticipant.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({"error": "You are not registered for this competition", "success": False}), 403
        
        # Get student session
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not student_session:
            return jsonify({"error": "Student session not found", "success": False}), 404
        
        # Log student into session
        if student_session.status == 'registered':
            student_session.login_to_session()
            
            # Check if competition can start
            if session_obj.can_start_competition():
                # Auto-start competition if all students are logged in
                session_obj.start_competition()
                
        return jsonify({
            "success": True,
            "message": "Successfully joined competition",
            "session_status": session_obj.status,
            "student_status": student_session.status,
            "waiting_for_others": session_obj.get_logged_in_count() < session_obj.get_participant_count()
        })
        
    except Exception as e:
        logger.error(f"Error joining competition: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

@student_bp.route('/stats')
@student_required
def student_stats():
    """Get student statistics"""
    try:
        # Get student performances
        performances = StudentPerformance.query.filter_by(student_id=current_user.id)\
            .order_by(StudentPerformance.completed_at.desc()).all()
        
        # Calculate stats
        total_workouts = len(performances)
        unique_stations = len(set(perf.case_number for perf in performances))
        
        if performances:
            average_score = sum(perf.percentage_score for perf in performances) / len(performances)
        else:
            average_score = 0
        
        # Format recent performances
        recent_performances = []
        for perf in performances[:10]:  # Last 10 performances
            case = PatientCase.query.filter_by(case_number=perf.case_number).first()
            recent_performances.append({
                'case_number': perf.case_number,
                'specialty': case.specialty if case else 'Unknown',
                'score': perf.percentage_score,
                'grade': perf.get_performance_grade(),
                'status': perf.get_performance_status(),
                'completed_at': perf.completed_at.strftime('%d/%m/%Y %H:%M'),
                'duration': f"{perf.consultation_duration // 60}:{perf.consultation_duration % 60:02d}" if perf.consultation_duration else "N/A"
            })
        
        return jsonify({
            'total_workouts': total_workouts,
            'unique_stations': unique_stations,
            'average_score': round(average_score),
            'recent_performances': recent_performances
        })
        
    except Exception as e:
        logger.error(f"Error getting student stats: {str(e)}")
        return jsonify({"error": str(e)}), 500

@student_bp.route('/stations')
@student_required
def student_stations():
    """Get student stations with performance data"""
    try:
        search_query = request.args.get('search', '').strip()
        
        # Get all cases
        query = PatientCase.query
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
            ).all()
            
            attempts = len(student_performances)
            best_score = max(perf.percentage_score for perf in student_performances) if student_performances else 0
            last_attempt = student_performances[-1].completed_at.strftime('%d/%m/%Y') if student_performances else None
            
            stations.append({
                'case_number': case.case_number,
                'specialty': case.specialty,
                'consultation_time': case.consultation_time,
                'attempts': attempts,
                'best_score': best_score,
                'last_attempt': last_attempt
            })
        
        return jsonify({'stations': stations})
        
    except Exception as e:
        logger.error(f"Error getting student stations: {str(e)}")
        return jsonify({"error": str(e)}), 500