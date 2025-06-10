from flask import Blueprint, render_template, request, jsonify, session, send_from_directory, current_app
from flask_login import current_user
from models import db, Student, PatientCase, StudentPerformance, CompetitionSession, CompetitionParticipant, StudentCompetitionSession, StudentStationAssignment
from auth import student_required
import logging
from datetime import datetime
import time
import random

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
            # Get logged in count
            logged_in_count = StudentCompetitionSession.query.filter_by(
                session_id=session_obj.id,
                status='logged_in'
            ).count()
            
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
                'logged_in_count': logged_in_count,
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
        
        # Get or create student session
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not student_session:
            student_session = StudentCompetitionSession(
                session_id=session_id,
                student_id=current_user.id,
                status='registered'
            )
            db.session.add(student_session)
            db.session.commit()
        
        # Log student into session
        if student_session.status == 'registered':
            student_session.status = 'logged_in'
            student_session.logged_in_at = datetime.utcnow()
            db.session.commit()
            
            # Check if competition can start
            logged_in_count = StudentCompetitionSession.query.filter_by(
                session_id=session_id,
                status='logged_in'
            ).count()
            
            total_participants = session_obj.get_participant_count()
            
            if logged_in_count >= total_participants and session_obj.status == 'scheduled':
                # Auto-start competition if all students are logged in
                start_success = session_obj.start_competition()
                if start_success:
                    logger.info(f"Competition {session_id} auto-started")
                
        return jsonify({
            "success": True,
            "message": "Successfully joined competition",
            "session_status": session_obj.status,
            "student_status": student_session.status,
            "waiting_for_others": student_session.status == 'logged_in'
        })
        
    except Exception as e:
        logger.error(f"Error joining competition: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

@student_bp.route('/competition/<int:session_id>/status')
@student_required
def get_competition_status(session_id):
    """Get current competition status for the student"""
    try:
        session_obj = CompetitionSession.query.get_or_404(session_id)
        
        # Get student's competition session
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not student_session:
            return jsonify({"error": "Student not found in this competition"}), 404
        
        # Get current station if active
        current_station = None
        if student_session.status == 'active' and student_session.current_station_order > 0:
            station_assignment = StudentStationAssignment.query.filter_by(
                student_session_id=student_session.id,
                station_order=student_session.current_station_order
            ).first()
            
            if station_assignment:
                case = PatientCase.query.filter_by(case_number=station_assignment.case_number).first()
                if case:
                    current_station = {
                        'case_number': station_assignment.case_number,
                        'station_order': station_assignment.station_order,
                        'specialty': case.specialty,
                        'directives': case.directives,
                        'images': [
                            {
                                'path': img.path,
                                'description': img.description,
                                'filename': img.filename
                            } for img in case.images
                        ] if hasattr(case, 'images') else []
                    }
        
        status_data = {
            'session_id': session_id,
            'session_name': session_obj.name,
            'session_status': session_obj.status,
            'student_status': student_session.status,
            'current_station_order': student_session.current_station_order,
            'total_stations': session_obj.stations_per_session,
            'completed_stations': student_session.get_completed_stations_count(),
            'progress_percentage': student_session.get_progress_percentage(),
            'time_per_station': session_obj.time_per_station,
            'time_between_stations': session_obj.time_between_stations,
            'current_station': current_station
        }
        
        return jsonify(status_data)
        
    except Exception as e:
        logger.error(f"Error getting competition status: {str(e)}")
        return jsonify({"error": str(e)}), 500

@student_bp.route('/competition/<int:session_id>/start-station', methods=['POST'])
@student_required
def start_competition_station(session_id):
    """Start the current station in competition"""
    try:
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not student_session:
            return jsonify({"error": "Student session not found"}), 404
        
        # Get current station assignment
        station_assignment = StudentStationAssignment.query.filter_by(
            student_session_id=student_session.id,
            station_order=student_session.current_station_order
        ).first()
        
        if not station_assignment:
            return jsonify({"error": "No station assignment found"}), 404
        
        # Start the station
        station_assignment.status = 'active'
        station_assignment.started_at = datetime.utcnow()
        db.session.commit()
        
        # Get case data
        case = PatientCase.query.filter_by(case_number=station_assignment.case_number).first()
        if not case:
            return jsonify({"error": "Case not found"}), 404
        
        # Initialize chat for this case
        initialize_conversation = current_app.config.get('INITIALIZE_CONVERSATION')
        if initialize_conversation:
            conversation = initialize_conversation(case.case_number)
            session['current_conversation'] = [msg.content if hasattr(msg, 'content') else str(msg) for msg in conversation]
            session['current_case'] = case.case_number
        
        response_data = {
            'success': True,
            'case_number': case.case_number,
            'specialty': case.specialty,
            'directives': case.directives or '',
            'consultation_time': case.consultation_time,
            'images': [
                {
                    'path': img.path,
                    'description': img.description,
                    'filename': img.filename
                } for img in case.images
            ] if hasattr(case, 'images') else []
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error starting competition station: {str(e)}")
        return jsonify({"error": str(e)}), 500

@student_bp.route('/competition/complete-station', methods=['POST'])
@student_required
def complete_competition_station():
    """Complete the current station in competition"""
    try:
        # Get current conversation and case from session
        conversation = session.get('current_conversation', [])
        case_number = session.get('current_case')
        
        if not case_number:
            return jsonify({"error": "No active station found"}), 400
        
        # Get student's current competition session
        student_session = StudentCompetitionSession.query.filter(
            StudentCompetitionSession.student_id == current_user.id,
            StudentCompetitionSession.status.in_(['active', 'between_stations'])
        ).first()
        
        if not student_session:
            return jsonify({"error": "No active competition session found"}), 404
        
        # Evaluate the conversation
        evaluate_conversation = current_app.config.get('EVALUATE_CONVERSATION')
        if evaluate_conversation:
            evaluation_results = evaluate_conversation(conversation, case_number)
        else:
            evaluation_results = {'percentage': 0, 'checklist': [], 'feedback': 'Evaluation not available'}
        
        # Complete the station
        current_assignment = StudentStationAssignment.query.filter_by(
            student_session_id=student_session.id,
            station_order=student_session.current_station_order
        ).first()
        
        if current_assignment:
            current_assignment.status = 'completed'
            current_assignment.completed_at = datetime.utcnow()
            current_assignment.performance_data = jsonify({
                'conversation_transcript': conversation,
                'evaluation_results': evaluation_results,
                'percentage_score': evaluation_results.get('percentage', 0),
                'points_earned': evaluation_results.get('points_earned', 0),
                'points_total': evaluation_results.get('points_total', 0),
                'completed_at': datetime.utcnow().isoformat()
            }).data.decode()
        
        # Move to next station or complete session
        competition_session = CompetitionSession.query.get(student_session.session_id)
        if student_session.current_station_order < competition_session.stations_per_session:
            student_session.current_station_order += 1
            student_session.status = 'between_stations'
            is_finished = False
        else:
            student_session.status = 'completed'
            student_session.completed_at = datetime.utcnow()
            is_finished = True
        
        db.session.commit()
        
        # Clear session data
        session.pop('current_conversation', None)
        session.pop('current_case', None)
        
        response_data = {
            'success': True,
            'current_station': student_session.current_station_order - 1,  # Previous station
            'evaluation': evaluation_results,
            'recommendations': evaluation_results.get('recommendations', []),
            'is_finished': is_finished,
            'next_station_delay': competition_session.time_between_stations * 60 if not is_finished else 0
        }
        
        if is_finished:
            # Add final competition results
            response_data.update({
                'final_score': student_session.get_average_score(),
                'total_stations': competition_session.stations_per_session,
                'rank': 1,  # Calculate actual rank
                'total_participants': competition_session.get_participant_count()
            })
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error completing competition station: {str(e)}")
        return jsonify({"error": str(e)}), 500

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

@student_bp.route('/competition/<int:session_id>/next-station', methods=['POST'])
@student_required
def start_next_station_route(session_id):
    """Start the next station in competition"""
    try:
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not student_session:
            return jsonify({"error": "Student session not found"}), 404
        
        if student_session.status == 'between_stations':
            student_session.status = 'active'
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Next station started'
            })
        else:
            return jsonify({
                'error': 'Cannot start next station in current state'
            }), 400
        
    except Exception as e:
        logger.error(f"Error starting next station: {str(e)}")
        return jsonify({"error": str(e)}), 500

@student_bp.route('/competition/<int:session_id>/results')
@student_required
def get_competition_results(session_id):
    """Get final competition results for the student"""
    try:
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=current_user.id
        ).first()
        
        if not student_session:
            return jsonify({"error": "Student session not found"}), 404
        
        if student_session.status != 'completed':
            return jsonify({"error": "Competition not completed yet"}), 400
        
        # Get final results
        competition_session = CompetitionSession.query.get(session_id)
        leaderboard = competition_session.get_leaderboard()
        
        # Find student's position
        student_rank = 1
        for entry in leaderboard:
            if entry['student_id'] == current_user.id:
                student_rank = entry['rank']
                break
        
        return jsonify({
            'final_score': student_session.get_average_score(),
            'total_stations': competition_session.stations_per_session,
            'completed_stations': student_session.get_completed_stations_count(),
            'rank': student_rank,
            'total_participants': competition_session.get_participant_count(),
            'leaderboard': leaderboard[:10]  # Top 10
        })
        
    except Exception as e:
        logger.error(f"Error getting competition results: {str(e)}")
        return jsonify({"error": str(e)}), 500