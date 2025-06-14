from flask import Blueprint, render_template, request, jsonify, send_from_directory, current_app
from flask_login import current_user
from auth import admin_required
import logging
from datetime import datetime
import tempfile
import json
from simple_pdf_generator import create_simple_consultation_pdf
from models import (
    db, Student, AdminAccess, OSCESession, SessionParticipant, 
    SessionStationAssignment, PatientCase, StudentPerformance, 
    CompetitionSession, CompetitionParticipant, CompetitionStationBank, 
    StudentCompetitionSession, StudentStationAssignment
)

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)

@admin_bp.route('/')
@admin_required
def admin_interface():
    """Render the administrator interface"""
    return render_template('admin.html')

@admin_bp.route('/overview')
@admin_required
def admin_overview():
    """Get overview data for admin dashboard"""
    try:
        # Get total counts
        total_stations = PatientCase.query.count()
        total_students = Student.query.count()
        total_consultations = StudentPerformance.query.count()
        
        # Get active sessions (scheduled or active status)
        active_sessions = OSCESession.query.filter(
            OSCESession.status.in_(['scheduled', 'active'])
        ).count()
        
        # Get recent activity (last 10 performances)
        recent_performances = db.session.query(
            StudentPerformance, Student, PatientCase
        ).join(Student).join(PatientCase).order_by(
            StudentPerformance.completed_at.desc()
        ).limit(10).all()
        
        recent_activity = []
        for perf, student, case in recent_performances:
            recent_activity.append({
                'date': perf.completed_at.strftime('%d/%m/%Y %H:%M'),
                'student_name': student.name,
                'student_code': student.student_code,
                'case_number': case.case_number,
                'score': perf.percentage_score,
                'status': perf.get_performance_status()
            })
        
        return jsonify({
            'total_stations': total_stations,
            'total_students': total_students,
            'active_sessions': active_sessions,
            'total_consultations': total_consultations,
            'recent_activity': recent_activity
        })
        
    except Exception as e:
        logger.error(f"Error getting admin overview: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@admin_bp.route('/competition-sessions/<int:session_id>/monitor')
@admin_required
def monitor_competition_session(session_id):
    """Real-time monitoring of competition session"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        # Get all student sessions
        student_sessions = StudentCompetitionSession.query.filter_by(
            session_id=session_id
        ).all()
        
        participants_status = []
        for student_session in student_sessions:
            current_assignment = None
            if student_session.current_station_order > 0:
                current_assignment = StudentStationAssignment.query.filter_by(
                    student_session_id=student_session.id,
                    station_order=student_session.current_station_order
                ).first()
            
            participant_data = {
                'student_id': student_session.student_id,
                'student_name': student_session.student.name,
                'student_code': student_session.student.student_code,
                'status': student_session.status,
                'current_station_order': student_session.current_station_order,
                'progress_percentage': student_session.get_progress_percentage(),
                'completed_stations': student_session.get_completed_stations_count(),
                'current_station_case': current_assignment.case_number if current_assignment else None,
                'station_started_at': current_assignment.started_at.isoformat() if current_assignment and current_assignment.started_at else None
            }
            participants_status.append(participant_data)
        
        return jsonify({
            'session_id': session_id,
            'session_name': session.name,
            'session_status': session.status,
            'participants': participants_status,
            'total_participants': len(participants_status),
            'logged_in_count': len([p for p in participants_status if p['status'] in ['logged_in', 'active', 'between_stations', 'completed']]),
            'active_count': len([p for p in participants_status if p['status'] == 'active']),
            'completed_count': len([p for p in participants_status if p['status'] == 'completed'])
        })
        
    except Exception as e:
        logger.error(f"Error monitoring competition session: {str(e)}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/competition-sessions/<int:session_id>/force-start', methods=['POST'])
@admin_required
def force_start_competition(session_id):
    """Force start a competition even if not all participants are ready"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        if session.status != 'scheduled':
            return jsonify({
                "success": False,
                "error": "Only scheduled sessions can be started"
            }), 400
        
        # Get logged in students
        logged_in_students = StudentCompetitionSession.query.filter(
            StudentCompetitionSession.session_id == session_id,
            StudentCompetitionSession.status.in_(['registered', 'logged_in'])
        ).all()
        
        if not logged_in_students:
            return jsonify({
                "success": False,
                "error": "No students are logged in"
            }), 400
        
        # Force start the competition
        success = session.start_competition()
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Competition force-started with {len(logged_in_students)} participants"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to start competition"
            }), 500
        
    except Exception as e:
        logger.error(f"Error force starting competition: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
@admin_bp.route('/competition-sessions/<int:session_id>/pause', methods=['POST'])
@admin_required
def pause_competition(session_id):
    """Pause an active competition"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        if session.status != 'active':
            return jsonify({
                "success": False,
                "error": "Only active sessions can be paused"
            }), 400
        
        # Update session status
        session.status = 'paused'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Competition paused successfully"
        })
        
    except Exception as e:
        logger.error(f"Error pausing competition: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_bp.route('/competition-sessions/<int:session_id>/resume', methods=['POST'])
@admin_required
def resume_competition(session_id):
    """Resume a paused competition"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        if session.status != 'paused':
            return jsonify({
                "success": False,
                "error": "Only paused sessions can be resumed"
            }), 400
        
        # Update session status
        session.status = 'active'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Competition resumed successfully"
        })
        
    except Exception as e:
        logger.error(f"Error resuming competition: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_bp.route('/competition-sessions/<int:session_id>/end', methods=['POST'])
@admin_required
def end_competition(session_id):
    """Manually end a competition"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        if session.status not in ['active', 'paused']:
            return jsonify({
                "success": False,
                "error": "Only active or paused sessions can be ended"
            }), 400
        
        # End all active student sessions
        active_students = StudentCompetitionSession.query.filter(
            StudentCompetitionSession.session_id == session_id,
            StudentCompetitionSession.status.in_(['active', 'between_stations'])
        ).all()
        
        for student_session in active_students:
            student_session.status = 'completed'
            student_session.completed_at = datetime.utcnow()
        
        # Update session status
        session.status = 'completed'
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Competition ended. {len(active_students)} student sessions completed."
        })
        
    except Exception as e:
        logger.error(f"Error ending competition: {str(e)}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
@admin_bp.route('/competition-sessions/<int:session_id>/reset-student/<int:student_id>', methods=['POST'])
@admin_required
def reset_student_competition(session_id, student_id):
    """Reset a student's competition progress"""
    try:
        student_session = StudentCompetitionSession.query.filter_by(
            session_id=session_id,
            student_id=student_id
        ).first()
        
        if not student_session:
            return jsonify({
                "success": False,
                "error": "Student session not found"
            }), 404
        
        # Reset student session
        student_session.status = 'registered'
        student_session.current_station_order = 0
        student_session.started_at = None
        student_session.completed_at = None
        
        # Delete all station assignments
        StudentStationAssignment.query.filter_by(
            student_session_id=student_session.id
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Student competition progress reset successfully"
        })
        
    except Exception as e:
        logger.error(f"Error resetting student competition: {str(e)}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@admin_bp.route('/competition-sessions/<int:session_id>/export-results')
@admin_required
def export_competition_results(session_id):
    """Export competition results as CSV"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        # Get all participants and their results
        participants = StudentCompetitionSession.query.filter_by(
            session_id=session_id
        ).all()
        
        # Create CSV content
        import csv
        import io
        from flask import make_response
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Student Code', 'Student Name', 'Status', 'Total Stations',
            'Completed Stations', 'Average Score', 'Total Score',
            'Started At', 'Completed At', 'Duration (minutes)'
        ])
        
        # Write participant data
        for participant in participants:
            duration = ""
            if participant.started_at and participant.completed_at:
                delta = participant.completed_at - participant.started_at
                duration = str(int(delta.total_seconds() / 60))
            
            writer.writerow([
                participant.student.student_code,
                participant.student.name,
                participant.status,
                session.stations_per_session,
                participant.get_completed_stations_count(),
                participant.get_average_score(),
                participant.get_total_score(),
                participant.started_at.isoformat() if participant.started_at else "",
                participant.completed_at.isoformat() if participant.completed_at else "",
                duration
            ])
        
        # Create response
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=competition_{session_id}_results.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting competition results: {str(e)}")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/stations')
@admin_required
def admin_stations():
    """Get stations data for admin management"""
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
        total_usage = 0
        specialty_count = {}
        
        for case in cases:
            usage_count = case.get_completion_count()
            avg_score = case.get_average_score()
            
            total_usage += usage_count
            
            # Count specialties
            if case.specialty:
                specialty_count[case.specialty] = specialty_count.get(case.specialty, 0) + usage_count
            
            stations.append({
                'case_number': case.case_number,
                'specialty': case.specialty,
                'consultation_time': case.consultation_time,
                'created_at': case.created_at.strftime('%d/%m/%Y'),
                'usage_count': usage_count,
                'average_score': avg_score
            })
        
        # Calculate average score
        avg_score = 0
        if stations:
            total_score = sum(s['average_score'] for s in stations if s['average_score'] > 0)
            stations_with_scores = len([s for s in stations if s['average_score'] > 0])
            if stations_with_scores > 0:
                avg_score = round(total_score / stations_with_scores)
        
        # Get most used specialty
        most_used_specialty = max(specialty_count.items(), key=lambda x: x[1])[0] if specialty_count else 'N/A'
        
        return jsonify({
            'stations': stations,
            'total': len(stations),
            'avg_score': avg_score,
            'most_used_specialty': most_used_specialty
        })
        
    except Exception as e:
        logger.error(f"Error getting admin stations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/students')
@admin_required
def admin_students():
    """Get students data for admin management"""
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
        active_count = 0
        total_score = 0
        students_with_scores = 0
        
        for student in students:
            total_consultations = student.get_total_workouts()
            avg_score = student.get_average_score()
            
            if total_consultations > 0:
                active_count += 1
            
            if avg_score > 0:
                total_score += avg_score
                students_with_scores += 1
            
            student_data.append({
                'id': student.id,
                'student_code': student.student_code,
                'name': student.name,
                'created_at': student.created_at.strftime('%d/%m/%Y'),
                'last_login': student.last_login.strftime('%d/%m/%Y %H:%M') if student.last_login else None,
                'total_consultations': total_consultations,
                'average_score': avg_score
            })
        
        avg_score = round(total_score / students_with_scores) if students_with_scores > 0 else 0
        
        return jsonify({
            'students': student_data,
            'total': len(student_data),
            'active': active_count,
            'avg_score': avg_score
        })
        
    except Exception as e:
        logger.error(f"Error getting admin students: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@admin_bp.route('/students/<int:student_id>/details')
@admin_required
def admin_student_details(student_id):
    """Get detailed information for a specific student"""
    try:
        student = Student.query.get_or_404(student_id)
        
        # Get student performances
        performances = StudentPerformance.query.filter_by(student_id=student_id)\
            .order_by(StudentPerformance.completed_at.desc()).all()
        
        performance_data = []
        for perf in performances:
            case = PatientCase.query.filter_by(case_number=perf.case_number).first()
            performance_data.append({
                'id': perf.id,
                'case_number': perf.case_number,
                'specialty': case.specialty if case else 'Unknown',
                'score': perf.percentage_score,
                'grade': perf.get_performance_grade(),
                'completed_at': perf.completed_at.strftime('%d/%m/%Y %H:%M'),
                'duration': f"{perf.consultation_duration // 60}:{perf.consultation_duration % 60:02d}" if perf.consultation_duration else "N/A"
            })
        
        return jsonify({
            'total_consultations': student.get_total_workouts(),
            'unique_stations': student.get_unique_stations_played(),
            'average_score': student.get_average_score(),
            'performances': performance_data
        })
        
    except Exception as e:
        logger.error(f"Error getting student details: {str(e)}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/sessions')
@admin_required
def admin_sessions():
    """Get OSCE sessions for admin management"""
    try:
        sessions = OSCESession.query.order_by(OSCESession.created_at.desc()).all()
        
        session_data = []
        total_sessions = len(sessions)
        scheduled_count = 0
        active_count = 0
        
        for session in sessions:
            if session.status == 'scheduled':
                scheduled_count += 1
            elif session.status == 'active':
                active_count += 1
            
            session_data.append({
                'id': session.id,
                'name': session.name,
                'start_time': session.start_time.strftime('%d/%m/%Y %H:%M'),
                'end_time': session.end_time.strftime('%d/%m/%Y %H:%M'),
                'participant_count': session.get_participant_count(),
                'station_count': session.get_assigned_stations_count(),
                'status': session.status,
                'status_display': session.get_status_display()
            })
        
        return jsonify({
            'sessions': session_data,
            'total': total_sessions,
            'scheduled': scheduled_count,
            'active': active_count
        })
        
    except Exception as e:
        logger.error(f"Error getting admin sessions: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@admin_bp.route('/available-students')
@admin_required
def admin_available_students():
    """Get list of students available for session assignment"""
    try:
        students = Student.query.order_by(Student.name).all()
        
        student_data = []
        for student in students:
            student_data.append({
                'id': student.id,
                'name': student.name,
                'student_code': student.student_code
            })
        
        return jsonify({'students': student_data})
        
    except Exception as e:
        logger.error(f"Error getting available students: {str(e)}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/available-stations')
@admin_required
def admin_available_stations():
    """Get list of stations available for session assignment"""
    try:
        cases = PatientCase.query.order_by(PatientCase.case_number).all()
        
        station_data = []
        for case in cases:
            station_data.append({
                'case_number': case.case_number,
                'specialty': case.specialty,
                'consultation_time': case.consultation_time
            })
        
        return jsonify({'stations': station_data})
        
    except Exception as e:
        logger.error(f"Error getting available stations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/create-session', methods=['POST'])
@admin_required
def admin_create_session():
    """Create a new OSCE session with enhanced error handling"""
    try:
        data = request.get_json()
        logger.info(f"Received session creation request: {data}")
        
        # Validate that we have JSON data
        if not data:
            logger.error("No JSON data received")
            return jsonify({"error": "No data received", "success": False}), 400
        
        # Validate required fields
        required_fields = ['name', 'start_time', 'end_time']
        missing_fields = []
        
        for field in required_fields:
            if not data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate datetime format
        try:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            logger.info(f"Parsed times - Start: {start_time}, End: {end_time}")
        except ValueError as e:
            error_msg = f"Invalid datetime format: {str(e)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate time logic
        if start_time >= end_time:
            error_msg = "Start time must be before end time"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate participants and stations
        participant_ids = data.get('participants', [])
        station_numbers = data.get('stations', [])
        
        logger.info(f"Participants: {participant_ids}, Stations: {station_numbers}")
        
        # Validate that participant IDs exist
        if participant_ids:
            existing_students = Student.query.filter(Student.id.in_(participant_ids)).all()
            existing_student_ids = [s.id for s in existing_students]
            invalid_student_ids = [pid for pid in participant_ids if pid not in existing_student_ids]
            
            if invalid_student_ids:
                error_msg = f"Invalid student IDs: {invalid_student_ids}"
                logger.error(error_msg)
                return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate that station numbers exist
        if station_numbers:
            existing_cases = PatientCase.query.filter(PatientCase.case_number.in_(station_numbers)).all()
            existing_case_numbers = [c.case_number for c in existing_cases]
            invalid_case_numbers = [sn for sn in station_numbers if sn not in existing_case_numbers]
            
            if invalid_case_numbers:
                error_msg = f"Invalid station numbers: {invalid_case_numbers}"
                logger.error(error_msg)
                return jsonify({"error": error_msg, "success": False}), 400
        
        # Create session
        session = OSCESession(
            name=data['name'],
            description=data.get('description', ''),
            start_time=start_time,
            end_time=end_time,
            created_by='admin',
            status='scheduled'
        )
        
        db.session.add(session)
        db.session.flush()  # Get the session ID
        
        logger.info(f"Created session with ID: {session.id}")
        
        # Add participants
        participants_added = 0
        for student_id in participant_ids:
            try:
                participant = SessionParticipant(
                    session_id=session.id,
                    student_id=student_id
                )
                db.session.add(participant)
                participants_added += 1
            except Exception as e:
                logger.error(f"Error adding participant {student_id}: {str(e)}")
        
        # Add stations
        stations_added = 0
        for i, case_number in enumerate(station_numbers):
            try:
                assignment = SessionStationAssignment(
                    session_id=session.id,
                    case_number=case_number,
                    station_order=i + 1
                )
                db.session.add(assignment)
                stations_added += 1
            except Exception as e:
                logger.error(f"Error adding station {case_number}: {str(e)}")
        
        db.session.commit()
        
        logger.info(f"Session created successfully - ID: {session.id}, Participants: {participants_added}, Stations: {stations_added}")
        
        return jsonify({
            "success": True, 
            "session_id": session.id,
            "participants_added": participants_added,
            "stations_added": stations_added
        })
        
    except Exception as e:
        logger.error(f"Unexpected error creating session: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": f"Internal server error: {str(e)}", "success": False}), 500

@admin_bp.route('/download_student_report/<int:performance_id>')
@admin_required
def admin_download_student_report(performance_id):
    """Download student performance report (admin version)"""
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
            download_name=f"admin_student_report_{performance.student.student_code}_case_{case_number}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        logger.error(f"Error generating admin student report PDF for performance ID {performance_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Erreur lors de la génération du rapport PDF"}), 500
    
@admin_bp.route('/competition-sessions')
@admin_required
def admin_competition_sessions():
    """Get competition sessions for admin management"""
    try:
        sessions = CompetitionSession.query.order_by(CompetitionSession.created_at.desc()).all()
        
        session_data = []
        total_sessions = len(sessions)
        scheduled_count = 0
        active_count = 0
        
        for session in sessions:
            if session.status == 'scheduled':
                scheduled_count += 1
            elif session.status == 'active':
                active_count += 1
            
            # Check if competition can start
            logged_in_count = StudentCompetitionSession.query.filter_by(
                session_id=session.id,
                status='logged_in'
            ).count()
            
            total_participants = session.get_participant_count()
            station_count = session.get_assigned_stations_count()
            
            can_start = (logged_in_count >= total_participants and 
                        total_participants > 0 and 
                        station_count >= session.stations_per_session and
                        session.status == 'scheduled')
            
            session_data.append({
                'id': session.id,
                'name': session.name,
                'start_time': session.start_time.strftime('%d/%m/%Y %H:%M'),
                'end_time': session.end_time.strftime('%d/%m/%Y %H:%M'),
                'participant_count': session.get_participant_count(),
                'station_count': session.get_assigned_stations_count(),
                'stations_per_session': session.stations_per_session,
                'time_per_station': session.time_per_station,
                'status': session.status,
                'status_display': session.get_status_display(),
                'can_start': can_start
            })
        
        return jsonify({
            'sessions': session_data,
            'total': total_sessions,
            'scheduled': scheduled_count,
            'active': active_count
        })
        
    except Exception as e:
        logger.error(f"Error getting admin competition sessions: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@admin_bp.route('/competition-sessions/<int:session_id>')
@admin_required
def admin_competition_session_details(session_id):
    """Get detailed information for a specific competition session"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        # Get participants with their current status
        participants_data = []
        for participant in session.participants:
            student_session = StudentCompetitionSession.query.filter_by(
                session_id=session_id,
                student_id=participant.student_id
            ).first()
            
            if student_session:
                current_station = f"{student_session.current_station_order}"
                progress = student_session.get_progress_percentage()
                status = student_session.status
            else:
                current_station = "0"
                progress = 0
                status = "registered"
            
            participants_data.append({
                'id': participant.student.id,
                'name': participant.student.name,
                'student_code': participant.student.student_code,
                'status': status,
                'current_station': current_station,
                'progress': progress
            })
        
        # Get stations in the bank
        stations_data = []
        for station_assignment in session.station_assignments:
            case = PatientCase.query.filter_by(case_number=station_assignment.case_number).first()
            if case:
                stations_data.append({
                    'case_number': case.case_number,
                    'specialty': case.specialty,
                    'consultation_time': case.consultation_time
                })
        
        # Get leaderboard if session is completed or active
        leaderboard = []
        if session.status in ['active', 'completed']:
            leaderboard = session.get_leaderboard()
        
        return jsonify({
            'id': session.id,
            'name': session.name,
            'description': session.description,
            'start_time': session.start_time.strftime('%d/%m/%Y %H:%M'),
            'end_time': session.end_time.strftime('%d/%m/%Y %H:%M'),
            'status': session.status,
            'status_display': session.get_status_display(),
            'stations_per_session': session.stations_per_session,
            'time_per_station': session.time_per_station,
            'time_between_stations': session.time_between_stations,
            'randomize_stations': session.randomize_stations,
            'participants': participants_data,
            'stations': stations_data,
            'leaderboard': leaderboard
        })
        
    except Exception as e:
        logger.error(f"Error getting competition session details: {str(e)}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/create-competition-session', methods=['POST'])
@admin_required
def admin_create_competition_session():
    """Create a new competition session"""
    try:
        data = request.get_json()
        logger.info(f"Received competition session creation request: {data}")
        
        # Validate that we have JSON data
        if not data:
            logger.error("No JSON data received")
            return jsonify({"error": "No data received", "success": False}), 400
        
        # Validate required fields
        required_fields = ['name', 'start_time', 'end_time', 'stations_per_session', 'time_per_station']
        missing_fields = []
        
        for field in required_fields:
            if not data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate datetime format
        try:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            logger.info(f"Parsed times - Start: {start_time}, End: {end_time}")
        except ValueError as e:
            error_msg = f"Invalid datetime format: {str(e)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate time logic
        if start_time >= end_time:
            error_msg = "Start time must be before end time"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate participants and stations
        participant_ids = data.get('participants', [])
        station_numbers = data.get('stations', [])
        
        logger.info(f"Participants: {participant_ids}, Stations: {station_numbers}")
        
        # Validate that participant IDs exist
        if participant_ids:
            existing_students = Student.query.filter(Student.id.in_(participant_ids)).all()
            existing_student_ids = [s.id for s in existing_students]
            invalid_student_ids = [pid for pid in participant_ids if pid not in existing_student_ids]
            
            if invalid_student_ids:
                error_msg = f"Invalid student IDs: {invalid_student_ids}"
                logger.error(error_msg)
                return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate that station numbers exist
        if station_numbers:
            existing_cases = PatientCase.query.filter(PatientCase.case_number.in_(station_numbers)).all()
            existing_case_numbers = [c.case_number for c in existing_cases]
            invalid_case_numbers = [sn for sn in station_numbers if sn not in existing_case_numbers]
            
            if invalid_case_numbers:
                error_msg = f"Invalid station numbers: {invalid_case_numbers}"
                logger.error(error_msg)
                return jsonify({"error": error_msg, "success": False}), 400
        
        # Validate that we have enough stations
        if len(station_numbers) < data['stations_per_session']:
            error_msg = f"Station bank must contain at least {data['stations_per_session']} stations"
            logger.error(error_msg)
            return jsonify({"error": error_msg, "success": False}), 400
        
        # Create competition session
        session = CompetitionSession(
            name=data['name'],
            description=data.get('description', ''),
            start_time=start_time,
            end_time=end_time,
            stations_per_session=data['stations_per_session'],
            time_per_station=data['time_per_station'],
            time_between_stations=data.get('time_between_stations', 2),
            randomize_stations=data.get('randomize_stations', True),
            created_by='admin',
            status='scheduled'
        )
        
        db.session.add(session)
        db.session.flush()  # Get the session ID
        
        logger.info(f"Created competition session with ID: {session.id}")
        
        # Add participants
        participants_added = 0
        for student_id in participant_ids:
            try:
                participant = CompetitionParticipant(
                    session_id=session.id,
                    student_id=student_id
                )
                db.session.add(participant)
                
                # Also create a StudentCompetitionSession record
                student_session = StudentCompetitionSession(
                    session_id=session.id,
                    student_id=student_id,
                    status='registered'
                )
                db.session.add(student_session)
                
                participants_added += 1
            except Exception as e:
                logger.error(f"Error adding participant {student_id}: {str(e)}")
        
        # Add stations to bank
        stations_added = 0
        for case_number in station_numbers:
            try:
                station_assignment = CompetitionStationBank(
                    session_id=session.id,
                    case_number=case_number
                )
                db.session.add(station_assignment)
                stations_added += 1
            except Exception as e:
                logger.error(f"Error adding station {case_number}: {str(e)}")
        
        db.session.commit()
        
        logger.info(f"Competition session created successfully - ID: {session.id}, Participants: {participants_added}, Stations: {stations_added}")
        
        return jsonify({
            "success": True, 
            "session_id": session.id,
            "participants_added": participants_added,
            "stations_added": stations_added
        })
        
    except Exception as e:
        logger.error(f"Unexpected error creating competition session: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": f"Internal server error: {str(e)}", "success": False}), 500

@admin_bp.route('/competition-sessions/<int:session_id>/start', methods=['POST'])
@admin_required
def admin_start_competition(session_id):
    """Start a competition session"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        if session.status != 'scheduled':
            return jsonify({
                "success": False,
                "error": "Only scheduled sessions can be started"
            }), 400
        
        if not session.can_start_competition():
            return jsonify({
                "success": False,
                "error": "Cannot start competition: not all participants are logged in or insufficient stations"
            }), 400
        
        # Start the competition
        success = session.start_competition()
        
        if success:
            return jsonify({
                "success": True,
                "message": "Competition started successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to start competition"
            }), 500
        
    except Exception as e:
        logger.error(f"Error starting competition: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_bp.route('/competition-sessions/<int:session_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_competition_session(session_id):
    """Edit a competition session"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        if request.method == 'GET':
            # Return session data for editing
            participants = [p.student_id for p in session.participants]
            stations = [s.case_number for s in session.station_assignments]
            
            return jsonify({
                'id': session.id,
                'name': session.name,
                'description': session.description,
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat(),
                'stations_per_session': session.stations_per_session,
                'time_per_station': session.time_per_station,
                'time_between_stations': session.time_between_stations,
                'randomize_stations': session.randomize_stations,
                'participants': participants,
                'stations': stations
            })
        
        elif request.method == 'POST':
            # Update session
            data = request.get_json()
            
            # Only allow editing if session is still scheduled
            if session.status != 'scheduled':
                return jsonify({
                    "success": False,
                    "error": "Only scheduled sessions can be edited"
                }), 400
            
            # Update basic fields
            session.name = data.get('name', session.name)
            session.description = data.get('description', session.description)
            
            # Update datetime fields
            if data.get('start_time'):
                session.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            if data.get('end_time'):
                session.end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            
            # Update competition settings
            session.stations_per_session = data.get('stations_per_session', session.stations_per_session)
            session.time_per_station = data.get('time_per_station', session.time_per_station)
            session.time_between_stations = data.get('time_between_stations', session.time_between_stations)
            session.randomize_stations = data.get('randomize_stations', session.randomize_stations)
            
            # Update participants
            if 'participants' in data:
                # Remove existing participants
                CompetitionParticipant.query.filter_by(session_id=session_id).delete()
                StudentCompetitionSession.query.filter_by(session_id=session_id).delete()
                
                # Add new participants
                for student_id in data['participants']:
                    participant = CompetitionParticipant(
                        session_id=session_id,
                        student_id=student_id
                    )
                    db.session.add(participant)
                    
                    student_session = StudentCompetitionSession(
                        session_id=session_id,
                        student_id=student_id,
                        status='registered'
                    )
                    db.session.add(student_session)
            
            # Update stations
            if 'stations' in data:
                # Remove existing stations
                CompetitionStationBank.query.filter_by(session_id=session_id).delete()
                
                # Add new stations
                for case_number in data['stations']:
                    station_assignment = CompetitionStationBank(
                        session_id=session_id,
                        case_number=case_number
                    )
                    db.session.add(station_assignment)
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "Competition session updated successfully"
            })
        
    except Exception as e:
        logger.error(f"Error editing competition session: {str(e)}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@admin_bp.route('/competition-sessions/<int:session_id>/delete', methods=['DELETE'])
@admin_required
def admin_delete_competition_session(session_id):
    """Delete a competition session"""
    try:
        session = CompetitionSession.query.get_or_404(session_id)
        
        # Only allow deletion of scheduled sessions
        if session.status not in ['scheduled', 'completed', 'cancelled']:
            return jsonify({
                "success": False,
                "error": "Cannot delete active sessions"
            }), 400
        
        # Delete the session (cascade will handle related records)
        db.session.delete(session)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Competition session deleted successfully"
        })
        
    except Exception as e:
        logger.error(f"Error deleting competition session: {str(e)}")
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500