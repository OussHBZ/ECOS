"""D03: authored hints in a separate channel, bounded by information policy."""
from copy import deepcopy
import json
from information_access import effective_mode, disclosed_ids, redact_reserved
from case_versions import simulation_case, simulation_student


def normalize_aids(rows, case):
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError('Liste d’aides requise.')
    if not rows:
        return []  # T03 snapshots precede the additive information-policy tables.
    items = {i.stable_id: i for i in case.information_items}
    ids, result = set(), []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or row['id'] in ids:
            raise ValueError('Identifiant d’aide unique requis.')
        ids.add(row['id'])
        item = items.get(row.get('information_id'))
        if not item or item.access_mode == 'evaluation_reserved':
            raise ValueError('L’aide doit viser une information clinique accessible, jamais une attente réservée.')
        if not isinstance(row.get('text'), str) or not row['text'].strip() or len(row['text']) > 1500:
            raise ValueError('Indice pédagogique requis (1500 caractères maximum).')
        required = row.get('requires_information', [])
        if not isinstance(required, list) or any(not isinstance(i, str) or i not in items for i in required):
            raise ValueError('Prérequis d’aide invalides.')
        for key in ('active', 'teacher_approved', 'no_direct_answer'):
            if not isinstance(row.get(key, False), bool):
                raise ValueError('Validation explicite de l’aide requise.')
        if row.get('teacher_approved') and not row.get('no_direct_answer'):
            raise ValueError('Confirmez que l’indice ne donne pas directement la réponse.')
        result.append({key: deepcopy(row.get(key, [] if key == 'requires_information' else False)) for key in
                       ('id', 'text', 'information_id', 'requires_information', 'active', 'teacher_approved', 'no_direct_answer')})
    return result


def available_aids(simulation):
    case = simulation_case(simulation)
    items = {i.stable_id: i for i in simulation.case_version.information_items}
    revealed = disclosed_ids(simulation)
    result = []
    for row in case.structured_content.get('teaching_aids', []):
        item = items.get(row['information_id'])
        if not item or not all(row.get(k) is True for k in ('active', 'teacher_approved', 'no_direct_answer')):
            continue
        mode = effective_mode(item, simulation_student(simulation).level)
        if mode == 'evaluation_reserved' or not set(row['requires_information']) <= revealed:
            continue
        conditions = json.loads(item.disclosure_conditions_json or '{}')
        if mode == 'deepening' and not set(conditions.get('requires_information', [])) <= revealed:
            continue
        if redact_reserved(row['text'], simulation.case_version) != row['text']:
            continue
        result.append({'id': row['id'], 'text': row['text']})
    return result
