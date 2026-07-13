"""Shared, specialty-gated physiotherapy evaluation logic."""

import json
import logging
import re

from langchain_core.messages import HumanMessage

from evaluation_config import apply_kine_elimination_cap, get_kine_evaluation_grid

logger = logging.getLogger(__name__)


def is_kine_case(case_data):
    """Return True only for the dedicated physiotherapy specialty."""
    return str((case_data or {}).get('specialty') or '').strip().lower() == 'kine'


def resolve_student_level(case_data):
    """Resolve level from supported request shapes, defaulting safely to Licence."""
    case_data = case_data or {}
    student = case_data.get('student')
    if isinstance(student, dict):
        level = student.get('level')
    else:
        level = getattr(student, 'level', None)
    level = level or case_data.get('student_level') or case_data.get('level') or 'licence'
    normalized = str(level).strip().lower()
    return normalized if normalized in ('licence', 'master') else 'licence'


def _transcript(conversation):
    lines = []
    for message in conversation or []:
        if message.get('role') == 'system':
            continue
        role = 'Étudiant' if message.get('role') == 'human' else 'Patient'
        lines.append(f"{role}: {message.get('content', '')}")
    return '\n'.join(lines)


def _extract_json(text):
    match = re.search(r'```(?:json)?\s*({.*})\s*```', text or '', re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r'({.*})', text or '', re.DOTALL)
    return json.loads(match.group(1)) if match else None


def _llm_evaluation(llm_client, transcript, case_data, grid):
    sections = [
        {
            'id': section['id'],
            'criterion': section['criterion'],
            'max_points': section['points'],
            'indicators': section['ai_indicators'],
        }
        for section in grid['sections']
    ]
    rules = grid['elimination_rules']
    context = {
        key: value for key, value in (case_data or {}).items()
        if key not in {'student', 'evaluation_checklist'}
    }
    prompt = f"""Vous êtes un évaluateur strict d'ECOS en kinésithérapie.
Évaluez uniquement les éléments explicites de la transcription, sans déduire les
actions non formulées. Notez chaque section entre 0 et son maximum, avec décimales
autorisées. Ne signalez une erreur éliminatoire que si la transcription l'établit.
L'absence de constantes initiales est établie si l'effort ou la séance commence
avant le contrôle complet de la PA, de la FC et de la SpO₂. Justifiez chaque note
et chaque erreur détectée. Toutes les justifications doivent être rédigées en français.

SECTIONS DE LA GRILLE :
{json.dumps(sections, ensure_ascii=False)}

ERREURS ÉLIMINATOIRES :
{json.dumps(rules, ensure_ascii=False)}

CONTEXTE DU CAS :
{json.dumps(context, ensure_ascii=False, default=str)}

TRANSCRIPTION :
{transcript}

Retournez uniquement ce JSON :
{{
  "section_scores": [
    {{"id": "section id", "score": 0, "justification": "explicit evidence"}}
  ],
  "eliminatory_errors": [
    {{"id": "rule id", "justification": "why", "evidence": "transcript evidence"}}
  ],
  "feedback": "concise overall feedback"
}}
"""
    response = llm_client.invoke(
        [HumanMessage(content=prompt)],
        {'max_tokens': 1800, 'temperature': 0.1},
    )
    parsed = _extract_json(response.content)
    if not isinstance(parsed, dict):
        raise ValueError('Kine evaluator returned no valid JSON object')
    return parsed


def _contains_any(text, terms):
    return any(term in text for term in terms)


def _pattern_evaluation(transcript, grid):
    """Conservative offline fallback; the LLM remains the primary evaluator."""
    text = transcript.lower()
    student_text = ' '.join(
        line.split(':', 1)[1] for line in text.splitlines()
        if line.startswith('étudiant:')
    )
    section_terms = {
        'medical_record_analysis': ['dossier', 'diagnostic', 'traitement', 'contre-indication'],
        'history_taking': ['douleur', 'dyspn', 'fatigue', 'activité', 'objectif'],
        'physiotherapy_assessment': ['tension', 'pouls', 'spo2', 'borg', 'marche'],
        'clinical_reasoning': ['diagnostic kiné', 'priorité', 'objectif smart', 'raisonnement'],
        'session_prescription': ['échauffement', 'fitt', 'exercice', 'récupération'],
        'therapeutic_communication': ['bonjour', 'comprends', 'reformul', 'rassur'],
        'therapeutic_education': ['conseil', 'signe', 'auto-surveillance', 'domicile'],
        'expert_medical_record_analysis': ['interaction', 'pronostic', 'comorbid', 'physiopath'],
        'expert_history_taking': ['red flag', 'drapeau rouge', 'psychosocial', 'comprenez'],
        'expert_physiotherapy_assessment': ['orthostatisme', 'test', 'spo2', 'équilibre'],
        'advanced_clinical_reasoning': ['hiérarch', 'interaction', 'adaptation', 'projection'],
        'advanced_prescription_fitt': ['fitt', 'progression', 'intensité', 'arrêt'],
        'dynamic_session_management': ['surveille', 'fréquence cardiaque', 'spo2', 'borg'],
        'incident_management': ['arrête', 'sécur', 'urgence', 'médecin'],
        'advanced_therapeutic_education': ['teach-back', 'prévention', 'autogestion', 'phase iii'],
    }
    section_scores = []
    for section in grid['sections']:
        terms = section_terms.get(section['id'], [])
        matched = sum(1 for term in terms if term in student_text)
        ratio = matched / len(terms) if terms else 0
        score = round(section['points'] * ratio, 1)
        section_scores.append({
            'id': section['id'],
            'score': score,
            'justification': (
                f'{matched}/{len(terms)} groupes de preuves attendus détectés par l’évaluation locale.'
            ),
        })

    errors = []
    exertion_terms = ['exercice', 'effort', 'marche', 'vélo', 'tapis', 'échauffement']
    vitals = {
        'bp': ['tension', 'pression artérielle', 'pa '],
        'hr': ['fréquence cardiaque', 'pouls', ' fc '],
        'spo2': ['spo2', 'saturation'],
    }
    exertion_started = _contains_any(student_text, exertion_terms)
    if exertion_started and not all(_contains_any(student_text, terms) for terms in vitals.values()):
        errors.append({
            'id': 'missing_initial_vitals',
            'justification': "L’effort a débuté sans contrôle explicite de la PA, de la FC et de la SpO₂.",
            'evidence': 'Détection locale dans la transcription',
        })
    monitoring_terms = ['surveille', 'monitor', 'tension', 'pouls', 'fréquence cardiaque', 'spo2', 'borg']
    if exertion_started and not _contains_any(student_text, monitoring_terms):
        errors.append({
            'id': 'missing_exertion_monitoring',
            'justification': 'Un exercice a été proposé sans surveillance clinique explicite.',
            'evidence': 'Détection locale dans la transcription',
        })
    dangerous_terms = ['100%', 'intensité maximale', 'jusqu’à épuisement', "jusqu'a epuisement"]
    if _contains_any(student_text, dangerous_terms):
        errors.append({
            'id': 'dangerous_exercise_or_intensity',
            'justification': 'Une intensité explicitement dangereuse ou maximale a été prescrite.',
            'evidence': 'Détection locale dans la transcription',
        })
    return {
        'section_scores': section_scores,
        'eliminatory_errors': errors,
        'feedback': "Évaluation kinésithérapique locale terminée ; une confirmation par le modèle d’IA est recommandée.",
    }


def _normalize_results(raw, grid, level):
    valid_rules = {rule['id']: rule for rule in grid['elimination_rules']}
    supplied_sections = {
        item.get('id'): item for item in raw.get('section_scores', [])
        if isinstance(item, dict)
    }
    section_scores = []
    raw_score = 0.0
    for section in grid['sections']:
        supplied = supplied_sections.get(section['id'], {})
        try:
            score = float(supplied.get('score', 0))
        except (TypeError, ValueError):
            score = 0.0
        score = round(max(0.0, min(float(section['points']), score)), 1)
        raw_score += score
        section_scores.append({
            'id': section['id'],
            'title': section['title'],
            'criterion': section['criterion'],
            'points_earned': score,
            'points_possible': section['points'],
            'justification': str(supplied.get('justification') or 'Aucune preuve explicite identifiée.'),
        })

    errors = []
    seen = set()
    for error in raw.get('eliminatory_errors', []):
        if not isinstance(error, dict) or error.get('id') not in valid_rules or error.get('id') in seen:
            continue
        seen.add(error['id'])
        errors.append({
            'id': error['id'],
            'description': valid_rules[error['id']]['description'],
            'justification': str(error.get('justification') or ''),
            'evidence': str(error.get('evidence') or ''),
        })

    raw_score = round(raw_score, 1)
    final_score = round(apply_kine_elimination_cap(raw_score, errors), 1)
    threshold = grid['validation_threshold']
    return {
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
    transcript = _transcript(conversation)
    if llm_client and transcript.strip():
        try:
            raw = _llm_evaluation(llm_client, transcript, case_data, grid)
        except Exception as exc:
            logger.exception('Kine LLM evaluation failed; using offline fallback: %s', exc)
            raw = _pattern_evaluation(transcript, grid)
    else:
        raw = _pattern_evaluation(transcript, grid)
    return _normalize_results(raw, grid, level)
