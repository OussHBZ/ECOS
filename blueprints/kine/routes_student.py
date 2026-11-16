import json
import hashlib
import os
import tempfile
from datetime import datetime, timedelta

from flask import current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from auth import student_required
from case_versions import (freeze_simulation, selected_exam_version, simulation_case,
                           simulation_student, training_version, version_metadata,
                           version_view)
from information_access import (
    AmbiguousQuestion, disclosed_ids, effective_mode, format_information_value,
    information_payload, student_information_payload, matching_examination_information,
    matching_question_information, record_disclosure,
    record_initial_disclosures, record_projection, redact_reserved,
)
from kine_patient_engine import KinePatientEngine
from kine_patient_engine import KinePatientEngine as PatientSafety
from patient_personality import style_patient_fact
from kine_evaluation import evaluate_kine_conversation, FrozenEvaluationUnavailable
from criterion_evaluation import evaluate as evaluate_criteria, ENGINE
from evaluation_lifecycle import (deadline as exam_deadline, student_result, student_simulation,
                                  student_timeline, feedback_allowed, record_change)
from models import (Exam, KineCaseAvailability, KineCaseDocument, PatientCase,
                    SimulationSession, db)
from progression_tracker import NavigationLockedError, ProgressionTracker
from timeline_logger import append_timeline_event, format_timeline

from . import kine_bp
from .common import error, payload, prune_empty, wants_json
from kine_transitions import claim, TransitionConflict


@kine_bp.errorhandler(TransitionConflict)
def transition_conflict(exc):
    db.session.rollback()
    return error(str(exc), 409)


@kine_bp.errorhandler(FrozenEvaluationUnavailable)
def frozen_evaluation_unavailable(exc):
    db.session.rollback()
    return error(str(exc), 409)


def _student_can_access_case(case):
    return case.specialty == 'kine' and not case.is_archived and case.level in ('both', current_user.level or 'licence')


def _student_has_exam_access(exam, student):
    return student in exam.students or bool(student.group_name and student.group_name in (exam.group_names or []))


def _session_or_404(session_id):
    return SimulationSession.query.join(PatientCase).filter(SimulationSession.id == session_id, SimulationSession.student_id == current_user.id, PatientCase.specialty == 'kine').first_or_404()


def _progression(simulation):
    """Build progression exclusively from the persisted session Student."""
    return ProgressionTracker(simulation, student=simulation_student(simulation))


def _expire_exam_session(simulation):
    if simulation.mode != 'exam' or simulation.status != 'in_progress':
        return False
    deadline = exam_deadline(simulation)
    if datetime.utcnow() >= deadline:
        _complete_simulation(simulation, completed_at=deadline, auto_closed=True)
        return True
    return False


@kine_bp.before_request
def auto_close_expired_exam_sessions():
    """A student's request may only expire their own attempts.

    Anonymous/staff requests must not trigger another student's evaluation.
    Autonomous scheduling remains a separate T16/T20 requirement.
    """
    if session.get('user_type') != 'student' or not current_user.is_authenticated or current_user.ecos_type != 'kine':
        return
    now = datetime.utcnow()
    active_sessions = SimulationSession.query.filter_by(
        mode='exam', status='in_progress', student_id=current_user.id,
    ).join(PatientCase).filter(PatientCase.specialty == 'kine').all()
    changed = False
    for simulation in active_sessions:
        deadline = exam_deadline(simulation)
        if now >= deadline:
            _complete_simulation(simulation, completed_at=deadline, auto_closed=True, commit=False)
            changed = True
    if changed:
        db.session.commit()


def _medications_json(record, level):
    medications = []
    for medication in record.medications:
        item = {'therapeutic_class': medication.therapeutic_class}
        if level == 'licence':
            item.update({'inn': medication.inn, 'effect': medication.effect,
                         'physiotherapy_precautions': medication.physiotherapy_precautions})
        medications.append(item)
    return medications


def _full_record_json(record, level):
    """Serialize the complete record for internal evaluation only."""
    return {
        'identity': record.identity, 'medical_context': record.medical_context,
        'medical_history': record.medical_history, 'comorbidities': record.comorbidities,
        'tests': record.tests, 'reference_vitals': record.reference_vitals,
        'medical_prescription': record.medical_prescription,
        'physiotherapy_prescription': record.physiotherapy_prescription,
        'available_documents': record.available_documents,
        'interventions': [{'type': item.intervention_type, 'date': item.timing,
                           'complications': item.complications} for item in record.interventions],
        'medications': _medications_json(record, level),
    }


def _student_initial_record_json(record, level):
    """Expose only information authorized before the student simulation.

    Test results, reference values and the physiotherapy assessment remain
    server-side. They are consumed by the patient engine after an explicit
    test announcement and by the final evaluation.
    """
    return {
        'identity': record.identity,
        'medical_context': record.medical_context,
        'medical_history': record.medical_history,
        'comorbidities': record.comorbidities,
        'medical_prescription': record.medical_prescription,
        'physiotherapy_prescription': record.physiotherapy_prescription,
        'available_documents': record.available_documents,
        'interventions': [{
            'intervention_type': item.intervention_type,
            'intervention_date': item.timing,
            'complications': item.complications,
        } for item in record.interventions],
        'medications': _medications_json(record, level),
    }


@kine_bp.route('/student')
@student_required
def student_kine_home():
    level = current_user.level or 'licence'
    cases = []
    for availability in KineCaseAvailability.query.filter(
            KineCaseAvailability.version_id.isnot(None)).all():
        version = training_version(availability.case_id, current_user)
        if version:
            cases.append(version_view(version))
    cases.sort(key=lambda case: case.case_number)
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
        compatible_cases = []
        for selection in exam.case_version_selections:
            version = selected_exam_version(exam.id, selection.case_id, current_user)
            if version:
                compatible_cases.append(version_view(version))
        compatible_cases.sort(key=lambda case: case.case_number)
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
    case = simulation_case(simulation)
    record = case.patient_record
    return {
        'case_number': case.case_number, 'specialty': 'kine',
        'diagnosis': case.diagnosis, 'student': simulation_student(simulation),
        'evaluation_inputs': json.loads(simulation.case_version.content_json).get('evaluation_inputs', {}) if simulation.case_version else {},
        **({'_frozen_evaluation_reference': json.loads(simulation.evaluation_reference_json)} if simulation.evaluation_reference_json else {}),
        'timeline': simulation.timeline or [],
        'patient_record': _full_record_json(record, simulation_student(simulation).level or 'licence') if record else {},
    }


def _complete_simulation(simulation, completed_at=None, auto_closed=False, commit=True):
    if simulation.evaluation_results:
        return simulation.evaluation_results
    reference = json.loads(simulation.evaluation_reference_json or '{}')
    if reference.get('engine') == ENGINE:
        try:
            evaluation = evaluate_criteria(simulation.conversation or [], reference,
                llm=None if auto_closed else current_app.config.get('KINE_LLM_CLIENT', current_app.config.get('GROQ_CLIENT')),
                timeline=simulation.timeline or [], context=_evaluation_case_data(simulation))
        except FrozenEvaluationUnavailable:
            if not auto_closed:
                raise
            evaluation = {'result_status': 'pending', 'status_label': 'En attente de vérification',
                          'points_earned': None, 'points_total': 20, 'passed': None,
                          'reason': 'Moteur figé indisponible ; échéance appliquée sans recalcul.'}
    else:
        # Historical scores stay untouched; unfinished legacy attempts require review.
        evaluation = {'result_status': 'pending', 'status_label': 'En attente de vérification',
                      'points_earned': None, 'points_total': 20, 'passed': None,
                      'reason': 'Référentiel historique : vérification humaine requise.'}
    try:
        claim(simulation, ('in_progress', 'paused'), 'completed')
    except TransitionConflict:
        if simulation.status == 'completed' and simulation.evaluation_results:
            return simulation.evaluation_results
        raise
    if simulation.paused_at:
        simulation.total_paused_seconds = (simulation.total_paused_seconds or 0) + max(
            0, round(((completed_at or datetime.utcnow()) - simulation.paused_at).total_seconds()))
        simulation.paused_at = None
    frozen_student = simulation_student(simulation)
    evaluation['student'] = {
        'name': (frozen_student.name or '').strip()
        or f"Étudiant {frozen_student.student_code}",
        'student_code': frozen_student.student_code,
        'level': {'licence': 'Licence', 'master': 'Master'}.get(
            frozen_student.level,
            frozen_student.level or 'Non renseigné',
        ),
        'group_name': frozen_student.group_name or '',
        'class_name': frozen_student.class_name or '',
    }
    evaluation['vital_measurements'] = list(
        (simulation.runtime_state or {}).get('obtained_vital_parameters') or []
    )
    record_change(simulation, None, evaluation, 'system', 'Évaluation initiale')
    simulation.eliminatory_error_triggered = evaluation.get('eliminatory_error_triggered', False)
    simulation.eliminatory_error = '; '.join(
        error.get('description') or error.get('id', '')
        for error in evaluation.get('eliminatory_errors', [])
    ) or None
    simulation.completed_at = completed_at or datetime.utcnow()
    tracker = _progression(simulation)
    completed_phase = tracker.to_frontend()['current_phase']
    tracker.finalize_current_phase(simulation.completed_at)
    simulation.status = 'completed'
    if auto_closed:
        append_timeline_event(simulation, 'exam_auto_closed', actor='system', timestamp=simulation.completed_at)
    append_timeline_event(simulation, 'simulation_completed', actor='system', phase=completed_phase,
                          details={'score': evaluation.get('points_earned'), 'passed': evaluation.get('passed')},
                          timestamp=simulation.completed_at)
    if commit:
        db.session.commit()
    return evaluation


@kine_bp.route('/cases/<int:case_id>/patient-record')
@student_required
def patient_record_view(case_id):
    PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    version = training_version(case_id, current_user)
    if not version:
        return error('Aucune version publiée ne vous est attribuée pour ce cas.', 403)
    case = version_view(version)
    if not case.patient_record:
        return error('Patient record is not configured', 404)
    display_record = prune_empty(record_projection(
        version, current_user.level or 'licence'
    )) or {}
    if wants_json():
        return jsonify(display_record)
    return render_template(
        'patient_record.html', clinical_case=case, patient_record=display_record,
        student_level=current_user.level or 'licence',
        start_simulation_url=url_for('kine.start_simulation'),
    )


@kine_bp.route('/simulation/<int:session_id>/patient-record')
@student_required
def simulation_patient_record(session_id):
    simulation = _session_or_404(session_id)
    case = simulation_case(simulation)
    if not case.patient_record:
        return error('Dossier indisponible.', 404)
    level = simulation_student(simulation).level or 'licence'
    display_record = prune_empty(record_projection(
        simulation.case_version, level, simulation
    )) or {}
    if wants_json():
        return jsonify(record=display_record, version_reference=version_metadata(simulation))
    return render_template('patient_record_embedded.html' if request.args.get('embedded') == '1' else 'patient_record.html', clinical_case=case, patient_record=display_record,
                           student_level=level, start_simulation_url=None,
                           version_reference=version_metadata(simulation),
                           document_url_template=url_for(
                               'kine.simulation_document', session_id=simulation.id,
                               stable_id='__STABLE_ID__',
                           ))


@kine_bp.route('/simulation/start', methods=['POST'])
@student_required
def start_simulation():
    data = payload()
    try:
        case_id = int(data.get('case_id'))
    except (TypeError, ValueError):
        return error('Valid case_id is required')
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    mode = str(data.get('mode') or 'training').lower()
    if mode not in ('training', 'exam'):
        return error('Mode de simulation invalide.', 403)
    exam = None
    version = None
    if mode == 'exam':
        try:
            exam = Exam.query.get(int(data.get('exam_id')))
        except (TypeError, ValueError):
            exam = None
        now = datetime.utcnow()
        if not exam or not _student_has_exam_access(exam, current_user) or case not in exam.cases:
            return error('Student or case is not authorized for this exam', 403)
        version = selected_exam_version(exam.id, case.id, current_user)
        if not version:
            return error("Aucune version publiée compatible n'est programmée pour ce cas.", 403)
        if not exam.start_at <= now < exam.end_at:
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
    else:
        version = training_version(case.id, current_user)
        if not version:
            return error("Aucune version publiée ne vous est attribuée pour cet entraînement.", 403)
    simulation = SimulationSession(
        student_id=current_user.id, clinical_case_id=case.id, exam=exam,
        mode=mode, status='in_progress', current_phase=1,
        phase_timings={}, timeline=[],
        conversation=[], runtime_state={},
    )
    freeze_simulation(simulation, version, current_user)
    append_timeline_event(simulation, 'simulation_started', phase=1,
                          details={'case_id': case.id, 'case_version_id': version.id,
                                   'case_version_number': version.number, 'mode': mode})
    db.session.add(simulation)
    try:
        db.session.flush()
        record_initial_disclosures(simulation)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error(
            "Ce cas d’examen a déjà été commencé. Une seule tentative est autorisée.",
            409,
        )
    result = {'simulation_id': simulation.id, 'case_id': case.id, 'mode': mode,
              'version_reference': version_metadata(simulation),
              'progress': _progression(simulation).to_frontend()}
    if exam:
        deadline = exam_deadline(simulation)
        result['deadline'] = deadline.isoformat() + 'Z'
    if wants_json():
        return jsonify(result), 201
    return redirect(url_for('kine.simulation_chat', session_id=simulation.id))


@kine_bp.route('/simulation/<int:session_id>/chat')
@student_required
def simulation_chat(session_id):
    simulation = _session_or_404(session_id)
    _expire_exam_session(simulation)
    progress_state = _progression(simulation).to_frontend()
    deadline = None
    if simulation.mode == 'exam' and simulation.exam:
        deadline = exam_deadline(simulation)
    return render_template(
        'chat_kine.html', simulation=student_simulation(simulation), clinical_case=simulation_case(simulation),
        version_reference=version_metadata(simulation),
        conversation=simulation.conversation or [],
        evaluation=student_result(simulation),
        obtained_vital_parameters=list(
            (simulation.runtime_state or {}).get('obtained_vital_parameters') or []
        ),
        simulation_mode=simulation.mode, current_phase=progress_state['current_phase'],
        progression=progress_state,
        progress_url=url_for('kine.simulation_progress', session_id=simulation.id),
        message_url=url_for('kine.simulation_message', session_id=simulation.id),
        test_url=url_for('kine.simulation_test_request', session_id=simulation.id),
        pause_url=url_for('kine.pause_simulation', session_id=simulation.id),
        resume_url=url_for('kine.resume_simulation', session_id=simulation.id),
        complete_url=url_for('kine.complete_simulation', session_id=simulation.id),
        record_url=url_for('kine.simulation_patient_record', session_id=simulation.id, embedded=1),
        timeline_url=url_for('kine.simulation_timeline', session_id=simulation.id),
        deadline=(deadline.isoformat() + 'Z') if deadline else None,
    )


def _process_message(simulation, message, request_id=None):
    from message_delivery import prepare, reserve, failed
    try:
        request_id, saved_human, saved_response = prepare(simulation, message, request_id)
    except TransitionConflict:
        raise
    except ValueError as exc:
        return error(str(exc), 400)
    if saved_response:
        return jsonify({'response': saved_response, 'replayed': True,
                        'progress': _progression(simulation).to_frontend(),
                        'vital_measurements': (simulation.runtime_state or {}).get('obtained_vital_parameters') or [],
                        'revealed_information_ids': sorted(disclosed_ids(simulation))})
    if simulation.status != 'in_progress':
        return error('Simulation is not in progress', 409)
    if _expire_exam_session(simulation):
        return error('Exam time has expired', 409)
    if not message:
        return error('Message is required')
    claim(simulation, ('in_progress',), 'in_progress')
    recorded_at = datetime.utcnow()
    phase_state = _progression(simulation).to_frontend()
    display_phase = phase_state['current_phase']
    conversation = list(simulation.conversation or [])
    human = {
        'role': 'human', 'content': message,
        'timestamp': recorded_at.isoformat(),
        'phase': display_phase,
        'phase_key': phase_state['current_phase_key'],
        'request_id': request_id,
        'processing_phase': simulation.current_phase,
    }
    if not saved_human:
        conversation.append(human)
    accepted_human = saved_human or human
    history = conversation[:conversation.index(accepted_human)]
    processing_phase = accepted_human.get('processing_phase', simulation.current_phase)
    # Persist the accepted interaction before any slow external call.
    simulation.conversation = conversation
    if not saved_human:
        append_timeline_event(simulation, 'student_message', phase=display_phase,
                              details=message, timestamp=recorded_at)
    reserve(simulation, request_id)
    db.session.flush()
    accepted_revision = simulation.updated_at
    db.session.commit()
    runtime_state = dict(simulation.runtime_state or {})
    exercise_started = runtime_state.get('exercise_started_at')
    runtime_state['session_elapsed_seconds'] = max(0, (datetime.utcnow() - datetime.fromisoformat(exercise_started)).total_seconds()) if exercise_started else 0
    level = simulation_student(simulation).level or 'licence'
    engine_record = record_projection(
        simulation.case_version, level, simulation, patient_context=True,
    )
    examination_record = record_projection(
        simulation.case_version, level, simulation, examination=True,
    )
    for key in ('tests', 'reference_vitals'):
        if key in examination_record:
            engine_record[key] = examination_record[key]
    engine = KinePatientEngine(
        simulation_case(simulation), engine_record,
        current_app.config.get('KINE_LLM_CLIENT', current_app.config.get('GROQ_CLIENT')), runtime_state,
        student=simulation_student(simulation),
    )
    try:
        candidate = None
        if (len(message) <= 1200 and not PatientSafety._is_prompt_injection(message)
                and not PatientSafety._is_privileged_request(message)
                and not PatientSafety._is_dangerous_student_advice(message)
                and not (runtime_state.get('session_measurements') and engine._is_measurement_intent(message))):
            candidate = matching_question_information(
                simulation.case_version, simulation, level, message,
                llm=current_app.config.get('KINE_QUESTION_ROUTER', current_app.config.get('KINE_LLM_CLIENT', current_app.config.get('GROQ_CLIENT'))),
                last_id=runtime_state.get('last_information_id'),
            )
        if (candidate is not None and not engine._is_prompt_injection(message)
                and not engine._is_privileged_request(message)):
            runtime_state['last_information_id'] = candidate.stable_id
            if candidate.patient_knows is True:
                response = {
                    'type': 'patient_response',
                    'content': style_patient_fact(format_information_value(candidate), simulation_case(simulation), level, history, message),
                }
                record_disclosure(
                    simulation, candidate,
                    'deepening' if effective_mode(candidate, level) == 'deepening' else 'question',
                    {'message': message},
                )
                runtime_state['last_information_id'] = candidate.stable_id
                if candidate.path.startswith('effort_tests.'):
                    from .routes_effort import store_measurement
                    simulation.runtime_state = runtime_state
                    store_measurement(simulation, candidate, json.loads(candidate.value_json), source='patient')
                    runtime_state = dict(simulation.runtime_state)
            else:
                response = {
                    'type': 'patient_response',
                    'content': "Je ne connais pas cette information.",
                }
        else:
            response = engine.respond(message, processing_phase, history)
    except AmbiguousQuestion:
        response = {'type': 'patient_response', 'content': 'Pouvez-vous préciser votre question ?'}
    except Exception:
        current_app.logger.warning(
            'Virtual patient service failed for simulation %s', simulation.id
        )
        failed(simulation, request_id, accepted_revision)
        return error(
            "Le patient virtuel est temporairement indisponible. Veuillez réessayer dans quelques instants.",
            503,
        )
    if simulation.mode == 'exam' and datetime.utcnow() >= exam_deadline(simulation):
        db.session.rollback()
        db.session.refresh(simulation)
        _expire_exam_session(simulation)
        return error('Exam time has expired', 409)
    # A late response must not modify a completed or explicitly abandoned attempt.
    claim(simulation, ('in_progress',), 'in_progress', refresh=False, expected=accepted_revision)
    conversation.append({
        'role': 'assistant', 'content': response['content'],
        'type': response['type'], 'timestamp': datetime.utcnow().isoformat(),
        'phase': display_phase, 'phase_key': phase_state['current_phase_key'],
        'request_id': request_id, 'delivery_response': response,
    })
    if response['type'] in ('test_result', 'test_result_unavailable'):
        append_timeline_event(simulation, 'test_requested', phase=display_phase,
                              details=response.get('test') or {'available': False})
    if response['type'] == 'test_result':
        disclosed_test = matching_examination_information(
            simulation.case_version, level, response.get('test'),
        )
        if disclosed_test is not None:
            record_disclosure(
                simulation, disclosed_test, 'examination',
                {'test': response.get('test') or {}},
            )
    if response['type'] == 'incident':
        append_timeline_event(simulation, 'incident_triggered', actor='system',
                              phase=display_phase,
                              incident_id=response.get('incident_id'), severity=response.get('severity'))
    for event in response.get('events', []):
        append_timeline_event(simulation, 'session_event', actor='system', details=event)
    if response['type'] == 'safety_guardrail':
        append_timeline_event(simulation, 'safety_guardrail_triggered', actor='system',
                              phase=display_phase,
                              details={'reason': response.get('guardrail')})
    simulation.conversation = conversation
    runtime_state['message_delivery'] = {'request_id': request_id, 'state': 'done'}
    simulation.runtime_state = runtime_state
    db.session.commit()
    return jsonify({
        'response': response,
        'progress': _progression(simulation).to_frontend(),
        'vital_measurements': runtime_state.get('obtained_vital_parameters') or [],
        'revealed_information_ids': sorted(disclosed_ids(simulation)),
    })


@kine_bp.route('/simulation/<int:session_id>/message', methods=['POST'])
@student_required
def simulation_message(session_id):
    data = payload()
    return _process_message(_session_or_404(session_id), str(data.get('message') or '').strip(), data.get('request_id'))


@kine_bp.route('/simulation/<int:session_id>/test-request', methods=['POST'])
@student_required
def simulation_test_request(session_id):
    data = payload()
    message = str(data.get('message') or '').strip()
    if not message and data.get('test'):
        message = f"I am going to perform the {data.get('test')} test"
    return _process_message(_session_or_404(session_id), message, data.get('request_id'))


@kine_bp.route('/simulation/<int:session_id>/pause', methods=['POST'])
@student_required
def pause_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.mode != 'training':
        return error('Exam sessions cannot be paused', 409)
    if simulation.status != 'in_progress':
        return error('Only an active simulation can be paused', 409)
    claim(simulation, ('in_progress',), 'paused')
    simulation.paused_at = datetime.utcnow()
    append_timeline_event(
        simulation, 'simulation_paused',
        phase=_progression(simulation).to_frontend()['current_phase'],
    )
    db.session.commit()
    return jsonify({'status': simulation.status, 'paused_at': simulation.paused_at.isoformat()})


@kine_bp.route('/simulation/<int:session_id>/resume', methods=['POST'])
@student_required
def resume_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.mode != 'training' or simulation.status != 'paused':
        return error('Only a paused training simulation can be resumed', 409)
    claim(simulation, ('paused',), 'in_progress')
    now = datetime.utcnow()
    if simulation.paused_at:
        simulation.total_paused_seconds = (simulation.total_paused_seconds or 0) + max(
            0, round((now - simulation.paused_at).total_seconds())
        )
    simulation.paused_at = None; simulation.status = 'in_progress'
    append_timeline_event(
        simulation, 'simulation_resumed',
        phase=_progression(simulation).to_frontend()['current_phase'],
    )
    db.session.commit()
    return jsonify({'status': simulation.status, 'total_paused_seconds': simulation.total_paused_seconds})


@kine_bp.route('/simulation/<int:session_id>/complete', methods=['POST'])
@student_required
def complete_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.status not in ('in_progress', 'paused'):
        if simulation.evaluation_results:
            return jsonify({
                'evaluation': student_result(simulation),
                'status': simulation.status,
            })
        return error('Simulation cannot be completed', 409)
    evaluation = _complete_simulation(simulation)
    return jsonify({'evaluation': student_result(simulation),
                    'status': simulation.status,
                    'progress': _progression(simulation).to_frontend(),
                    'timeline_url': url_for('kine.simulation_timeline', session_id=simulation.id)})


@kine_bp.route('/simulation/<int:session_id>/abandon', methods=['POST'])
@student_required
def abandon_simulation(session_id):
    simulation = _session_or_404(session_id)
    if simulation.status == 'interrupted':
        return jsonify(status='interrupted')
    if simulation.status not in ('in_progress', 'paused') or simulation.evaluation_results:
        return error('Cette tentative ne peut plus être abandonnée.', 409)
    claim(simulation, ('in_progress', 'paused'), 'interrupted')
    now = datetime.utcnow()
    if simulation.paused_at:
        simulation.total_paused_seconds += max(0, round((now - simulation.paused_at).total_seconds()))
        simulation.paused_at = None
    simulation.runtime_state = {**(simulation.runtime_state or {}), 'interrupted_at': now.isoformat(), 'interruption_reason': 'explicit_abandon'}
    _progression(simulation).finalize_current_phase(now)
    append_timeline_event(simulation, 'simulation_abandoned', details={'reason': 'explicit_abandon'}, timestamp=now)
    db.session.commit()
    return jsonify(status='interrupted')


@kine_bp.route('/simulation/<int:session_id>/reconnect', methods=['POST'])
@student_required
def reconnect_simulation(session_id):
    simulation = _session_or_404(session_id)
    # Request expiry runs before this route: a network outage never pauses the clock.
    if simulation.status != 'in_progress':
        return error('La tentative n’est plus active. Consultez son historique.', 409)
    claim(simulation, ('in_progress',), 'in_progress')
    append_timeline_event(simulation, 'network_reconnected', details={'client_reported': True})
    db.session.commit()
    return jsonify(status=simulation.status, deadline=exam_deadline(simulation).isoformat() + 'Z' if simulation.mode == 'exam' else None)


@kine_bp.route('/simulation/<int:session_id>/information/<stable_id>')
@student_required
def simulation_information(session_id, stable_id):
    """Direct-object access follows the same frozen policy as every projection."""
    simulation = _session_or_404(session_id)
    item = next((candidate for candidate in simulation.case_version.information_items
                 if candidate.stable_id == stable_id), None)
    level = simulation_student(simulation).level or 'licence'
    if (item is None or effective_mode(item, level) == 'evaluation_reserved'
            or (effective_mode(item, level) != 'initial'
                and item.stable_id not in disclosed_ids(simulation))):
        return error('Information indisponible.', 404)
    return jsonify(student_information_payload(item))


@kine_bp.route('/simulation/<int:session_id>/documents/<stable_id>')
@student_required
def simulation_document(session_id, stable_id):
    """Download only an original frozen document allowed by the T04 policy."""
    simulation = _session_or_404(session_id)
    item = next((candidate for candidate in simulation.case_version.information_items
                 if candidate.stable_id == stable_id), None)
    level = simulation_student(simulation).level or 'licence'
    if (item is None or effective_mode(item, level) == 'evaluation_reserved'
            or (effective_mode(item, level) != 'initial'
                and stable_id not in disclosed_ids(simulation))):
        return error('Document indisponible.', 404)
    snapshot = json.loads(simulation.case_version.content_json)
    frozen = next((document for document in snapshot.get('case_documents') or []
                   if document.get('stable_id') == stable_id
                   and document.get('kind') != 'source'), None)
    stored = db.session.query(KineCaseDocument).filter_by(
        clinical_case_id=simulation.clinical_case_id, stable_id=stable_id,
    ).first()
    if frozen is None or stored is None:
        return error('Document indisponible.', 404)
    root_base = (
        current_app.config.get('KINE_DOCUMENT_FOLDER')
        or current_app.config.get('UPLOAD_FOLDER') or tempfile.gettempdir()
    )
    root = os.path.abspath(os.path.join(root_base, 'kine_case_documents', str(simulation.clinical_case_id)))
    from storage_paths import upload_path
    path = upload_path(frozen.get('stored_path'))
    try:
        contained = os.path.commonpath((root, path)) == root
    except ValueError:
        contained = False
    if not contained or not os.path.isfile(path):
        return error('Document indisponible.', 404)
    with open(path, 'rb') as stream:
        content_hash = hashlib.sha256(stream.read()).hexdigest()
    if (content_hash != frozen.get('sha256') or os.path.getsize(path) != frozen.get('size_bytes')):
        return error('Intégrité du document invalide.', 409)
    return send_file(
        path, as_attachment=True, download_name=frozen['original_filename'],
        mimetype=frozen.get('mime_type') or 'application/octet-stream',
    )


@kine_bp.route('/simulation/<int:session_id>/progress', methods=['GET', 'POST'])
@student_required
def simulation_progress(session_id):
    simulation = _session_or_404(session_id)
    if _expire_exam_session(simulation):
        return error('Exam time has expired', 409)
    tracker = _progression(simulation)
    if request.method == 'POST':
        if simulation.status != 'in_progress':
            return error('Progression is available only while the simulation is active', 409)
        claim(simulation, ('in_progress',), 'in_progress')
        try:
            state = tracker.navigate_to(payload().get('phase'))
            db.session.commit()
        except (ValueError, NavigationLockedError) as exc:
            db.session.rollback()
            claim(simulation, ('in_progress',), 'in_progress')
            append_timeline_event(
                simulation, 'phase_navigation_denied',
                phase=_progression(simulation).to_frontend()['current_phase'],
                details={'requested_phase': payload().get('phase'), 'reason': str(exc)},
            )
            db.session.commit()
            return error(str(exc), 409)
        return jsonify(state)
    return jsonify(tracker.to_frontend())


@kine_bp.route('/simulation/<int:session_id>/timeline')
@student_required
def simulation_timeline(session_id):
    simulation = _session_or_404(session_id)
    timezone_name = request.args.get('timezone', 'Africa/Casablanca')
    formatted = format_timeline(student_timeline(simulation), timezone_name)
    public = student_simulation(simulation)
    if wants_json():
        return jsonify({'simulation_id': simulation.id, 'timeline': formatted,
                        'event_count': len(formatted), 'timezone': formatted[0]['timezone'] if formatted else timezone_name,
                        'progression': _progression(simulation).to_frontend(),
                        'phase_timings': simulation.phase_timings or {},
                        'supplementary_score': public.supplementary_score,
                        'teacher_comments': public.teacher_comments,
                        'reviewed_at': public.reviewed_at.isoformat() + 'Z' if public.reviewed_at else None})
    return render_template(
        'timeline_view.html', simulation=public, student=simulation_student(simulation),
        clinical_case=simulation_case(simulation), version_reference=version_metadata(simulation),
        timeline=formatted, progression=_progression(simulation).to_frontend(),
        pdf_url=url_for('kine.individual_pdf', session_id=simulation.id),
    )


@kine_bp.route('/history')
@student_required
def simulation_history():
    sessions = SimulationSession.query.join(PatientCase).filter(SimulationSession.student_id == current_user.id, PatientCase.specialty == 'kine').order_by(SimulationSession.started_at.desc()).all()
    from kine_reporting import duration_minutes
    history = []
    for item in sessions:
        progress = _progression(item).to_frontend()
        public = student_simulation(item)
        history.append({
            'id': item.id, 'case_id': item.clinical_case_id,
            'duration_minutes': duration_minutes(item),
            'student_name': (current_user.name or '').strip()
            or f"Étudiant {current_user.student_code}",
            'student_code': current_user.student_code,
            'case_number': simulation_case(item).case_number,
            **version_metadata(item),
            'mode': item.mode, 'status': item.status,
            'current_phase': progress['current_phase'],
            'total_phases': len(progress['phases']),
            'started_at': item.started_at.isoformat(),
            'completed_at': item.completed_at.isoformat() if item.completed_at else None,
            'evaluation_results': student_result(item),
            'revealed_information_ids': sorted(disclosed_ids(item)),
            'supplementary_score': public.supplementary_score,
            'teacher_comments': public.teacher_comments,
            'reviewed_at': public.reviewed_at.isoformat() + 'Z' if public.reviewed_at else None,
            'pdf_url': url_for('kine.individual_pdf', session_id=item.id),
            'chat_url': url_for('kine.simulation_chat', session_id=item.id),
            'timeline_url': url_for('kine.simulation_timeline', session_id=item.id),
        })
    from kine_reporting import aggregate, result_status, duration_minutes, matches, COMPETENCIES
    rows = [{**h, 'student_id': current_user.id, 'score': (h['evaluation_results'] or {}).get('points_earned'),
             'result_status': result_status(h['evaluation_results'] or {}), 'evaluation': h['evaluation_results'] or {},
             'duration_minutes': h['duration_minutes']} for h in history]
    rows = [row for row in rows if matches(row, request.args)]
    kept = {row['id'] for row in rows}
    history = [h for h in history if h['id'] in kept]
    report = aggregate(rows, request.args)
    if wants_json():
        return jsonify({'sessions': history, 'report': report})
    return render_template('student_history_kine.html', sessions=history, report=report, filters=request.args, competency_options=COMPETENCIES)
