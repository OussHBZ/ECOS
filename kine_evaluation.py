"""Shared, specialty-gated physiotherapy evaluation logic."""

import json
import logging
import re
import unicodedata

from langchain_core.messages import HumanMessage

from evaluation_config import apply_kine_elimination_cap, get_kine_evaluation_grid

logger = logging.getLogger(__name__)

STATUSES = {'realized', 'partial', 'not_realized'}
STATUS_LABELS = {
    'realized': 'Réalisé',
    'partial': 'Partiellement réalisé',
    'not_realized': 'Non réalisé',
}
STOP_WORDS = {
    'adapté', 'adaptée', 'avec', 'dans', 'des', 'définie', 'définis', 'et',
    'évalué', 'évaluée', 'exploré', 'explorés', 'fournis', 'incluse', 'inclus',
    'intégrée', 'intégrés', 'les', 'prise', 'recherché', 'recherchés',
    'réalisé', 'réalisés', 'selon', 'une',
}
KEYWORD_ALIASES = {
    'dyspnee': {'dyspnee', 'essouffle', 'essoufflement', 'souffle', 'respirer', 'orthopnee', 'mrc'},
    'douleur': {'douleur', 'mal', 'eva'},
    'fatigue': {'fatigue', 'epuise', 'epuisement'},
    'activite': {'activite', 'marche', 'marcher', 'escalier', 'distance', 'effort'},
    'ecoute': {'ecoute', 'comprends', 'reformul', 'bonjour', 'rassur'},
    'empathie': {'empathie', 'comprends', 'desole', 'rassur'},
    'constantes': {'constante', 'tension', 'pression', 'pouls', 'frequence', 'spo2', 'saturation'},
    'surveillance': {'surveille', 'monitor', 'tension', 'pouls', 'frequence', 'spo2', 'borg'},
    'traitements': {'traitement', 'medicament', 'ordonnance'},
    'exercices': {'exercice', 'marche', 'velo', 'tapis', 'renforcement'},
    'incident': {'incident', 'arret', 'arrete', 'secur', 'urgence', 'appel', 'medecin'},
}


def is_kine_case(case_data):
    return str((case_data or {}).get('specialty') or '').strip().lower() == 'kine'


def resolve_student_level(case_data):
    """Use only the authoritative persisted Student level."""
    student = (case_data or {}).get('student')
    level = getattr(student, 'level', None)
    normalized = str(level or 'licence').strip().lower()
    return normalized if normalized in ('licence', 'master') else 'licence'


def _normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def _student_messages(conversation, timeline=None):
    """Return authoritative student-only evidence candidates."""
    timeline_messages = [
        event for event in (timeline or [])
        if event.get('action') == 'student_message'
    ]
    timeline_index = 0
    messages = []
    for message in conversation or []:
        if message.get('role') != 'human':
            continue
        event = timeline_messages[timeline_index] if timeline_index < len(timeline_messages) else {}
        timeline_index += 1
        messages.append({
            'id': f"message_{len(messages) + 1}",
            'quote': str(message.get('content') or '').strip(),
            'phase': message.get('phase', event.get('phase')),
            'phase_key': message.get('phase_key'),
            'timestamp': message.get('timestamp') or event.get('timestamp'),
        })
    return messages


def _extract_json(text):
    match = re.search(r'```(?:json)?\s*({.*})\s*```', text or '', re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'({.*})', text or '', re.DOTALL)
    return json.loads(match.group(1)) if match else None


def _llm_evaluation(llm_client, student_messages, case_data, grid):
    sections = [{
        'id': section['id'],
        'criterion': section['criterion'],
        'max_points': section['points'],
        'criteria': [
            {'id': f"{section['id']}__{index}", 'expected': indicator}
            for index, indicator in enumerate(section['ai_indicators'], start=1)
        ],
    } for section in grid['sections']]
    context = {
        key: value for key, value in (case_data or {}).items()
        if key not in {'student', 'evaluation_checklist', 'timeline'}
    }
    prompt = f"""Vous êtes un évaluateur strict d'ECOS en kinésithérapie.
Vous devez évaluer UNIQUEMENT les messages étudiants fournis ci-dessous.
Les réponses du patient sont volontairement absentes et ne constituent jamais une preuve.

Pour chaque critère :
- choisissez realized, partial ou not_realized ;
- référencez uniquement les identifiants exacts message_N ;
- n'utilisez jamais deux fois le même message comme preuve de score ;
- décrivez les éléments détectés, partiels et absents ;
- rédigez une justification factuelle et claire en français.
Une preuve sans identifiant valide sera rejetée par le serveur.

SECTIONS ET CRITÈRES :
{json.dumps(sections, ensure_ascii=False)}

ERREURS ÉLIMINATOIRES :
{json.dumps(grid['elimination_rules'], ensure_ascii=False)}

CONTEXTE DU CAS :
{json.dumps(context, ensure_ascii=False, default=str)}

MESSAGES ÉTUDIANTS AUTORISÉS :
{json.dumps(student_messages, ensure_ascii=False)}

Retournez uniquement ce JSON :
{{
  "section_scores": [{{
    "id": "section id",
    "criteria": [{{
      "id": "criterion id",
      "status": "realized|partial|not_realized",
      "evidence_message_ids": ["message_1"],
      "detected_elements": ["élément explicite"],
      "partial_elements": [],
      "missing_elements": [],
      "justification": "justification en français"
    }}],
    "justification": "synthèse de section en français"
  }}],
  "eliminatory_errors": [{{
    "id": "rule id",
    "justification": "raison en français",
    "evidence_message_ids": ["message_2"]
  }}],
  "feedback": "feedback global concis en français"
}}"""
    response = llm_client.invoke(
        [HumanMessage(content=prompt)],
        {'max_tokens': 5000, 'temperature': 0.1},
    )
    parsed = _extract_json(response.content)
    if not isinstance(parsed, dict):
        raise ValueError('Kine evaluator returned no valid JSON object')
    return parsed


def _keyword_set(expected):
    normalized = _normalize(expected)
    keywords = {
        token for token in normalized.split()
        if len(token) >= 4 and token not in {_normalize(word) for word in STOP_WORDS}
    }
    expanded = set(keywords)
    for key, aliases in KEYWORD_ALIASES.items():
        if key in keywords or key in normalized:
            expanded.update(aliases)
    return expanded


def _pattern_evaluation(student_messages, grid):
    """Conservative, student-only offline evaluation with exact evidence IDs."""
    used_messages = set()
    section_scores = []
    for section in grid['sections']:
        criteria = []
        for index, expected in enumerate(section['ai_indicators'], start=1):
            keywords = _keyword_set(expected)
            best = None
            best_matches = set()
            for message in student_messages:
                if message['id'] in used_messages:
                    continue
                text = _normalize(message['quote'])
                matches = {keyword for keyword in keywords if keyword in text}
                if len(matches) > len(best_matches):
                    best, best_matches = message, matches
            if best_matches:
                used_messages.add(best['id'])
                status = 'realized' if len(best_matches) >= 3 else 'partial'
                evidence_ids = [best['id']]
            else:
                status, evidence_ids = 'not_realized', []
            criteria.append({
                'id': f"{section['id']}__{index}",
                'status': status,
                'evidence_message_ids': evidence_ids,
                'detected_elements': [expected] if status == 'realized' else [],
                'partial_elements': [expected] if status == 'partial' else [],
                'missing_elements': [expected] if status == 'not_realized' else [],
                'justification': (
                    'Le message étudiant cité apporte une preuve complète.'
                    if status == 'realized'
                    else 'Le message étudiant cité aborde cet élément sans le réaliser complètement.'
                    if status == 'partial'
                    else 'Aucun message étudiant ne fournit de preuve pour cet élément.'
                ),
            })
        section_scores.append({
            'id': section['id'],
            'criteria': criteria,
            'justification': 'Évaluation locale fondée uniquement sur les messages de l’étudiant.',
        })

    text_by_id = {
        message['id']: _normalize(message['quote'])
        for message in student_messages
    }
    errors = []
    exertion_ids = [
        message_id for message_id, text in text_by_id.items()
        if any(term in text for term in ('exercice', 'effort', 'marche', 'velo', 'tapis', 'echauffement'))
    ]
    all_student_text = ' '.join(text_by_id.values())
    has_vitals = all(
        any(term in all_student_text for term in terms)
        for terms in (
            ('tension', 'pression arterielle', ' pa '),
            ('frequence cardiaque', 'pouls', ' fc '),
            ('spo2', 'saturation'),
        )
    )
    if exertion_ids and not has_vitals:
        errors.append({
            'id': 'missing_initial_vitals',
            'justification': "L’effort a débuté sans contrôle explicite de la PA, de la FC et de la SpO₂.",
            'evidence_message_ids': [exertion_ids[0]],
        })
    dangerous_ids = [
        message_id for message_id, text in text_by_id.items()
        if any(term in text for term in ('100', 'intensite maximale', 'jusqu a epuisement'))
    ]
    if dangerous_ids:
        errors.append({
            'id': 'dangerous_exercise_or_intensity',
            'justification': 'Une intensité explicitement dangereuse ou maximale a été prescrite.',
            'evidence_message_ids': [dangerous_ids[0]],
        })
    return {
        'section_scores': section_scores,
        'eliminatory_errors': errors,
        'feedback': 'Évaluation kinésithérapique locale fondée sur les messages étudiants.',
    }


def _criterion_weights(total, count):
    if not count:
        return []
    weights = []
    remaining = float(total)
    for index in range(count):
        weight = remaining if index == count - 1 else round(float(total) / count, 2)
        weights.append(round(weight, 2))
        remaining -= weight
    return weights


def _evidence_from_ids(ids, messages_by_id, used_ids=None):
    evidence = []
    seen = set()
    for message_id in ids or []:
        message_id = str(message_id)
        if message_id in seen or message_id not in messages_by_id:
            continue
        if used_ids is not None and message_id in used_ids:
            continue
        seen.add(message_id)
        if used_ids is not None:
            used_ids.add(message_id)
        message = messages_by_id[message_id]
        evidence.append({
            'message_id': message_id,
            'quote': message['quote'],
            'phase': message.get('phase'),
            'phase_key': message.get('phase_key'),
            'timestamp': message.get('timestamp'),
        })
    return evidence


def _normalize_results(raw, grid, level, student_messages):
    messages_by_id = {message['id']: message for message in student_messages}
    supplied_sections = {
        item.get('id'): item for item in raw.get('section_scores', [])
        if isinstance(item, dict)
    }
    used_scoring_evidence = set()
    section_scores = []
    raw_score = 0.0
    for section in grid['sections']:
        supplied = supplied_sections.get(section['id'], {})
        supplied_criteria = {
            item.get('id'): item for item in supplied.get('criteria', [])
            if isinstance(item, dict)
        }
        weights = _criterion_weights(section['points'], len(section['ai_indicators']))
        criteria = []
        for index, (expected, maximum) in enumerate(
            zip(section['ai_indicators'], weights), start=1
        ):
            criterion_id = f"{section['id']}__{index}"
            item = supplied_criteria.get(criterion_id, {})
            status = str(item.get('status') or 'not_realized').strip().lower()
            if status not in STATUSES:
                status = 'not_realized'
            evidence = _evidence_from_ids(
                item.get('evidence_message_ids'), messages_by_id,
                used_scoring_evidence,
            )
            if status in ('realized', 'partial') and not evidence:
                status = 'not_realized'
            multiplier = 1 if status == 'realized' else .5 if status == 'partial' else 0
            earned = round(maximum * multiplier, 2)
            if status == 'realized':
                detected = [expected]
                partial, missing = [], []
            elif status == 'partial':
                partial = [expected]
                missing = [expected]
                detected = []
            else:
                detected, partial, missing = [], [], [expected]
            criteria.append({
                'id': criterion_id,
                'criterion': expected,
                'expected_elements': [expected],
                'status': status,
                'status_label': STATUS_LABELS[status],
                'detected_elements': detected,
                'partial_elements': partial,
                'missing_elements': missing,
                'evidence': evidence,
                'points_earned': earned,
                'points_possible': maximum,
                'justification': str(
                    item.get('justification')
                    or (
                        'Critère réalisé et étayé par la preuve étudiante citée.'
                        if status == 'realized'
                        else 'Critère abordé, mais encore incomplet.'
                        if status == 'partial'
                        else 'Aucune preuve étudiante explicite n’a été détectée.'
                    )
                ),
            })
        section_score = round(sum(item['points_earned'] for item in criteria), 1)
        raw_score += section_score
        section_evidence = {}
        for criterion in criteria:
            for evidence in criterion['evidence']:
                section_evidence.setdefault(evidence['message_id'], evidence)
        realized_count = sum(item['status'] == 'realized' for item in criteria)
        partial_count = sum(item['status'] == 'partial' for item in criteria)
        section_scores.append({
            'id': section['id'],
            'title': section['title'],
            'criterion': section['criterion'],
            'expected_elements': list(section['ai_indicators']),
            'detected_elements': [
                value for item in criteria for value in item['detected_elements']
            ],
            'partial_elements': [
                value for item in criteria for value in item['partial_elements']
            ],
            'missing_elements': [
                value for item in criteria for value in item['missing_elements']
            ],
            'evidence': list(section_evidence.values()),
            'criteria': criteria,
            'points_earned': section_score,
            'points_possible': section['points'],
            'justification': str(
                supplied.get('justification')
                or (
                    f'{realized_count} critère(s) réalisé(s), '
                    f'{partial_count} partiellement réalisé(s) et '
                    f'{len(criteria) - realized_count - partial_count} non réalisé(s).'
                )
            ),
        })

    valid_rules = {rule['id']: rule for rule in grid['elimination_rules']}
    errors, seen_errors = [], set()
    for error in raw.get('eliminatory_errors', []):
        if (
            not isinstance(error, dict)
            or error.get('id') not in valid_rules
            or error.get('id') in seen_errors
        ):
            continue
        evidence = _evidence_from_ids(
            error.get('evidence_message_ids'), messages_by_id
        )
        if not evidence:
            continue
        seen_errors.add(error['id'])
        errors.append({
            'id': error['id'],
            'description': valid_rules[error['id']]['description'],
            'justification': str(error.get('justification') or ''),
            'evidence': evidence,
        })

    raw_score = round(raw_score, 1)
    final_score = round(apply_kine_elimination_cap(raw_score, errors), 1)
    threshold = grid['validation_threshold']
    return {
        'schema_version': 2,
        'specialty': 'kine',
        'level': level,
        'grid_name': grid['name'],
        'section_scores': section_scores,
        'checklist': section_scores,
        'raw_points_earned': raw_score,
        'points_earned': final_score,
        'points_total': grid['total_points'],
        'percentage': round(final_score / grid['total_points'] * 100),
        'validation_threshold': threshold,
        'passed': not errors and final_score >= threshold,
        'eliminatory_error_triggered': bool(errors),
        'eliminatory_errors': errors,
        'elimination_cap': grid['elimination_cap'],
        'feedback': str(raw.get('feedback') or 'Évaluation kinésithérapique terminée.'),
    }


def evaluate_kine_conversation(conversation, case_data, llm_client=None):
    level = resolve_student_level(case_data)
    grid = get_kine_evaluation_grid(level)
    student_messages = _student_messages(
        conversation, (case_data or {}).get('timeline')
    )
    if llm_client and student_messages:
        try:
            raw = _llm_evaluation(llm_client, student_messages, case_data, grid)
        except Exception as exc:
            logger.exception('Kine LLM evaluation failed; using offline fallback: %s', exc)
            raw = _pattern_evaluation(student_messages, grid)
    else:
        raw = _pattern_evaluation(student_messages, grid)
    return _normalize_results(raw, grid, level, student_messages)
