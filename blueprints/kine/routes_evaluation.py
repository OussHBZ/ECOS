"""Case criteria, scoped review/publication, individual feedback and expiry command."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
import json
from flask import jsonify, render_template, request, redirect, url_for, send_file
from sqlalchemy.exc import IntegrityError
from auth import student_required
from case_versions import save_draft
from criterion_evaluation import normalize_criteria, calculate, reference, LABELS, ENGINE, STEPS, TYPES
from evaluation_lifecycle import record_change, student_result, feedback_allowed, deadline
from kine_permissions import kine_permission_required, require_simulation, actor
from models import db, PatientCase, SimulationSession, KineEvaluationChange, KineEvaluationSettings
from . import kine_bp
from .common import payload, wants_json, error
from .routes_versions import _actor
from .routes_student import _session_or_404, _complete_simulation


def current_thresholds():
    return {level: (db.session.get(KineEvaluationSettings, level).threshold if db.session.get(KineEvaluationSettings, level) else str(default))
            for level, default in [('licence', 12), ('master', 14)]}


@kine_bp.context_processor
def evaluation_authoring_context():
    return {'evaluation_thresholds_for_case': lambda: current_thresholds() if actor() in ('teacher', 'pedagogical') else {}}


def suggestions(case):
    # Only project existing authored expectations; no clinical invention or implicit activation.
    sources = []
    for index, c in enumerate(case.evaluation_checklist or []):
        if isinstance(c, dict) and c.get('description'):
            sources.append((f'legacy-{index}', 'final', c['description']))
    from rehabilitation import evaluation_inputs
    inputs = evaluation_inputs(case)
    for key, step in [('objectives', 'objectives'), ('surveillance', 'prescription')]:
        for index, value in enumerate(inputs.get(key, [])):
            expected = value.get('expected') or value.get('label') or value.get('title')
            if isinstance(expected, str) and expected:
                sources.append((f'{key}-{index}', step, expected))
    proposed = [{'id': cid, 'title': expected, 'expected': expected, 'step': step, 'type': 'decision',
                 'weight': '2', 'active': False, 'teacher_approved': False} for cid, step, expected in sources]
    for index, item in enumerate(case.information_items):
        if item.access_mode in ('question', 'deepening'):
            proposed.append({'id': f'information-{index}', 'title': f'Rechercher : {item.label}',
                'expected': f'Rechercher l’information : {item.label}', 'step': 'history', 'type': 'information_gathering',
                'weight': '2', 'active': False, 'teacher_approved': False})
    reasoning = case.structured_content.get('reasoning', {})
    for key in ('clinical_synthesis', 'expected_physiotherapy_diagnosis'):
        if isinstance(reasoning.get(key), str) and reasoning[key].strip():
            proposed.append({'id': key, 'title': 'Raisonnement clinique', 'expected': reasoning[key], 'step': 'reasoning',
                             'type': 'interpretation', 'active': False, 'teacher_approved': False, 'weight': '2'})
    return proposed


@kine_bp.route('/cases/<int:case_id>/criteria', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def case_criteria(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'POST':
        try:
            data = payload()
            rows = data.get('criteria') if request.is_json else json.loads(data.get('criteria_json', '[]'))
            content = deepcopy(case.structured_content)
            content['evaluation_criteria'] = normalize_criteria(rows)
            case.structured_content = content
            save_draft(case)
            db.session.commit()
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return error(str(exc))
        if not wants_json():
            return redirect(url_for('kine.case_criteria', case_id=case_id))
    criteria = case.structured_content.get('evaluation_criteria', [])
    if wants_json():
        return jsonify(criteria=criteria, suggestions=suggestions(case), thresholds=current_thresholds())
    return render_template('criteria_kine.html', clinical_case=case, criteria=criteria,
                           suggestions=suggestions(case), steps=STEPS, types=TYPES)


@kine_bp.route('/evaluation/thresholds', methods=['GET', 'POST'])
@kine_permission_required('thresholds.manage')
def evaluation_thresholds():
    if request.method == 'POST':
        try:
            data = payload()
            values = {level: reference([], level, data[level])['validation_threshold'] for level in ('licence', 'master')}
            for level, value in values.items():
                row = db.session.get(KineEvaluationSettings, level)
                if row is None:
                    row = KineEvaluationSettings(level=level)
                    db.session.add(row)
                row.threshold = value
            db.session.commit()
        except (ValueError, KeyError, TypeError) as exc:
            db.session.rollback()
            return error(str(exc))
    values = current_thresholds()
    if wants_json():
        return jsonify(values)
    return render_template('evaluation_thresholds_kine.html', values=values)


@kine_bp.route('/dashboard/simulation/<int:session_id>/classification', methods=['POST'])
@kine_permission_required('results.review')
def classify_criterion(session_id):
    simulation = require_simulation(session_id)
    before = deepcopy(simulation.evaluation_results or {})
    data = payload()
    if simulation.status != 'completed' or before.get('engine') != ENGINE:
        return error('Évaluation par critères terminée requise.', 409)
    try:
        if int(data.get('revision', -1)) != before['revision']:
            return error('Résultat modifié ; rechargez avant de vérifier.', 409)
        status = data.get('status')
        reason = str(data.get('reason') or '').strip()
        if status not in LABELS or not reason or len(reason) > 6000:
            raise ValueError('Classification et motif requis.')
        outcomes = deepcopy(before['criteria'])
        row = next((r for r in outcomes if r['id'] == data.get('criterion_id')), None)
        if row is None:
            raise ValueError('Critère absent du référentiel figé.')
        row.update(status=status, justification=reason, reviewed_by=_actor())
        if 'evidence_message_ids' in data or data.get('evidence_submitted') == 'yes':
            from kine_evaluation import _student_messages
            ids = data.get('evidence_message_ids', []) if request.is_json else request.form.getlist('evidence_message_ids')
            evidence = {m['id']: m for m in _student_messages(simulation.conversation or [], simulation.timeline)}
            if not isinstance(ids, list) or any(not isinstance(i, str) or i not in evidence for i in ids):
                raise ValueError('Preuves étudiantes invalides.')
            row['evidence'] = [{**evidence[i], 'message_id': i} for i in dict.fromkeys(ids)]
            row['omission'] = not bool(ids)
        resolution = data.get('safety_resolution')
        if resolution:
            ref = json.loads(simulation.evaluation_reference_json)
            definition = next(c for c in ref['criteria'] if c['id'] == row['id'])
            if definition['safety']['consequence'] != 'review' or resolution not in ('none', 'critical', 'eliminatory'):
                raise ValueError('Résolution non autorisée par les règles figées.')
            row['safety_resolution'] = resolution
        after = calculate(json.loads(simulation.evaluation_reference_json), outcomes)
        for key in ('student', 'vital_measurements'):
            if key in before:
                after[key] = before[key]
        record_change(simulation, before, after, _actor(), reason, row['id'])
        simulation.eliminatory_error_triggered = after['eliminatory_error_triggered']
        simulation.eliminatory_error = '; '.join(e['description'] for e in after['eliminatory_errors']) or None
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error('Une autre vérification a été enregistrée ; rechargez.', 409)
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        return error(str(exc))
    if not wants_json():
        return redirect(url_for('kine.dashboard_simulation', session_id=session_id))
    return jsonify(evaluation=after)


@kine_bp.route('/dashboard/simulation/<int:session_id>/evaluation-history')
@kine_permission_required('results.read')
def evaluation_history(session_id):
    require_simulation(session_id)
    return jsonify(changes=[{'revision': c.revision, 'actor': c.actor, 'at': c.created_at.isoformat(),
        'criterion_id': c.criterion_id, 'reason': c.reason, 'before': json.loads(c.before_json), 'after': json.loads(c.after_json)}
        for c in KineEvaluationChange.query.filter_by(simulation_id=session_id).order_by(KineEvaluationChange.revision)])


@kine_bp.route('/dashboard/simulation/<int:session_id>/feedback-publication', methods=['POST'])
@kine_permission_required('results.review')
def publish_feedback(session_id):
    simulation = require_simulation(session_id)
    before = deepcopy(simulation.evaluation_results or {})
    if simulation.status != 'completed' or before.get('result_status') == 'pending':
        return error('Résultat vérifié requis avant publication.', 409)
    try:
        if int(payload().get('revision', -1)) != before.get('revision'):
            return error('Résultat modifié ; rechargez.', 409)
        after = deepcopy(before)
        after['feedback_published_revision'] = before['revision'] + 1
        record_change(simulation, before, after, _actor(), 'Publication du bilan individuel')
        db.session.commit()
    except (ValueError, TypeError, IntegrityError):
        db.session.rollback()
        return error('Publication concurrente ou révision invalide.', 409)
    if not wants_json():
        return redirect(url_for('kine.dashboard_simulation', session_id=session_id))
    return jsonify(revision=after['revision'], published=True)


@kine_bp.route('/simulation/<int:session_id>/evaluation')
@student_required
def individual_evaluation(session_id):
    return jsonify(evaluation=student_result(_session_or_404(session_id)))


@kine_bp.route('/cases/<int:case_id>/aids', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def teaching_aids(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'POST':
        try:
            from teaching_aids import normalize_aids
            content = deepcopy(case.structured_content)
            data = payload()
            rows = data.get('aids') if request.is_json else [r for r in content.get('teaching_aids', []) if r['id'] != data.get('id')] + [{
                'id': data.get('id'), 'text': data.get('text'), 'information_id': data.get('information_id'),
                'active': data.get('active') == 'yes', 'teacher_approved': data.get('approved') == 'yes',
                'no_direct_answer': data.get('approved') == 'yes',
                'requires_information': [s.strip() for s in data.get('requires_information', '').split(',') if s.strip()]}]
            content['teaching_aids'] = normalize_aids(rows, case)
            case.structured_content = content
            save_draft(case)
            db.session.commit()
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return error(str(exc))
    aids = case.structured_content.get('teaching_aids', [])
    if wants_json():
        return jsonify(aids=aids)
    return render_template('teaching_aids_kine.html', clinical_case=case, aids=aids)


@kine_bp.route('/simulation/<int:session_id>/aids')
@student_required
def simulation_aids(session_id):
    from teaching_aids import available_aids
    simulation = _session_or_404(session_id)
    if simulation.mode != 'training' or simulation.status != 'in_progress':
        return error('Aides indisponibles dans ce mode ou cet état.', 403)
    return jsonify(channel='pedagogical', aids=available_aids(simulation))


@kine_bp.route('/simulation/<int:session_id>/pdf')
@student_required
def individual_pdf(session_id):
    from kine_personal_pdf import personal_pdf
    from case_versions import simulation_student, simulation_case, version_metadata
    simulation = _session_or_404(session_id)
    result = student_result(simulation)
    if not result:
        return error('Bilan indisponible.', 409)
    stream = personal_pdf(result, simulation_student(simulation), simulation_case(simulation),
        {**version_metadata(simulation), 'id': simulation.id,
         'mode': 'Examen' if simulation.mode == 'exam' else 'Entraînement',
         'date': simulation.started_at.strftime('%d/%m/%Y %H:%M UTC'), 'feedback_allowed': feedback_allowed(simulation)},
        simulation.teacher_comments if feedback_allowed(simulation) else None)
    return send_file(stream, as_attachment=True, download_name=f'bilan-{session_id}.pdf', mimetype='application/pdf')


@kine_bp.cli.command('expire-exams')
def expire_exams():
    """Run periodically by the deployment scheduler; no network/AI dependency."""
    count = 0
    for simulation in SimulationSession.query.join(PatientCase).filter(
            PatientCase.specialty == 'kine', SimulationSession.mode == 'exam', SimulationSession.status == 'in_progress'):
        if datetime.utcnow() >= deadline(simulation):
            _complete_simulation(simulation, completed_at=deadline(simulation), auto_closed=True)
            count += 1
    import click
    click.echo(f'{count} tentative(s) clôturée(s).')
