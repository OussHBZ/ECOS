"""Effort measurements resolved by frozen test + measurement IDs, never fuzzy names."""
from copy import deepcopy
import json
from datetime import datetime

from flask import jsonify, request, render_template
from auth import student_required
from case_versions import simulation_student
from information_access import effective_mode, record_disclosure, disclosed_ids
from kine_permissions import kine_permission_required, require_simulation
from models import db
from kine_transitions import claim
from timeline_logger import append_timeline_event
from . import kine_bp
from .common import error, payload
from .routes_student import _session_or_404, _expire_exam_session


def entries(simulation):
    level = simulation_student(simulation).level or 'licence'
    return [(item, json.loads(item.value_json)) for item in simulation.case_version.information_items
            if item.path.startswith('effort_tests.') and effective_mode(item, level) != 'evaluation_reserved']


def store_measurement(simulation, item, value, *, source, observed=None):
    runtime = deepcopy(simulation.runtime_state or {})
    observations = list(runtime.get('effort_measurements') or [])
    row = {key: value[key] for key in (
        'test_id', 'test_name', 'id', 'name', 'moment', 'moment_detail', 'actor', 'unit', 'status',
    ) if key in value}
    row.update(stable_id=item.stable_id, source=source, timestamp=datetime.utcnow().isoformat())
    if observed is not None:
        row['value'] = observed
        row['status'] = 'value'
    elif 'value' in value:
        row['value'] = value['value']
    observations.append(row)
    runtime['effort_measurements'] = observations
    simulation.runtime_state = runtime
    append_timeline_event(simulation, 'effort_measurement', actor=value['actor'], details=row)
    if observed is None:
        record_disclosure(simulation, item, 'examination', {'test_id': value['test_id'], 'measurement_id': value['id']})
    return row


def save_measurement_once(simulation, item, value, data, *, source, observed=None):
    key = data.get('request_id')
    if key is not None and (not isinstance(key, str) or not 1 <= len(key) <= 128):
        return error('Identifiant de requête invalide.')
    identity = json.dumps([source, data.get('test_id'), data.get('measurement_id'), observed], ensure_ascii=False)
    if key is not None:
        for row in (simulation.runtime_state or {}).get('effort_measurements', []):
            if row.get('request_id') == key:
                if row.get('delivery_identity') != identity:
                    return error('Cet identifiant appartient à une autre mesure.')
                return jsonify(measurement=row, replayed=True)
    claim(simulation, ('in_progress',), 'in_progress')
    row = store_measurement(simulation, item, value, source=source, observed=observed)
    if key is not None:
        # This row is shared by the freshly assigned JSON containers. Flag the
        # final dictionaries explicitly so all serializers persist the key.
        row.update(request_id=key, delivery_identity=identity)
        simulation.runtime_state = deepcopy(simulation.runtime_state)
        simulation.timeline = deepcopy(simulation.timeline)
    db.session.commit()
    return jsonify(measurement=row)


@kine_bp.route('/simulation/<int:session_id>/effort-tests', methods=['GET', 'POST'])
@student_required
def simulation_effort_tests(session_id):
    simulation = _session_or_404(session_id)
    if _expire_exam_session(simulation):
        return error('Exam time has expired', 409)
    level = simulation_student(simulation).level or 'licence'
    if request.method == 'GET':
        catalog = {}
        for item, value in entries(simulation):
            if effective_mode(item, level) != 'examination' and item.stable_id not in disclosed_ids(simulation):
                continue
            test = catalog.setdefault(value['test_id'], {'id': value['test_id'], 'name': value['test_name'], 'measurements': []})
            test['measurements'].append({key: value[key] for key in ('id', 'name', 'moment', 'moment_detail', 'actor', 'unit') if key in value})
        return jsonify(tests=list(catalog.values()), measurements=(simulation.runtime_state or {}).get('effort_measurements', []))
    if simulation.status != 'in_progress':
        return error('Simulation is not in progress', 409)
    data = payload()
    match = next(((item, value) for item, value in entries(simulation)
                  if value['test_id'] == data.get('test_id') and value['id'] == data.get('measurement_id')
                  and effective_mode(item, level) == 'examination'), None)
    if not match:
        return error('Mesure indisponible.', 404)
    item, value = match
    if value['actor'] != 'student':
        return error('Cette mesure doit être renseignée par son responsable.', 403)
    observed = data.get('observed_value')
    if observed is not None and (not isinstance(observed, (str, int, float)) or isinstance(observed, bool) or len(str(observed)) > 1200):
        return error('Valeur observée invalide.')
    if observed is None and value.get('value') in (None, '') and value.get('status') == 'value':
        return error('Aucune valeur prédéfinie disponible.', 404)
    return save_measurement_once(simulation, item, value, data, source='student_reported' if observed is not None else 'scenario', observed=observed)


@kine_bp.route('/simulation/<int:session_id>/effort-event', methods=['POST'])
@student_required
def simulation_effort_event(session_id):
    simulation = _session_or_404(session_id)
    if _expire_exam_session(simulation) or simulation.status != 'in_progress':
        return error('Simulation is not in progress', 409)
    claim(simulation, ('in_progress',), 'in_progress')
    data = payload()
    level = simulation_student(simulation).level or 'licence'
    rows = []
    # Events are explicit scenario markers, not inferred physiological rules.
    for item, value in entries(simulation):
        if (value['test_id'] == data.get('test_id') and value.get('actor') == 'system'
                and value.get('trigger') == data.get('event')
                and effective_mode(item, level) == 'examination'
                and item.stable_id not in disclosed_ids(simulation)):
            if value.get('value') not in (None, '') or value.get('status') != 'value':
                rows.append(store_measurement(simulation, item, value, source='scenario_event'))
    db.session.commit()
    return jsonify(measurements=rows)


@kine_bp.route('/teacher/simulation/<int:session_id>/effort-measurement', methods=['GET', 'POST'])
@kine_permission_required('results.review')
def teacher_effort_measurement(session_id):
    simulation = require_simulation(session_id)
    if request.method == 'GET':
        return render_template('effort_observer_kine.html', simulation=simulation,
                               measurements=[value for _, value in entries(simulation) if value['actor'] == 'teacher'])
    if _expire_exam_session(simulation) or simulation.status != 'in_progress':
        return error('Simulation is not in progress', 409)
    data = payload()
    match = next(((item, value) for item, value in entries(simulation)
                  if value['test_id'] == data.get('test_id') and value['id'] == data.get('measurement_id')
                  and value['actor'] == 'teacher'), None)
    if not match:
        return error('Mesure indisponible.', 404)
    observed = data.get('observed_value')
    if observed is None or isinstance(observed, bool) or not isinstance(observed, (str, int, float)) or len(str(observed)) > 1200:
        return error('Valeur observée requise.')
    return save_measurement_once(simulation, *match, data, source='teacher_reported', observed=observed)
