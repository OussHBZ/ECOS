"""Read-only reporting of saved results; never recalculate historical evaluations."""
from collections import Counter, defaultdict
from datetime import datetime
from fractions import Fraction

from criterion_evaluation import ENGINE

COMPETENCIES = {
    'clinical_record': 'Dossier clinique', 'history': 'Anamnèse',
    'assessment': 'Bilan kinésithérapique', 'reasoning': 'Raisonnement clinique',
    'objectives': 'Objectifs / SMART', 'prescription': 'Prescription / FITT-VP',
    'etp': 'Éducation thérapeutique', 'final': 'Synthèse finale',
}


def result_status(result):
    if not result:
        return 'unevaluated'
    return result.get('result_status') or ('passed' if result.get('passed') else 'failed')


def duration_minutes(simulation, now=None):
    interrupted = (simulation.runtime_state or {}).get('interrupted_at')
    end = simulation.completed_at or (datetime.fromisoformat(interrupted) if interrupted else None) or simulation.paused_at or now or datetime.utcnow()
    return max(0, (end - simulation.started_at).total_seconds() - (simulation.total_paused_seconds or 0)) / 60


def evaluated_criteria(result):
    if result.get('engine') != ENGINE:
        # Legacy sections retain their own definitions and are not reclassified.
        return []
    return [r for r in result.get('criteria', [])
            if r.get('applicable', True) and r.get('max_points', 0) > 0]


def selected_criteria(result, filters):
    return [r for r in evaluated_criteria(result)
            if (not filters.get('competency') or r.get('step') == filters['competency'])
            and (not filters.get('criterion') or r.get('id') == filters['criterion'])]


def matches(row, filters):
    for key, field in [('student_id', 'student_id'), ('level', 'student_level'),
                       ('version_id', 'case_version_id'), ('mode', 'mode'), ('case_id', 'case_id'), ('status', 'status'), ('result', 'result_status')]:
        if filters.get(key) and str(row.get(field)) != str(filters[key]):
            return False
    if filters.get('competency') or filters.get('criterion'):
        return bool(selected_criteria(row.get('evaluation', {}), filters))
    return True


def aggregate(rows, filters=None):
    filters = filters or {}
    scored = [r['score'] for r in rows if r['status'] == 'completed'
              and r['result_status'] != 'pending' and isinstance(r.get('score'), (int, float))]
    groups = {'competencies': {}, 'criteria': {}}
    for row in rows:
        if row['status'] != 'completed':
            continue
        for c in selected_criteria(row.get('evaluation', {}), filters):
            for kind, key, name in [
                ('competencies', c['step'], COMPETENCIES.get(c['step'], c['step'])),
                ('criteria', f"{row.get('case_version_id')}:{row['case_number']}:{c['id']}", c['title']),
            ]:
                bucket = groups[kind].setdefault(key, dict(key=key, name=name, count=0, provisional=0,
                    satisfied=0, partial=0, failed=0, pending=0, omissions=0, safety=0,
                    earned=Fraction(0), possible=Fraction(0), series=[]))
                bucket['count'] += 1
                if row['result_status'] == 'pending':
                    bucket['provisional'] += 1
                    bucket['pending'] += bool(c.get('review_required'))
                    continue  # Entire provisional attempts stay outside definitive totals.
                state = c.get('status')
                bucket['pending' if c.get('review_required') else 'satisfied' if state in ('correct', 'acceptable')
                       else 'partial' if state == 'partial' else 'failed'] += 1
                bucket['omissions'] += bool(c.get('omission'))
                bucket['safety'] += c.get('safety_consequence', 'none') != 'none'
                if not c.get('review_required') and c.get('points') is not None:
                    bucket['earned'] += Fraction(str(c['points']))
                    bucket['possible'] += Fraction(str(c['max_points']))
                    bucket['series'].append(dict(simulation_id=row['id'], date=row['started_at'],
                        points=c['points'], maximum=c['max_points'], mode=row['mode']))
    for kind in groups:
        for b in groups[kind].values():
            b['percentage'] = round(float(b['earned'] / b['possible'] * 100), 2) if b['possible'] else None
            b['earned'], b['possible'] = float(b['earned']), float(b['possible'])
            b['series'].sort(key=lambda item: item['date'])
        groups[kind] = list(groups[kind].values())
    return dict(stats=dict(student_count=len({r['student_id'] for r in rows}), simulation_count=len(rows),
        scored_count=len(scored), pending_count=sum(r['result_status'] == 'pending' for r in rows),
        average_score=round(sum(scored) / len(scored), 2) if scored else None,
        average_duration=round(sum(r['duration_minutes'] for r in rows) / len(rows), 1) if rows else None),
        **groups, dimensions={key: dict(Counter(str(r.get(key)) for r in rows))
            for key in ('case_version_id', 'mode', 'status', 'result_status')})


def feedback_summary(result):
    rows = evaluated_criteria(result)
    return dict(satisfied=sum(r['status'] in ('correct', 'acceptable') for r in rows),
        partial=sum(r['status'] == 'partial' for r in rows),
        failed=sum(r['status'] in ('incorrect', 'dangerous') for r in rows),
        pending=sum(bool(r.get('review_required')) for r in rows),
        omissions=sum(bool(r.get('omission')) for r in rows))
