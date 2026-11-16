"""Independent effort-test measurements. Values/rules come only from authors."""
from copy import deepcopy
import re

ACTORS = {'student', 'patient', 'system', 'teacher'}
MOMENTS = {'initial', 'during', 'stage', 'end', 'recovery'}
STATES = {'value', 'ras', 'absent', 'not_evaluated', 'unknown'}
EXPECTED_TYPES = {'undefined', 'exact', 'range', 'minimum', 'maximum', 'evolution', 'qualitative', 'unchanged'}
ID = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def normalize_effort_tests(tests):
    if not isinstance(tests, list) or len(tests) > 50:
        raise ValueError('Les tests à l’effort doivent être une liste (50 maximum).')
    result, test_ids = [], set()
    for test in tests:
        if not isinstance(test, dict):
            raise ValueError('Test à l’effort invalide.')
        test = deepcopy(test)
        test_id = str(test.get('id') or '')
        if not ID.fullmatch(test_id) or test_id in test_ids or not test.get('name'):
            raise ValueError('Chaque test exige un identifiant unique et un nom.')
        test_ids.add(test_id)
        rows = test.get('measurements', [])
        if not isinstance(rows, list) or len(rows) > 200:
            raise ValueError('Mesures du test invalides (200 maximum).')
        measurement_ids = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Mesure à l’effort invalide.')
            measurement_id = str(row.get('id') or '')
            if not ID.fullmatch(measurement_id) or measurement_id in measurement_ids or not row.get('name'):
                raise ValueError('Chaque mesure exige un identifiant unique dans son test et un paramètre.')
            measurement_ids.add(measurement_id)
            if row.get('moment') not in MOMENTS or row.get('actor') not in ACTORS:
                raise ValueError('Moment ou responsable de mesure invalide.')
            if row['moment'] == 'stage' and not row.get('moment_detail'):
                raise ValueError('Précisez l’étape ou la durée de mesure.')
            row.setdefault('status', 'value')
            if row['status'] not in STATES:
                raise ValueError('État de mesure invalide.')
            if row['status'] != 'value':
                row.pop('value', None)
            # Expected values and thresholds are author-only evaluation data.
            if row.get('expected_type', 'undefined') not in EXPECTED_TYPES:
                raise ValueError('Type de valeur attendue invalide.')
            if row.get('patient_knows') is not None and not isinstance(row.get('patient_knows'), bool):
                raise ValueError('Connaissance du patient invalide.')
            if row.get('actor') == 'system' and not row.get('trigger'):
                raise ValueError('Une mesure système exige un déclencheur défini par l’enseignant.')
        result.append(test)
    return result


def effort_information(tests):
    """Atomic measurements use stable IDs; expected answers have a reserved path."""
    values = []
    for test in normalize_effort_tests(tests):
        for row in test.get('measurements', []):
            path = f"effort_tests.{test['id']}.{row['id']}"
            clinical = {key: deepcopy(row[key]) for key in (
                'id', 'name', 'moment', 'moment_detail', 'actor', 'value', 'unit',
                'status', 'data_type', 'patient_knows', 'trigger', 'source',
            ) if key in row}
            clinical.update(test_id=test['id'], test_name=test['name'])
            values.append((path, clinical))
            expected = {key: deepcopy(row[key]) for key in (
                'expected_type', 'expected_value', 'thresholds', 'expected_action',
            ) if key in row}
            if expected:
                values.append((f'evaluation_expectations.{path}', expected))
    return values
