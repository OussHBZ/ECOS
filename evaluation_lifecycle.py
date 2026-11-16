"""Append-only review evidence and one student-facing result policy."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from sqlalchemy import event, text
from models import db, KineEvaluationChange, KineEvaluationSettings
from criterion_evaluation import reference, calculate, ENGINE


def frozen_reference(version, student, simulation):
    data = json.loads(version.content_json)
    settings = db.session.get(KineEvaluationSettings, student.level)
    ref = reference(data.get('evaluation_criteria', []), student.level, settings.threshold if settings else None)
    if simulation.mode == 'exam':
        simulation.started_at = simulation.started_at or datetime.utcnow()
        ref['deadline'] = min(simulation.exam.end_at, simulation.started_at + timedelta(minutes=simulation.exam.max_duration_minutes)).isoformat()
    return ref


def deadline(simulation):
    if simulation.mode != 'exam':
        return None
    ref = json.loads(simulation.evaluation_reference_json or '{}')
    if ref.get('deadline'):
        return datetime.fromisoformat(ref['deadline'])
    if simulation.exam:
        return min(simulation.exam.end_at, simulation.started_at + timedelta(minutes=simulation.exam.max_duration_minutes))
    return simulation.started_at  # Missing exam cannot create an unlimited attempt.


def record_change(simulation, before, after, actor, reason, criterion_id=None):
    from case_versions import canonical
    revision = (before or {}).get('revision', 0) + 1
    after['revision'] = revision
    db.session.add(KineEvaluationChange(simulation_id=simulation.id, revision=revision,
        actor=actor, reason=reason, criterion_id=criterion_id,
        before_json=canonical(before), after_json=canonical(after)))
    simulation.evaluation_results = after


def feedback_allowed(simulation):
    result = simulation.evaluation_results or {}
    return simulation.status == 'completed' and (simulation.mode == 'training' or result.get('feedback_published_revision') == result.get('revision') and result.get('revision') is not None)


def student_result(simulation):
    result = simulation.evaluation_results
    if not result or simulation.status != 'completed':
        return None
    keys = ('schema_version', 'engine', 'result_status', 'status_label', 'points_earned', 'score_display', 'points_total', 'passed', 'rounded_below_threshold')
    public = {k: deepcopy(result[k]) for k in keys if k in result}
    if not feedback_allowed(simulation):
        return public
    if result.get('engine') != ENGINE:
        from information_access import redact_reserved
        # Historical storage is immutable in meaning, but arbitrary internal fields
        # must never become public merely because an old result contains them.
        safe_keys = set(keys) | {'specialty', 'level', 'grid_name', 'validation_threshold',
            'student', 'name', 'student_code', 'group_name', 'class_name',
            'section_scores', 'criteria', 'id', 'title', 'criterion', 'status', 'status_label',
            'points_possible', 'expected_elements', 'detected_elements', 'partial_elements',
            'missing_elements', 'evidence', 'message_id', 'quote', 'phase', 'timestamp',
            'justification', 'feedback', 'elimination_cap', 'eliminatory_error_triggered',
            'eliminatory_errors', 'description'}
        def project(value):
            if isinstance(value, dict):
                return {k: project(v) for k, v in value.items() if k in safe_keys}
            if isinstance(value, list):
                return [project(v) for v in value]
            return deepcopy(value)
        return redact_reserved(project(result), simulation.case_version)
    public.update(level=result['level'], validation_threshold=result['validation_threshold'], student=deepcopy(result.get('student', {})))
    ref = json.loads(simulation.evaluation_reference_json)
    definitions = {c['id']: c for c in ref['criteria']}
    public['criteria'] = []
    for row in result['criteria']:
        c = definitions[row['id']]
        if not c['active'] or not c['teacher_approved'] or not row['applicable'] or c['importance'] == 'not_evaluated':
            continue
        item = {k: deepcopy(row[k]) for k in ('id', 'status', 'status_label', 'points', 'max_points', 'evidence', 'justification', 'review_required', 'safety_consequence')}
        item['omission'] = bool(row.get('omission'))
        item.update(title=c['title'], type=c['type'], step=c['step'])
        # Individual relevant expectations only; never the full private configuration.
        if row['status'] != 'pending':
            item.update(expected=c['expected'], alternatives=c['alternatives'])
        public['criteria'].append(item)
    public['critical_errors'] = deepcopy(result.get('critical_errors', []))
    from kine_reporting import feedback_summary
    public['summary'] = feedback_summary(public)
    public['criteria'].sort(key=lambda r: (r['safety_consequence'] == 'none', r['step'] != 'reasoning'))
    return public


def student_simulation(simulation):
    """Templates receive a projection, never the ORM object carrying private fields."""
    values = {c.name: deepcopy(getattr(simulation, c.name)) for c in simulation.__table__.columns}
    values['evaluation_results'] = student_result(simulation)
    for key in ('teacher_comments', 'supplementary_score', 'reviewed_at'):
        if not feedback_allowed(simulation):
            values[key] = None
    values['runtime_state'] = {}
    values['evaluation_reference_json'] = None
    values['eliminatory_error'] = None
    from case_versions import simulation_student, simulation_case
    values['student'] = simulation_student(simulation)
    case = simulation_case(simulation)
    values['clinical_case'] = SimpleNamespace(case_number=case.case_number, title=case.title)
    return SimpleNamespace(**values)


def student_timeline(simulation):
    allowed = {'simulation_started', 'student_message', 'patient_response', 'phase_changed', 'phase_navigation_denied',
               'simulation_paused', 'simulation_resumed', 'simulation_abandoned', 'network_reconnected', 'exam_auto_closed', 'session_action', 'session_event', 'effort_measurement'}
    # Evaluation/review events are internal even after publication; feedback has its own projection.
    return [deepcopy(e) for e in simulation.timeline or [] if e.get('action') in allowed]


@event.listens_for(KineEvaluationChange, 'before_update')
@event.listens_for(KineEvaluationChange, 'before_delete')
def immutable_change(*args):
    raise ValueError('Historique d’évaluation immuable.')


@event.listens_for(KineEvaluationChange.__table__, 'after_create')
def evaluation_guards(table, connection, **kwargs):
    if connection.dialect.name == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            connection.execute(text(f"CREATE TRIGGER IF NOT EXISTS evaluation_change_no_{operation.lower()} BEFORE {operation} ON kine_evaluation_changes BEGIN SELECT RAISE(ABORT, 'immutable evaluation history'); END"))
