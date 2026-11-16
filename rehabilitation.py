"""Versioned authoring contracts, not a clinical inference or scoring engine."""
from copy import deepcopy
import math
import re

ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
CATEGORIES = {
    'aerobic': 'Aérobie / endurance cardiorespiratoire',
    'strength': 'Renforcement musculaire', 'functional': 'Exercices fonctionnels',
    'mobility': 'Mobilité / souplesse', 'balance': 'Équilibre / contrôle postural',
    'respiratory': 'Exercices respiratoires', 'recovery': 'Récupération / retour au calme',
}

# PDF pp. 39–44: authoring suggestions, never active evaluation criteria.
MODALITIES = {
    'aerobic': ['Marche', 'Vélo ergométrique', 'Tapis roulant', 'Danse adaptée', 'Exercices aquatiques', 'Circuit aérobie'],
    'strength': ['Poids du corps', 'Élastiques', 'Charges libres', 'Haltères', 'Machines', 'Résistance manuelle', 'Circuit de renforcement'],
    'functional': ['Sit-to-stand', 'Escaliers', 'Marche fonctionnelle', 'Transferts', 'Activités de la vie quotidienne', 'Parcours fonctionnel'],
    'mobility': ['Mobilité active', 'Mobilité active-assistée', 'Étirements'],
    'balance': ['Équilibre statique', 'Équilibre dynamique', 'Transferts de poids', 'Appui unipodal', 'Coordination', 'Double tâche'],
    'respiratory': ['Respiration diaphragmatique', 'Contrôle ventilatoire', 'Coordination respiration-mouvement', 'Récupération respiratoire'],
    'recovery': ['Marche lente', 'Mobilité douce', 'Respiration contrôlée', 'Diminution progressive de l’intensité', 'Relaxation adaptée'],
}
SURVEILLANCE_SUGGESTIONS = {
    'aerobic': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Effort/Borg', 'Palpitations', 'Vertiges/malaise', 'Tolérance générale', 'Fatigue', 'Douleur', 'Réponse à l’intensité'],
    'strength': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Effort/Borg', 'Douleur musculaire/articulaire', 'Technique', 'Compensation', 'Respiration', 'Tolérance de la charge', 'Nombre de répétitions'],
    'functional': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Effort/Borg', 'Fatigue', 'Tolérance fonctionnelle', 'Vertiges/malaise', 'Équilibre', 'Qualité du mouvement', 'Vitesse d’exécution', 'Besoin d’aide', 'Récupération'],
    'mobility': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Fatigue', 'Qualité du mouvement', 'Douleur', 'Amplitude', 'Vertiges', 'Tolérance', 'Cicatrice/zone opérée', 'Restrictions médicales'],
    'balance': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Fatigue', 'Vertiges', 'Besoin d’aide', 'Qualité du mouvement', 'Compensation'],
    'respiratory': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Fatigue', 'Douleur', 'Type respiratoire', 'Travail respiratoire', 'Symétrie', 'Toux', 'Expectorations', 'Coloration', 'Tolérance', 'Récupération'],
    'recovery': ['PA', 'SpO₂', 'FR', 'Dyspnée', 'Fatigue', 'Temps de récupération', 'Tolérance globale', 'Palpitations', 'Vertiges/malaise'],
}
OBJECTIVE_SUGGESTIONS = ['Capacité fonctionnelle', 'Tolérance à l’effort', 'Dyspnée à l’effort', 'Force musculaire', 'Endurance musculaire', 'Autonomie', 'Équilibre', 'Marche', 'Activités quotidiennes', 'Activité physique', 'Qualité de vie']


def rows(value, label):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(f'{label} : liste requise (100 maximum).')
    seen = set()
    for row in value:
        if not isinstance(row, dict) or not ID.fullmatch(str(row.get('id', ''))) or row['id'] in seen:
            raise ValueError(f'{label} : identifiants uniques requis.')
        seen.add(row['id'])
    return value


def quantity(value):
    """Exact, range, choices or qualitative; units are explicit, never converted."""
    if not isinstance(value, dict) or value.get('kind') not in ('exact', 'range', 'choices', 'qualitative'):
        raise ValueError('Valeur structurée invalide.')
    kind = value['kind']
    if kind == 'qualitative':
        if not isinstance(value.get('value'), str) or not value['value'].strip():
            raise ValueError('Description qualitative requise.')
        return value
    if not isinstance(value.get('unit'), str) or not value['unit'].strip():
        raise ValueError('Unité requise.')
    numbers = ([value.get('min'), value.get('max')] if kind == 'range' else
               value.get('values') if kind == 'choices' else [value.get('value')])
    if not isinstance(numbers, list) or not numbers or any(
        isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) for n in numbers
    ):
        raise ValueError('Valeurs numériques finies requises.')
    if kind == 'range' and numbers[0] > numbers[1]:
        raise ValueError('Plage inversée.')
    return value


def accepts(reference, proposal):
    """Mechanical compatibility only; no score or clinical equivalence inferred."""
    quantity(reference)
    if proposal.get('unit') != reference.get('unit'):
        return False
    v = proposal.get('value')
    if reference['kind'] == 'qualitative':
        return v == reference['value']
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return False
    if reference['kind'] == 'range':
        return reference['min'] <= v <= reference['max']
    return v in reference['values'] if reference['kind'] == 'choices' else v == reference['value']


def weekly_volume(fitt):
    """Mechanical minutes/week only; never replaces the teacher's reference."""
    duration = fitt.get('duration', {})
    frequency = fitt.get('frequency', {})
    time = duration.get('quantity', {})
    if duration.get('applicability') != 'required' or time.get('unit') != 'min/session' or frequency.get('unit') != 'sessions/week':
        return None
    quantity(time); quantity(frequency)
    if time['kind'] == 'qualitative' or frequency['kind'] == 'qualitative':
        return None
    def numbers(q):
        return [q['min'], q['max']] if q['kind'] == 'range' else q['values'] if q['kind'] == 'choices' else [q['value']]
    values = sorted({t * f for t in numbers(time) for f in numbers(frequency)})
    if 'range' in (time['kind'], frequency['kind']):
        return {'kind': 'range', 'min': values[0], 'max': values[-1], 'unit': 'min/week'}
    return {'kind': 'exact', 'value': values[0], 'unit': 'min/week'} if len(values) == 1 else {'kind': 'choices', 'values': values, 'unit': 'min/week'}


def normalize_rehabilitation(value):
    if not isinstance(value, dict):
        raise ValueError('Rééducation structurée invalide.')
    result = deepcopy(value)
    for objective in rows(result.get('objectives', []), 'Objectifs SMART'):
        for key in ('specific', 'measurable', 'achievable', 'relevant', 'time_bound'):
            if not isinstance(objective.get(key), str) or not objective[key].strip():
                raise ValueError(f'Objectif SMART : {key} requis.')
    # Additional categories are local to the case; no global taxonomy permission inferred.
    categories = dict(CATEGORIES)
    for category in rows(result.get('categories', []), 'Catégories du cas'):
        if not category.get('label'):
            raise ValueError('Libellé de catégorie requis.')
        categories[category['id']] = category['label']
    exercises = rows(result.get('exercises', []), 'Exercices')
    exercise_ids = {x['id'] for x in exercises}
    for exercise in exercises:
        if exercise.get('category') not in categories or not exercise.get('modality'):
            raise ValueError('Catégorie et modalité requises.')
        alternatives = exercise.get('acceptable_alternatives', [])
        if not isinstance(alternatives, list) or len(alternatives) > 50:
            raise ValueError('Liste d’alternatives FITT-VP requise (50 maximum).')
        variants = [exercise.get('fitt', {})] + alternatives
        if not all(isinstance(v, dict) for v in variants):
            raise ValueError('Alternatives FITT-VP invalides.')
        for fitt in variants:
            if not fitt.get('type'):
                raise ValueError('Type de prescription requis.')
            for field in ('frequency', 'duration', 'volume'):
                if field not in fitt:
                    continue
                spec = fitt[field]
                if field in ('duration', 'volume'):
                    if not isinstance(spec, dict):
                        raise ValueError('Durée/volume structuré requis.')
                    if spec.get('applicability') not in ('required', 'conditional', 'not_applicable'):
                        raise ValueError('Applicabilité durée/volume requise.')
                    if spec['applicability'] == 'conditional' and not spec.get('condition'):
                        raise ValueError('Condition durée/volume requise.')
                    if spec['applicability'] == 'not_applicable':
                        if 'quantity' in spec:
                            raise ValueError('Champ non applicable avec valeur.')
                        continue
                    quantity(spec.get('quantity'))
                else:
                    quantity(spec)
            for intensity in rows(fitt.get('intensity', []), 'Méthodes d’intensité'):
                if not intensity.get('method') or intensity.get('role') not in ('reference', 'acceptable'):
                    raise ValueError('Méthode et statut d’intensité requis.')
                if any(k in intensity for k in ('stop_conditions', 'adaptation_rules')):
                    raise ValueError('Séparez intensité, adaptation et arrêt.')
                quantity(intensity.get('target'))
                if intensity['method'] in ('borg', 'rpe', 'dyspnea') and not intensity.get('scale'):
                    raise ValueError('Échelle d’intensité requise.')
                if intensity['method'] in ('percent_hrmax', 'heart_rate_reserve', 'percent_capacity') and not intensity.get('reference'):
                    raise ValueError('Référentiel d’intensité requis.')
            for rule in rows(fitt.get('progression', []), 'Progression'):
                if not rule.get('condition') or not rule.get('change'):
                    raise ValueError('Condition et changement de progression requis.')
            for component in rows(fitt.get('components', []), 'Composants de séance'):
                if not component.get('label'):
                    raise ValueError('Libellé de composant requis.')
                for key in ('duration', 'repetitions', 'sets', 'recovery', 'distance', 'load', 'stations', 'circuits', 'steps'):
                    if key in component:
                        quantity(component[key])
                for parameter in rows(component.get('custom_parameters', []), 'Paramètres complémentaires'):
                    if not parameter.get('label'):
                        raise ValueError('Nom du paramètre complémentaire requis.')
                    quantity(parameter.get('quantity'))
    for name in ('surveillance', 'adaptation_rules', 'stop_conditions'):
        for rule in rows(result.get(name, []), name):
            if any(k in rule and not isinstance(rule[k], bool) for k in ('active', 'teacher_approved')):
                raise ValueError('Activation et validation doivent être explicites.')
            if rule.get('exercise_id') and rule['exercise_id'] not in exercise_ids:
                raise ValueError('Exercice de surveillance inconnu.')
            if not rule.get('description'):
                raise ValueError('Description de règle requise.')
            if rule.get('active', False) and rule.get('teacher_approved') is not True:
                raise ValueError('Validation enseignant requise pour activer une règle.')
            if rule.get('importance') == 'unused' and rule.get('active'):
                raise ValueError('Un critère non utilisé ne peut pas être actif.')
            if name != 'surveillance' and (not rule.get('condition') or not rule.get('action')):
                raise ValueError('Condition et conduite requises.')
    session = result.get('session', {})
    if not isinstance(session, dict):
        raise ValueError('Scénario de séance invalide.')
    if 'enabled' in session and not isinstance(session['enabled'], bool):
        raise ValueError('Activation de séance invalide.')
    for event in rows(session.get('events', []), 'Évolutions de séance'):
        trigger = event.get('trigger')
        if isinstance(trigger, dict):
            trigger = {k: v for k, v in trigger.items() if v not in (None, '', [])}
            event['trigger'] = trigger
        if not isinstance(trigger, dict) or not trigger or set(trigger) - {'phase', 'action_contains', 'exercise_id', 'elapsed_seconds_min', 'requires'}:
            raise ValueError('Déclencheur de séance invalide.')
        if 'elapsed_seconds_min' in trigger:
            t = trigger['elapsed_seconds_min']
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
                raise ValueError('Durée du déclencheur invalide.')
        if trigger.get('exercise_id') and trigger['exercise_id'] not in exercise_ids:
            raise ValueError('Exercice du scénario inconnu.')
        if 'action_contains' in trigger and (not isinstance(trigger['action_contains'], str) or not trigger['action_contains'].strip()):
            raise ValueError('Action déclencheuse invalide.')
        if 'phase' in trigger and (isinstance(trigger['phase'], bool) or str(trigger['phase']) not in {str(i) for i in range(1, 10)}):
            raise ValueError('Étape du scénario invalide.')
        if event.get('kind') not in ('evolution', 'incident') or not event.get('reaction'):
            raise ValueError('Type et réaction scénarisée requis.')
        if not isinstance(event['reaction'], str):
            raise ValueError('Réaction patient textuelle requise.')
        if session.get('enabled') and event.get('teacher_approved') is not True:
            raise ValueError('Validez chaque événement avant activation de la séance.')
        for measurement in rows(event.get('measurements', []), 'Mesures du scénario'):
            if measurement.get('delivery') not in ('automatic', 'on_request') or not measurement.get('name') or 'value' not in measurement:
                raise ValueError('Mesure scénarisée invalide.')
            if 'allowed_range' in measurement:
                if not accepts(measurement['allowed_range'], measurement):
                    raise ValueError('Mesure hors de la plage validée.')
    event_ids = {e['id'] for e in session.get('events', [])}
    for event in session.get('events', []):
        requires = event['trigger'].get('requires', [])
        if not isinstance(requires, list) or any(i not in event_ids or i == event['id'] for i in requires):
            raise ValueError('Prérequis du scénario invalide.')
    result['schema_version'] = 1
    return result


def evaluation_inputs(case):
    """Private T13/T14 input. No weight, classification or ETP score is invented."""
    content = case.structured_content or {}
    rehab = content.get('rehabilitation_program') or {}
    return {
        'schema_version': 1, 'objectives': deepcopy(rehab.get('objectives', [])),
        'prescriptions': deepcopy(rehab.get('exercises', [])),
        **{name: [deepcopy(r) for r in rehab.get(name, []) if r.get('active') is True and r.get('teacher_approved') is True]
           for name in ('surveillance', 'adaptation_rules', 'stop_conditions')},
        'etp': [deepcopy(a) for a in content.get('etp_associations', []) if a.get('status') == 'validated'],
    }


def advance_session(program, state, action, *, phase=None, exercise_id=None, elapsed_seconds=0):
    """Consume all matching authored events once. No interpolation or random incidents."""
    state = deepcopy(state or {})
    session = program.get('session') or {}
    if session.get('enabled') is not True:
        return state, []
    triggered = list(state.get('session_events', []))
    emitted = []
    for event in session.get('events', []):
        if event['id'] in triggered or event.get('teacher_approved') is not True:
            continue
        t = event['trigger']
        checks = [
            'phase' not in t or str(t['phase']) == str(phase),
            'action_contains' not in t or t['action_contains'].casefold() in action.casefold(),
            'exercise_id' not in t or t['exercise_id'] == exercise_id,
            'elapsed_seconds_min' not in t or elapsed_seconds >= t['elapsed_seconds_min'],
            all(i in triggered for i in t.get('requires', [])),
        ]
        if all(checks):
            triggered.append(event['id'])
            emitted.append(deepcopy(event))
    state['session_events'] = triggered
    state.setdefault('session_measurements', {})
    for event in emitted:
        for measurement in event.get('measurements', []):
            state['session_measurements'][f"{event['id']}:{measurement['id']}"] = deepcopy(measurement)
    return state, emitted
