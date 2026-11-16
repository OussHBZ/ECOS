"""Teacher authoring and explicit student session actions on frozen versions."""
from copy import deepcopy
from datetime import datetime
import json
from flask import jsonify, render_template, request, redirect, url_for
from auth import student_required
from case_versions import save_draft, simulation_case, simulation_student
from kine_permissions import kine_permission_required
from models import db, PatientCase
from kine_transitions import claim, TransitionConflict
from message_delivery import prepare
from rehabilitation import (CATEGORIES, MODALITIES, SURVEILLANCE_SUGGESTIONS, OBJECTIVE_SUGGESTIONS,
                            normalize_rehabilitation, advance_session, evaluation_inputs, weekly_volume)
from timeline_logger import append_timeline_event
from . import kine_bp
from .common import error, payload, wants_json
from .routes_student import _session_or_404, _expire_exam_session


@kine_bp.route('/cases/<int:case_id>/rehabilitation', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def rehabilitation_editor(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'GET':
        program = case.structured_content.get('rehabilitation_program', {})
        if wants_json():
            return jsonify(program=program, evaluation_inputs=evaluation_inputs(case),
                           calculated_weekly_volumes={e['id']: weekly_volume(e.get('fitt', {})) for e in program.get('exercises', [])})
        return render_template('rehabilitation_kine.html', clinical_case=case, program=program, categories=CATEGORIES,
                               suggestions={'modalities': MODALITIES, 'surveillance': SURVEILLANCE_SUGGESTIONS,
                                            'objectives': OBJECTIVE_SUGGESTIONS})
    try:
        data = payload()
        program = data.get('program') if request.is_json else json.loads(data.get('program_json', '{}'))
        content = deepcopy(case.structured_content)
        content['rehabilitation_program'] = normalize_rehabilitation(program)
        case.structured_content = content
        save_draft(case)
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return error(str(exc))
    if wants_json():
        return jsonify(program=program)
    return redirect(url_for('kine.rehabilitation_editor', case_id=case.id))


@kine_bp.route('/simulation/<int:session_id>/session-action', methods=['POST'])
@student_required
def session_action(session_id):
    simulation = _session_or_404(session_id)
    if _expire_exam_session(simulation) or simulation.status != 'in_progress':
        return error('Simulation inactive.', 409)
    data = payload()
    action = data.get('action', '')
    if not isinstance(action, str) or not action.strip() or len(action) > 1200:
        return error('Action de séance requise (1200 caractères maximum).')
    identity=json.dumps([action,data.get('exercise_id'),data.get('exercise_name')],ensure_ascii=False)
    try:
        key, previous, replay=prepare(simulation, identity, data.get('request_id'))
    except TransitionConflict:
        raise
    except ValueError as exc:
        return error(str(exc))
    if replay is not None:
        return jsonify(**replay, replayed=True)
    claim(simulation, ('in_progress',), 'in_progress')
    case = simulation_case(simulation)
    program = deepcopy(case.structured_content.get('rehabilitation_program', {}))
    if (simulation_student(simulation).level or 'licence') != 'master':
        program.setdefault('session', {})['events'] = [e for e in program.get('session', {}).get('events', []) if e['kind'] != 'incident']
    runtime = deepcopy(simulation.runtime_state or {})
    exercise_id = data.get('exercise_id') or runtime.get('session_exercise_id')
    if data.get('exercise_id') and exercise_id not in {e['id'] for e in program.get('exercises', [])}:
        return error('Exercice absent du scénario.')
    exercise_name = data.get('exercise_name')
    if exercise_name is not None:
        if not isinstance(exercise_name, str) or len(exercise_name) > 250:
            return error('Nom d’exercice invalide.')
        exercise_id = next((e['id'] for e in program.get('exercises', []) if e['modality'].casefold() == exercise_name.strip().casefold()), None)
    # Exercise time starts at the explicit session action, not at the anamnèse.
    now = datetime.utcnow()
    if not runtime.get('exercise_started_at') or exercise_id != runtime.get('session_exercise_id') or exercise_name is not None and exercise_name != runtime.get('session_exercise_name'):
        runtime['exercise_started_at'] = now.isoformat()
    elapsed = max(0, (now - datetime.fromisoformat(runtime['exercise_started_at'])).total_seconds())
    runtime, events = advance_session(program, runtime, action,
                                     phase=simulation.current_phase, exercise_id=exercise_id, elapsed_seconds=elapsed)
    runtime['session_exercise_id'] = exercise_id
    if exercise_name is not None:
        runtime['session_exercise_name'] = exercise_name
    simulation.runtime_state = runtime
    append_timeline_event(simulation, 'session_action', actor='student', details={'action': action, 'exercise_id': exercise_id})
    public = []
    for event in events:
        row = {'id': event['id'], 'kind': event['kind'], 'reaction': event['reaction'],
               'measurements': [{k: m[k] for k in ('id', 'name', 'value', 'unit') if k in m}
                                for m in event.get('measurements', []) if m['delivery'] == 'automatic']}
        public.append(row)
        append_timeline_event(simulation, 'session_event', actor='system', details=row)
    transcript = list(simulation.conversation or [])
    transcript.append({'role': 'human', 'content': action, 'type': 'session_action',
                       'exercise': exercise_name, 'timestamp': now.isoformat(), 'phase': simulation.current_phase,
                       'request_id': key, 'delivery_identity': identity, 'delivery_response': {'events': public}})
    for row in public:
        transcript.append({'role': 'assistant', 'content': row['reaction'], 'type': 'session_evolution',
                           'timestamp': now.isoformat(), 'phase': simulation.current_phase})
    simulation.conversation = transcript
    db.session.commit()
    return jsonify(events=public)
