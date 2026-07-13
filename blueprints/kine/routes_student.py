from datetime import datetime, timedelta

from flask import current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from auth import student_required
from kine_patient_engine import KinePatientEngine
from kine_evaluation import evaluate_kine_conversation
from models import Exam, PatientCase, SimulationSession, db
from progression_tracker import NavigationLockedError, ProgressionTracker
from timeline_logger import append_timeline_event, format_timeline

from . import kine_bp
from .common import canonicalize_medical_tests, error, payload, prune_empty, wants_json


def _student_can_access_case(case):
    return case.specialty == 'kine' and not case.is_archived and case.level in ('both', current_user.level or 'licence')


def _student_has_exam_access(exam, student):
    return student in exam.students or bool(student.group_name and student.group_name in (exam.group_names or []))


def _session_or_404(session_id):
    return SimulationSession.query.filter_by(id=session_id, student_id=current_user.id).first_or_404()


def _expire_exam_session(simulation):
    if simulation.mode != 'exam' or not simulation.exam or simulation.status != 'in_progress':
        return False
    deadline = min(
        simulation.exam.end_at,
        simulation.started_at + timedelta(minutes=simulation.exam.max_duration_minutes),
    )
    if datetime.utcnow() >= deadline:
        _complete_simulation(simulation, completed_at=deadline, auto_closed=True)
        return True
    return False


@kine_bp.before_request
def auto_close_expired_exam_sessions():
    """Per-request server-side expiry sweep; never relies on browser timers."""
    now = datetime.utcnow()
    active_sessions = SimulationSession.query.filter_by(mode='exam', status='in_progress').all()
    changed = False
    for simulation in active_sessions:
        if not simulation.exam:
            continue
        deadline = min(
            simulation.exam.end_at,
            simulation.started_at + timedelta(minutes=simulation.exam.max_duration_minutes),
        )
        if now >= deadline:
            _complete_simulation(simulation, completed_at=deadline, auto_closed=True, commit=False)
            changed = True
    if changed:
        db.session.commit()


def _record_json(record, level):
    medications = []
    for medication in record.medications:
        item = {'therapeutic_class': medication.therapeutic_class}
        if level == 'licence':
            item.update({'inn': medication.inn, 'effect': medication.effect,
                         'physiotherapy_precautions': medication.physiotherapy_precautions})
        medications.append(item)
    return {
        'identity': record.identity, 'medical_context': record.medical_context,
        'medical_history': record.medical_history, 'comorbidities': record.comorbidities,
        'tests': record.tests, 'reference_vitals': record.reference_vitals,
        'medical_prescription': record.medical_prescription,
        'physiotherapy_prescription': record.physiotherapy_prescription,
        'available_documents': record.available_documents,
        'interventions': [{'type': item.intervention_type, 'date': item.intervention_date.isoformat() if item.intervention_date else None,
                           'complications': item.complications} for item in record.interventions],
        'medications': medications,
    }


@kine_bp.route('/student')
@student_required
def student_kine_home():
    level = current_user.level or 'licence'
    cases = PatientCase.query.filter(
        PatientCase.specialty == 'kine',
        PatientCase.is_archived.is_(False),
        PatientCase.level.in_(['both', level]),
        PatientCase.mode_availability.in_(['both', 'training']),
    ).order_by(PatientCase.case_number).all()
    now = datetime.utcnow()
    assigned_exams = Exam.query.filter(Exam.end_at >= now).order_by(Exam.start_at).all()
    assigned_exams = [exam for exam in assigned_exams if _student_has_exam_access(exam, current_user)]
    exam_ids = [exam.id for exam in assigned_exams]
    attempts = SimulationSession.query.filter(
        SimulationSession.student_id == current_user.id,
        SimulationSession.exam_id.in_(exam_ids),
    ).all() if exam_ids else []
    attempts_by_exam_case = {
        (attempt.exam_id, attempt.clinical_case_id): attempt for attempt in attempts
    }
    exam_rows = []
    for exam in assigned_exams:
        compatible_cases = [
            case for case in exam.cases
            if _student_can_access_case(case) and case.mode_availability in ('exam', 'both')
        ]
        exam_rows.append({
            'exam': exam, 'cases': compatible_cases,
            'is_open': exam.start_at <= now <= exam.end_at,
            'is_upcoming': now < exam.start_at,
            'attempts': {
                case.id: attempts_by_exam_case.get((exam.id, case.id))
                for case in compatible_cases
            },
        })
    return render_template('student_kine_home.html', cases=cases, exam_rows=exam_rows,
                           student_level=level, student_name=current_user.name)


def _evaluation_case_data(simulation):
    case = simulation.clinical_case
    record = case.patient_record
    return {
        'case_number': case.case_number, 'specialty': 'kine',
        'diagnosis': case.diagnosis, 'student': simulation.student,
        'patient_record': _record_json(record, simulation.student.level or 'licence') if record else {},
    }


def _complete_simulation(simulation, completed_at=None, auto_closed=False, commit=True):
    if simulation.evaluation_results:
        return simulation.evaluation_results
    evaluation = evaluate_kine_conversation(
        simulation.conversation or [], _evaluation_case_data(simulation),
        current_app.config.get('GROQ_CLIENT'),
    )
    simulation.evaluation_results = evaluation
    simulation.eliminatory_error_triggered = evaluation.get('eliminatory_error_triggered', False)
    simulation.eliminatory_error = '; '.join(
        error.get('description') or error.get('id', '')
        for error in evaluation.get('eliminatory_errors', [])
    ) or None
    simulation.status = 'completed'
    simulation.current_phase = 11
    simulation.completed_at = completed_at or datetime.utcnow()
    if auto_closed:
        append_timeline_event(simulation, 'exam_auto_closed', actor='system', timestamp=simulation.completed_at)
    append_timeline_event(simulation, 'simulation_completed', actor='system', phase=11,
                          details={'score': evaluation.get('points_earned'), 'passed': evaluation.get('passed')},
                          timestamp=simulation.completed_at)
    if commit:
        db.session.commit()
    return evaluation


@kine_bp.route('/cases/<int:case_id>/patient-record')
@student_required
def patient_record_view(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if not _student_can_access_case(case):
        return error('This case is not available for your level', 403)
    if not case.patient_record:
        return error('Patient record is not configured', 404)
    if wants_json():
        return jsonify(_record_json(case.patient_record, current_user.level or 'licence'))
    record = case.patient_record
    display_record = {
        'identity': prune_empty(record.identity or {}) or {},
        'medical_context': prune_empty(record.medical_context or {}) or {},
        'medical_history': prune_empty(record.medical_history or {}) or {},
        'comorbidities': prune_empty(record.comorbidities or []) or [],
        'tests': prune_empty(canonicalize_medical_tests(record.tests or {})) or {},
        'reference_vitals': prune_empty(record.reference_vitals or {}) or {},
        'medical_prescription': prune_empty(record.medical_prescription),
        'physiotherapy_prescription': prune_empty(record.physiotherapy_prescription),
        'available_documents': prune_empty(record.available_documents or []) or [],
        'interventions': record.interventions,
        'medications': record.medications,
    }
    return render_template(
        'patient_record.html', clinical_case=case, patient_record=display_record,
        student_level=current_user.level or 'licence',
        start_simulation_url=url_for('kine.start_simulation'),
    )


@kine_bp.route('/simulation/start', methods=['POST'])
@student_required
def start_simulation():
    data = payload()
    try:
        case_id = int(data.get('case_id'))
    except (TypeError, ValueError):
        return error('Valid case_id is required')
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if not _student_can_access_case(case):
        return error('This case is not available for your level', 403)
    mode = str(data.get('mode') or 'training').lower()
    if mode not in ('training', 'exam') or case.mode_availability not in ('both', mode):
        return error('Requested mode is not available for this case', 403)
    exam = None
    if mode == 'exam':
        try:
            exam = Exam.query.get(int(data.get('exam_id')))
        except (TypeError, ValueError):
            exam = None
        now = datetime.utcnow()
        if not exam or not _student_has_exam_access(exam, current_user) or case not in exam.cases:
            return error('Student or case is not authorized for this exam', 403)
        if not exam.start_at <= now <= exam.end_at:
            return error('Exam is not currently open', 403)
        previous_attempt = SimulationSession.query.filter_by(
            student_id=current_user.id,
            exam_id=exam.id,
            clinical_case_id=case.id,
        ).first()
        if previous_attempt:
            return error(
                "Ce cas d’examen a déjà été commencé. Une seule tentative est autorisée.",
                409,
            )
    simulation = SimulationSession(
        student_id=current_user.id, clinical_case_id=case.id, exam=exam,
        mode=mode, status='in_progress', current_phase=1,
        phase_timings={}, timeline=[],
        conversation=[], runtime_state={},
    )
    append_timeline_event(simulation, 'simulation_started', phase=1,
                          details={'case_id': case.id, 'mode': mode})
    db.session.add(simulation)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error(
            "Ce cas d’examen a déjà été commencé. Une seule tentative est autorisée.",
            409,
        )
    result = {'simulation_id': simulation.id, 'case_id': case.id, 'mode': mode,
              'progress': ProgressionTracker(simulation).to_frontend()}
    if exam:
        deadline = min(exam.end_at, simulation.started_at + timedelta(minutes=exam.max_duration_minutes))
        result['deadline'] = deadline.isoformat() + 'Z'
    if wants_json():
        return jsonify(result), 201
    return redirect(url_for('kine.simulation_chat', session_id=simulation.id))


@kine_bp.route('/simulation/<int:session_id>/chat')
@student_required
def simulation_chat(session_id):
    simulation = _session_or_404(session_id)
    _expire_exam_session(simulation)
    display_phase = 11 if simulation.status == 'completed' and simulation.current_phase == 10 else simulation.current_phase
    deadline = None
    if simulation.mode == 'exam' and simulation.exam:
        deadline = min(simulation.exam.end_at,
                       simulation.started_at + timedelta(minutes=simulation.exam.max_duration_minutes))
    return render_template(
        'chat_kine.html', simulation=simulation, clinical_case=simulation.clinical_case,
        conversation=simulation.conversation or [], evaluation=simulation.evaluation_results,
        simulation_mode=simulation.mode, current_phase=display_phase,
        progress_url=url_for('kine.simulation_progress', session_id=simulation.id),
        message_url=url_for('kine.simulation_message', session_id=simulation.id),
        test_url=url_for('kine.simulation_test_request', session_id=simulation.id),
        pause_url=url_for('kine.pause_simulation', session_id=simulation.id),
        resume_url=url_for('kine.resume_simulation', session_id=simulation.id),
        complete_url=url_for('kine.complete_simulation', session_id=simulation.id),
        record_url=url_for('kine.patient_record_view', case_id=simulation.clinical_case_id),
        timeline_url=url_for('kine.simulation_timeline', session_id=simulation.id),
        deadline=(deadline.isoformat() + 'Z') if deadline else None,
    )


def _process_message(simulation, message):
    if simulation.status != 'in_progress':
        return error('Simulation is not in progress', 409)
    if _expire_exam_session(simulation):
        return error('Exam time has expired', 409)
    if not message:
        return error('Message is required')
    conversation = list(simulation.conversation or [])
    conversation.append({'role': 'human', 'content': message, 'timestamp': datetime.utcnow().isoformat()})
    runtime_state = dict(simulation.runtime_state or {})
    engine = KinePatientEngine(
        simulation.clinical_case, simulation.clinical_case.patient_record,
        current_app.config.get('GROQ_CLIENT'), runtime_state,
    )
    response = engine.respond(message, simulation.current_phase, conversation[:-1])
    conversation.append({'role': 'assistant', 'content': response['content'],
                         'type': response['type'], 'timestamp': datetime.utcnow().isoformat()})
    append_timeline_event(simulation, 'student_message', phase=simulation.current_phase, details=message)
    if response['type'] in ('test_result', 'test_result_unavailable'):
        append_timeline_event(simulation, 'test_requested', phase=simulation.current_phase,
                              details=response.get('test') or {'available': False})
    if response['type'] == 'incident':
        append_timeline_event(simulation, 'incident_triggered', actor='system',
                              phase=simulation.current_phase,
                              incident_id=response.get('incident_id'), severity=response.get('severity'))
    if response['type'] == 'safety_guardrail':
        append_timeline_event(simulation, 'safety_guardrail_triggered', actor='system',
                              phase=simulation.current_phase,
                              details={'reason': response.get('guardrail')})
    simulation.conversation = conversation
    simulation.runtime_state = runtime_state
    db.session.commit()
    return jsonify({'response': response, 'progress': ProgressionTracker(simulation).to_frontend()})


@kine_bp.route('/simulation/<int:session_id>/message', methods=['POST'])
@student_required
def simulation_message(session_id):
    return _process_message(_session_or_404(session_id), str(payload().get('message') or '').strip())


@kine_bp.route('/simulation/<int:session_id>/test-request', methods=['POST'])
@student_required
def simulation_test_request(session_id):
    data = payload()
    message = str(data.get('message') or '').strip()
    if not message and data.get('test'):
        message = f"I am going to perform the {data.get('test')} test"
    return _process_message(_session_or_404(session_id), message)


@kine_bp.route('/simulation/<int:session_id>/pause', methods=['POST'])
@student_required
def pause_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.mode != 'training':
        return error('Exam sessions cannot be paused', 409)
    if simulation.status != 'in_progress':
        return error('Only an active simulation can be paused', 409)
    simulation.status = 'paused'; simulation.paused_at = datetime.utcnow()
    append_timeline_event(simulation, 'simulation_paused', phase=simulation.current_phase)
    db.session.commit()
    return jsonify({'status': simulation.status, 'paused_at': simulation.paused_at.isoformat()})


@kine_bp.route('/simulation/<int:session_id>/resume', methods=['POST'])
@student_required
def resume_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.mode != 'training' or simulation.status != 'paused':
        return error('Only a paused training simulation can be resumed', 409)
    now = datetime.utcnow()
    if simulation.paused_at:
        simulation.total_paused_seconds = (simulation.total_paused_seconds or 0) + max(
            0, round((now - simulation.paused_at).total_seconds())
        )
    simulation.paused_at = None; simulation.status = 'in_progress'
    append_timeline_event(simulation, 'simulation_resumed', phase=simulation.current_phase)
    db.session.commit()
    return jsonify({'status': simulation.status, 'total_paused_seconds': simulation.total_paused_seconds})


@kine_bp.route('/simulation/<int:session_id>/complete', methods=['POST'])
@student_required
def complete_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.status not in ('in_progress', 'paused'):
        if simulation.evaluation_results:
            return jsonify({'evaluation': simulation.evaluation_results, 'status': simulation.status})
        return error('Simulation cannot be completed', 409)
    if simulation.status == 'paused' and simulation.paused_at:
        simulation.total_paused_seconds = (simulation.total_paused_seconds or 0) + max(
            0, round((datetime.utcnow() - simulation.paused_at).total_seconds())
        )
        simulation.paused_at = None
    evaluation = _complete_simulation(simulation)
    return jsonify({'evaluation': evaluation, 'status': simulation.status,
                    'timeline_url': url_for('kine.simulation_timeline', session_id=simulation.id)})


@kine_bp.route('/simulation/<int:session_id>/progress', methods=['GET', 'POST'])
@student_required
def simulation_progress(session_id):
    simulation = _session_or_404(session_id)
    if _expire_exam_session(simulation):
        return error('Exam time has expired', 409)
    tracker = ProgressionTracker(simulation)
    if request.method == 'POST':
        if simulation.status != 'in_progress':
            return error('Progression is available only while the simulation is active', 409)
        try:
            state = tracker.navigate_to(payload().get('phase'))
            db.session.commit()
        except (ValueError, NavigationLockedError) as exc:
            db.session.rollback()
            append_timeline_event(simulation, 'phase_navigation_denied', phase=simulation.current_phase,
                                  details={'requested_phase': payload().get('phase'), 'reason': str(exc)})
            db.session.commit()
            return error(str(exc), 409)
        return jsonify(state)
    return jsonify(tracker.to_frontend())


@kine_bp.route('/simulation/<int:session_id>/timeline')
@student_required
def simulation_timeline(session_id):
    simulation = _session_or_404(session_id)
    timezone_name = request.args.get('timezone', 'Africa/Casablanca')
    formatted = format_timeline(simulation.timeline or [], timezone_name)
    if wants_json():
        return jsonify({'simulation_id': simulation.id, 'timeline': formatted,
                        'event_count': len(formatted), 'timezone': formatted[0]['timezone'] if formatted else timezone_name,
                        'phase_timings': simulation.phase_timings or {},
                        'supplementary_score': simulation.supplementary_score,
                        'teacher_comments': simulation.teacher_comments,
                        'reviewed_at': simulation.reviewed_at.isoformat() + 'Z' if simulation.reviewed_at else None})
    return render_template('timeline_view.html', simulation=simulation, student=current_user,
                           timeline=formatted)


@kine_bp.route('/history')
@student_required
def simulation_history():
    sessions = SimulationSession.query.filter_by(student_id=current_user.id).order_by(SimulationSession.started_at.desc()).all()
    history = [{
        'id': item.id, 'case_id': item.clinical_case_id, 'case_number': item.clinical_case.case_number,
        'mode': item.mode, 'status': item.status, 'current_phase': item.current_phase,
        'started_at': item.started_at.isoformat(), 'completed_at': item.completed_at.isoformat() if item.completed_at else None,
        'evaluation_results': item.evaluation_results,
        'supplementary_score': item.supplementary_score,
        'teacher_comments': item.teacher_comments,
        'reviewed_at': item.reviewed_at.isoformat() + 'Z' if item.reviewed_at else None,
        'chat_url': url_for('kine.simulation_chat', session_id=item.id),
        'timeline_url': url_for('kine.simulation_timeline', session_id=item.id),
    } for item in sessions]
    if wants_json():
        return jsonify({'sessions': history})
    return render_template('student_history_kine.html', sessions=history)
