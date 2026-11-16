"""Optional teacher dialogue sandbox; never creates a student attempt/result."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from flask import current_app, jsonify, render_template, request, session
from case_versions import canonical, case_snapshot, digest
from information_access import (
    AmbiguousQuestion, effective_mode, format_information_value,
    matching_question_information, record_projection,
)
from kine_patient_engine import KinePatientEngine
from patient_personality import style_patient_fact
from kine_permissions import kine_permission_required
from models import PatientCase
from . import kine_bp
from .common import error, payload, teacher_id


@kine_bp.route('/cases/<int:case_id>/patient-preview', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def patient_preview(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'GET':
        return render_template('patient_preview_kine.html', clinical_case=case)
    data = payload()
    fingerprint = digest(canonical(case_snapshot(case)))
    previews = dict(session.get('kine_patient_previews') or {})
    preview_id = data.get('preview_id')
    if not preview_id:
        preview_id = uuid4().hex
        previews[preview_id] = {
            'case_id': case_id, 'teacher_id': teacher_id(), 'fingerprint': fingerprint,
            'level': 'licence' if data.get('level') == 'licence' else 'master',
            'conversation': [], 'runtime': {}, 'disclosed': [],
        }
        # Bound signed-cookie/server-session growth; old previews expire explicitly.
        previews = dict(list(previews.items())[-2:])
    state = deepcopy(previews.get(preview_id))
    if not state or state['case_id'] != case_id or state['teacher_id'] != teacher_id():
        return error('Aperçu introuvable.', 404)
    if state['fingerprint'] != fingerprint:
        return error('Le cas a changé. Recommencez un aperçu pour utiliser la nouvelle configuration.', 409)
    if len(state['conversation']) >= 20:
        return error('Recommencez un aperçu pour poursuivre le test.', 409)
    message = str(data.get('message') or '').strip()
    if len(message) > 1200:
        return error('Message trop long.')
    response = None
    if message:
        version = SimpleNamespace(information_items=case.information_items)
        simulation = SimpleNamespace(information_disclosures=[
            SimpleNamespace(stable_id=item) for item in state['disclosed']
        ])
        level = state['level']
        record = record_projection(version, level, simulation, patient_context=True)
        engine = KinePatientEngine(case, record, current_app.config.get('KINE_LLM_CLIENT', current_app.config.get('GROQ_CLIENT')),
                                   state['runtime'], student=SimpleNamespace(level=level))
        try:
            candidate = None
            if not engine._is_prompt_injection(message) and not engine._is_privileged_request(message):
                candidate = matching_question_information(
                    version, simulation, level, message,
                    llm=current_app.config.get('KINE_QUESTION_ROUTER', current_app.config.get('KINE_LLM_CLIENT', current_app.config.get('GROQ_CLIENT'))),
                    last_id=state['runtime'].get('last_information_id'),
                )
            if candidate:
                response = {'type': 'patient_response', 'content': (
                    style_patient_fact(format_information_value(candidate), case, level, state['conversation'], message) if candidate.patient_knows is True
                    else 'Je ne connais pas cette information.')}
                if candidate.patient_knows is True:
                    state['disclosed'] = sorted(set(state['disclosed']) | {candidate.stable_id})
                    state['runtime']['last_information_id'] = candidate.stable_id
            else:
                response = engine.respond(message, 2, state['conversation'])
        except AmbiguousQuestion:
            response = {'type': 'patient_response', 'content': 'Pouvez-vous préciser votre question ?'}
        except Exception:
            current_app.logger.exception('Teacher patient preview failed')
            return error('Le patient virtuel est temporairement indisponible.', 503)
        state['conversation'].extend([
            {'role': 'human', 'content': message},
            {'role': 'assistant', **response},
        ])
    previews[preview_id] = state
    session['kine_patient_previews'] = previews
    return jsonify(preview_id=preview_id, response=response, preview_only=True)
