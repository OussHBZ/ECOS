"""Authored behavioral settings, separate from clinical facts and scoring."""
from copy import deepcopy
import re
import unicodedata

PERSONALITY_OPTIONS = {
    'anxiety': ('calm', 'worried', 'very_anxious'),
    'cooperation': ('cooperative', 'hesitant', 'reluctant'),
    'motivation': ('motivated', 'ambivalent', 'low'),
    'trust': ('high', 'moderate', 'low'),
    'understanding': ('easy', 'average', 'limited'),
    'pain_reaction': ('calm', 'worried', 'amplified'),
    'effort_reaction': ('reassured', 'cautious', 'anxious', 'reluctant'),
    'communication_style': ('direct', 'reserved', 'talkative', 'hesitant', 'inexpressive'),
    'vocabulary': ('everyday', 'simple', 'limited'),
}
TEXT_FIELDS = ('main_fear', 'communication_difficulties', 'notes')


def normalize_personality(value):
    if not isinstance(value, dict):
        raise ValueError('Le profil du patient doit être un objet.')
    if set(value) - (set(PERSONALITY_OPTIONS) | set(TEXT_FIELDS) | {'enabled', 'transitions'}):
        raise ValueError('Paramètre de personnalité inconnu.')
    if not isinstance(value.get('enabled', False), bool):
        raise ValueError('Activation de personnalité invalide.')
    result = {'enabled': value.get('enabled', False)}
    for key, options in PERSONALITY_OPTIONS.items():
        setting = value.get(key)
        if setting not in (None, ''):
            if setting not in options:
                raise ValueError(f'Paramètre de personnalité invalide : {key}.')
            result[key] = setting
    for key in TEXT_FIELDS:
        if value.get(key):
            if not isinstance(value[key], str) or len(value[key]) > 1200:
                raise ValueError(f'Texte de personnalité invalide : {key}.')
            result[key] = value[key]
    transitions = value.get('transitions') or []
    if not isinstance(transitions, list) or len(transitions) > 20:
        raise ValueError('Évolutions comportementales invalides.')
    result['transitions'] = []
    for transition in transitions:
        if not isinstance(transition, dict):
            raise ValueError('Évolution comportementale invalide.')
        terms = transition.get('terms') or []
        if isinstance(terms, str):
            terms = [term.strip() for term in terms.split('|') if term.strip()]
        try:
            count = int(transition.get('after_occurrences') or 2)
        except (TypeError, ValueError):
            raise ValueError('Nombre d’interactions invalide.') from None
        if not terms or not isinstance(terms, list) or count < 2 or count > 100:
            raise ValueError('Une évolution progressive exige des formulations et au moins deux interactions.')
        if not all(isinstance(term, str) and term.strip() and len(term) <= 150 for term in terms):
            raise ValueError('Formulations d’évolution invalides.')
        changes = {key: transition[key] for key in PERSONALITY_OPTIONS if transition.get(key)}
        normalized = normalize_personality(changes)
        result['transitions'].append({
            'terms': terms,
            'after_occurrences': count,
            **{key: normalized[key] for key in changes},
        })
    return result


def personality_for(case, level, conversation=(), message=''):
    structured = case.get('structured_content', {}) if isinstance(case, dict) else getattr(case, 'structured_content', {})
    profile = deepcopy((structured or {}).get('patient_personality') or {})
    if level != 'master' or not profile.get('enabled'):
        return {}
    profile = normalize_personality(profile)
    def normalized(text):
        text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
        return re.sub(r'\W+', ' ', text).strip()
    turns = [item['content'] for item in conversation if item.get('role') == 'human'] + [message]
    for rule in profile.pop('transitions', []):
        count = sum(any(normalized(term) in normalized(turn) for term in rule['terms']) for turn in turns)
        if count >= rule['after_occurrences']:
            profile.update({key: rule[key] for key in PERSONALITY_OPTIONS if key in rule})
    return profile


def style_patient_fact(content, case, level, conversation=(), message=''):
    """Tone can change around a fact; its stored wording/value cannot change."""
    profile = personality_for(case, level, conversation, message)
    if profile.get('anxiety') == 'very_anxious':
        return 'Cela m’inquiète beaucoup. ' + content
    if profile.get('anxiety') == 'worried':
        return 'Cela m’inquiète encore. ' + content
    if profile.get('cooperation') == 'hesitant':
        return 'Je vais essayer de vous répondre. ' + content
    return content
