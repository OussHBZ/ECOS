"""T04 per-information disclosure policy; all people and values are fictitious."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_kine_extension import (
    app, create_case, student_login, teacher_login,
)
from information_access import record_projection
from models import (
    db, CaseInformation, PatientCase, SimulationDisclosure, SimulationSession,
    Student, TeacherStudentScope,
)


def _create_policy(client, case_id, **values):
    response = client.post(f'/kine/cases/{case_id}/information', json=values)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def _patch_policy(client, case_id, item, **values):
    response = client.patch(
        f"/kine/cases/{case_id}/information/{item['stable_id']}", json=values,
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_server_policy_covers_initial_question_deepening_exam_reserved_and_levels(app):
    from types import SimpleNamespace
    app.config['GROQ_CLIENT'] = SimpleNamespace(invoke=lambda *a, **k: SimpleNamespace(content='Je vous écoute.'))
    client = app.test_client()
    teacher_login(client)
    folder_id = client.post('/kine/folders', json={'name': 'T04 fictitious folder'}).get_json()['id']
    case_id = create_case(client, folder_id, activate=False)
    with app.app_context():
        case = db.session.get(PatientCase, case_id)
        case.diagnosis = 'PHYSIO-EXPECTED-SECRET'
        case.patient_record.medical_context = {'main_diagnosis': 'MEDICAL-DIAGNOSIS-VISIBLE'}
        master = Student(
            student_code='T04002', name='Master fictif', level='master',
            group_name='Groupe A', ecos_type='kine',
        )
        db.session.add(master)
        db.session.flush()
        db.session.add(TeacherStudentScope(teacher_id=1, student_id=master.id))
        db.session.commit()
        master_id = master.id

    question = _create_policy(
        client, case_id, path='custom.question_fact', label='Douleur secrète',
        value='QUESTION-VALUE', value_type='string', access_mode='question',
        patient_knows=True, importance='essential',
        disclosure_conditions={'terms': ['douleur ciblée']}, level_rules={},
    )
    deepening = _create_policy(
        client, case_id, path='custom.deep_fact', label='Précision douleur',
        value='DEEPENING-VALUE', access_mode='deepening', patient_knows=True,
        importance='important', disclosure_conditions={
            'terms': ['précisez cette douleur'],
            'requires_information': [question['stable_id']],
        }, level_rules={},
    )
    unknown = _create_policy(
        client, case_id, path='custom.unknown_fact', label='Sommeil inconnu',
        value='UNKNOWN-PATIENT-VALUE', access_mode='question', patient_knows=False,
        importance='complementary', disclosure_conditions={'terms': ['votre sommeil']},
        level_rules={},
    )
    reserved = _create_policy(
        client, case_id, path='custom.reserved_fact', label='Attente pédagogique',
        value='RESERVED-EVALUATION-VALUE', access_mode='evaluation_reserved',
        patient_knows=True, importance='essential', disclosure_conditions={}, level_rules={},
    )

    policies = client.get(f'/kine/cases/{case_id}/information').get_json()['information']
    expected = next(item for item in policies if item['path'] == 'expected_physiotherapy_diagnosis')
    assert expected['value'] == 'PHYSIO-EXPECTED-SECRET'
    assert expected['access_mode'] == 'evaluation_reserved'
    test_item = next(item for item in policies if item['path'].startswith('tests.functional.'))
    test_item = _patch_policy(
        client, case_id, test_item, access_mode='examination', patient_knows=False,
        disclosure_conditions={'terms': ['6MWT', 'test de marche']},
    )
    document = next(item for item in policies if item['path'] == 'available_documents.0')
    document = _patch_policy(
        client, case_id, document, access_mode='evaluation_reserved',
        patient_knows=False, disclosure_conditions={},
    )

    published = client.post(f'/kine/cases/{case_id}/versions/publish', json={})
    assert published.status_code == 201
    version_id = published.get_json()['id']
    assert client.put(f'/kine/cases/{case_id}/availability', json={
        'version_id': version_id, 'student_ids': [1, master_id],
    }).status_code == 200

    student_login(client)
    initial = client.get(
        f'/kine/cases/{case_id}/patient-record', headers={'Accept': 'application/json'},
    )
    assert initial.status_code == 200
    initial_text = initial.get_data(as_text=True)
    assert 'MEDICAL-DIAGNOSIS-VISIBLE' in initial_text
    for secret in (
        'PHYSIO-EXPECTED-SECRET', 'QUESTION-VALUE', 'DEEPENING-VALUE',
        'RESERVED-EVALUATION-VALUE', 'UNKNOWN-PATIENT-VALUE', '6MWT', 'ECG',
    ):
        assert secret not in initial_text
    medication = initial.get_json()['medications'][0]
    assert medication == {'therapeutic_class': 'Beta blocker', 'inn': 'bisoprolol'}

    student_login(client, master_id)
    master_initial = client.get(
        f'/kine/cases/{case_id}/patient-record', headers={'Accept': 'application/json'},
    ).get_json()
    assert master_initial['medications'][0] == {'therapeutic_class': 'Beta blocker'}

    student_login(client)
    started = client.post('/kine/simulation/start', json={'case_id': case_id})
    assert started.status_code == 201
    session_id = started.get_json()['simulation_id']
    direct_reserved = client.get(
        f"/kine/simulation/{session_id}/information/{reserved['stable_id']}"
    )
    assert direct_reserved.status_code == 404
    assert 'RESERVED-EVALUATION-VALUE' not in direct_reserved.get_data(as_text=True)
    assert client.get(
        f"/kine/simulation/{session_id}/information/{question['stable_id']}"
    ).status_code == 404

    assert client.post(
        f'/kine/simulation/{session_id}/message',
        json={'message': 'Pouvez-vous préciser cette douleur ?'},
    ).get_json()['response']['content'] != 'DEEPENING-VALUE'
    question_response = client.post(
        f'/kine/simulation/{session_id}/message',
        json={'message': 'Avez-vous une douleur ciblée ?'},
    )
    assert question_response.get_json()['response']['content'] == 'QUESTION-VALUE'
    assert question['stable_id'] in question_response.get_json()['revealed_information_ids']
    assert client.get(
        f"/kine/simulation/{session_id}/information/{question['stable_id']}"
    ).get_json()['value'] == 'QUESTION-VALUE'

    deep_response = client.post(
        f'/kine/simulation/{session_id}/message',
        json={'message': 'Précisez cette douleur.'},
    )
    assert deep_response.get_json()['response']['content'] == 'DEEPENING-VALUE'
    unknown_response = client.post(
        f'/kine/simulation/{session_id}/message',
        json={'message': 'Que savez-vous de votre sommeil ?'},
    )
    assert unknown_response.get_json()['response']['content'] == 'Je ne connais pas cette information.'
    assert unknown['stable_id'] not in unknown_response.get_json()['revealed_information_ids']

    test_response = client.post(
        f'/kine/simulation/{session_id}/test-request', json={'test': '6MWT'},
    )
    assert test_response.status_code == 200
    assert test_response.get_json()['response']['type'] == 'test_result'
    assert test_item['stable_id'] in test_response.get_json()['revealed_information_ids']

    record_json = client.get(
        f'/kine/simulation/{session_id}/patient-record',
        headers={'Accept': 'application/json'},
    ).get_json()['record']
    serialized = json.dumps(record_json, ensure_ascii=False)
    assert 'QUESTION-VALUE' in serialized and 'DEEPENING-VALUE' in serialized and '6MWT' in serialized
    assert 'RESERVED-EVALUATION-VALUE' not in serialized
    assert 'PHYSIO-EXPECTED-SECRET' not in serialized
    page = client.get(f'/kine/simulation/{session_id}/patient-record').get_data(as_text=True)
    assert 'QUESTION-VALUE' in page and '6MWT' in page
    assert 'RESERVED-EVALUATION-VALUE' not in page and 'PHYSIO-EXPECTED-SECRET' not in page
    chat = client.get(f'/kine/simulation/{session_id}/chat').get_data(as_text=True)
    assert 'RESERVED-EVALUATION-VALUE' not in chat and 'PHYSIO-EXPECTED-SECRET' not in chat

    history = client.get('/kine/history', headers={'Accept': 'application/json'}).get_json()
    history_text = json.dumps(history, ensure_ascii=False)
    assert reserved['stable_id'] not in history['sessions'][0]['revealed_information_ids']
    assert 'RESERVED-EVALUATION-VALUE' not in history_text
    with app.app_context():
        simulation = db.session.get(SimulationSession, session_id)
        assert {item.channel for item in simulation.information_disclosures} >= {
            'initial_record', 'question', 'deepening', 'examination',
        }
        patient_context = record_projection(
            simulation.case_version, 'licence', simulation, patient_context=True,
        )
        patient_text = json.dumps(patient_context, ensure_ascii=False)
        assert 'UNKNOWN-PATIENT-VALUE' not in patient_text
        assert 'RESERVED-EVALUATION-VALUE' not in patient_text
        assert 'PHYSIO-EXPECTED-SECRET' not in patient_text
        assert SimulationDisclosure.query.filter_by(
            simulation_id=session_id, stable_id=unknown['stable_id'],
        ).first() is None
        logged = SimulationDisclosure.query.filter_by(simulation_id=session_id).first()
        for statement in (
            'UPDATE simulation_disclosures SET channel=\'forged\' WHERE simulation_id=:sid AND stable_id=:iid',
            'DELETE FROM simulation_disclosures WHERE simulation_id=:sid AND stable_id=:iid',
        ):
            with pytest.raises(IntegrityError, match='immutable'):
                db.session.execute(text(statement), {'sid': session_id, 'iid': logged.stable_id})
                db.session.commit()
            db.session.rollback()


def test_information_policy_api_rejects_student_and_keeps_published_copy_immutable(app):
    client = app.test_client()
    teacher_login(client)
    folder_id = client.post('/kine/folders', json={'name': 'T04 immutable folder'}).get_json()['id']
    case_id = create_case(client, folder_id, activate=False)
    item = _create_policy(
        client, case_id, path='custom.immutable', label='Information figée',
        value='VERSION-ONE', access_mode='initial', patient_knows=True,
        importance='important', disclosure_conditions={}, level_rules={},
    )
    published = client.post(f'/kine/cases/{case_id}/versions/publish', json={}).get_json()
    _patch_policy(client, case_id, item, value='WORKING-COPY-TWO')
    with app.app_context():
        version_item = next(
            value for value in db.session.get(PatientCase, case_id).kine_versions[0].information_items
            if value.stable_id == item['stable_id']
        )
        assert json.loads(version_item.value_json) == 'VERSION-ONE'
        assert published['id'] == version_item.version_id
        for statement in (
            'UPDATE kine_version_information SET value_json=\'"FORGED"\' WHERE version_id=:vid AND stable_id=:iid',
            'DELETE FROM kine_version_information WHERE version_id=:vid AND stable_id=:iid',
        ):
            with pytest.raises(IntegrityError, match='immutable'):
                db.session.execute(text(statement), {
                    'vid': version_item.version_id, 'iid': version_item.stable_id,
                })
                db.session.commit()
            db.session.rollback()
    student_login(client)
    denied = client.get(f'/kine/cases/{case_id}/information')
    assert denied.status_code == 401
    assert 'VERSION-ONE' not in denied.get_data(as_text=True)
    assert 'WORKING-COPY-TWO' not in denied.get_data(as_text=True)
