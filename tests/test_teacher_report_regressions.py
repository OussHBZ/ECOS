"""Regressions for the teaching team's September 2026 reports."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from test_kine_extension import app, teacher_login, student_login, create_case
from kine_patient_engine import KinePatientEngine
from models import (
    db, Teacher, PatientCase, SimulationSession, PathologyFolder,
    Exam, KineCaseImportBatch, KineCaseDraft,
)


def admin_login(client):
    with client.session_transaction() as session:
        session.clear()
        session.update(user_type='admin', admin_authenticated=True)


@pytest.mark.parametrize('identifier', ['sahar', ' SAHAR ', 'sahar@example.test'])
def test_legacy_teacher_can_login_after_admin_password_reset(app, identifier):
    with app.app_context():
        teacher = db.session.get(Teacher, 1)
        teacher.email, teacher.login = ' Sahar@Example.Test ', 'Sahar'
        teacher.set_password('old-password')
        db.session.commit()
    client = app.test_client()
    admin_login(client)
    assert client.post('/admin/teachers/1/reset-password', json={'password': 'new-password'}).status_code == 200
    failed = client.post('/login', data={
        'login_type': 'teacher', 'workspace': 'kine',
        'teacher_email': identifier, 'password': 'old-password',
    })
    assert '/login' in failed.location
    success = client.post('/login', data={
        'login_type': 'teacher', 'workspace': 'kine',
        'teacher_email': identifier, 'password': 'new-password',
    })
    assert success.location.endswith('/kine/teacher')
    assert client.get('/kine/dashboard').status_code == 200
    with client.session_transaction() as session:
        assert session['user_type'] == 'teacher'
        assert not session.get('admin_authenticated')


def test_teacher_identifier_collisions_are_rejected(app):
    client = app.test_client()
    with app.app_context():
        teacher = db.session.get(Teacher, 1)
        teacher.email = 'Mixed@Example.Test'
        teacher.set_password('secret')
        db.session.commit()
    admin_login(client)
    result = client.post('/admin/add-teacher', json={
        'email': 'mixed@example.test', 'name': 'Duplicate',
        'password': 'secret', 'ecos_type': 'kine',
    })
    assert result.status_code == 400


def test_case_form_duplicate_update_and_invalid_folder_are_recoverable(app):
    client = app.test_client()
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': 'Cas manuels'}).get_json()['id']
    case_id = create_case(client, folder)
    headers = {'Accept': 'application/json'}
    form = {'case_number': 'KINE-001', 'title': 'Cas conservé', 'folder_id': str(folder), 'form_version': '2'}
    duplicate = client.post('/kine/cases', data=form, headers=headers)
    assert duplicate.status_code == 409
    assert 'existe déjà' in duplicate.get_json()['error']
    form['case_number'] = 'KINE-002'
    created = client.post('/kine/cases', data=form, headers=headers)
    assert created.status_code == 201
    assert created.get_json()['redirect_url'].endswith(str(created.get_json()['id']))
    conflict = client.post(f'/kine/cases/{case_id}', data=form, headers=headers)
    assert conflict.status_code in (400, 409)
    with app.app_context():
        assert db.session.get(PatientCase, case_id).case_number == 'KINE-001'
    form.update(case_number='KINE-003', folder_id='999999')
    assert client.post('/kine/cases', data=form, headers=headers).status_code == 400
    page = client.get('/kine/cases/new').get_data(as_text=True)
    assert 'data-case-save-status' in page


def test_cleared_form_fields_do_not_reappear_from_extraction(app):
    client = app.test_client()
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': 'Édition'}).get_json()['id']
    case_id = create_case(client, folder)
    original = {
        'patient_info': {'occupation': 'Ancien métier'},
        'tests': {'cardiac': [{'name': 'FEVG', 'value': 40, 'unit': '%'}]},
        'reference_vitals': {'SpO2': {'value': 96}},
        'prescriptions': {'medical': 'Ancienne prescription'},
        'medications': [{'therapeutic_class': 'Ancien médicament'}],
        'evaluation_checklist': [{'description': 'Ancien critère'}],
    }
    response = client.post(f'/kine/cases/{case_id}', data={
        'form_version': '2', 'case_number': 'KINE-001', 'title': 'Cas corrigé',
        'folder_id': str(folder), 'occupation': '', 'medical_prescription': '',
        'extracted_case_data': json.dumps(original),
    })
    assert response.status_code == 302
    with app.app_context():
        case = db.session.get(PatientCase, case_id)
        assert not case.patient_record.identity.get('occupation')
        assert not case.patient_record.tests.get('cardiac')
        assert not case.patient_record.reference_vitals
        assert not case.patient_record.medical_prescription
        assert not case.patient_record.medications
        assert not case.evaluation_checklist


def test_legacy_functional_tests_survive_download_and_can_be_edited(app):
    client = app.test_client()
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': 'Ancien format'}).get_json()['id']
    case_id = create_case(client, folder)
    downloaded = client.get(f'/kine/cases/{case_id}/download').get_json()
    assert downloaded['tests']['functional'][0]['value'] == 410
    response = client.post(f'/kine/cases/{case_id}', data={
        'form_version': '2', 'case_number': 'KINE-001', 'title': 'Test mis à jour',
        'folder_id': str(folder), 'extracted_case_data': json.dumps(downloaded),
        'tests[0][category]': 'other', 'tests[0][name]': '6MWT',
        'tests[0][value]': '420', 'tests[0][unit]': 'm',
    })
    assert response.status_code == 302
    with app.app_context():
        case = db.session.get(PatientCase, case_id)
        assert 'functional' not in case.patient_record.tests
        engine = KinePatientEngine(case, case.patient_record)
        assert engine.respond('Je vais réaliser le test TM6.', 1)['content'] == '420 m'


@pytest.mark.parametrize('requested,expected', [
    ('Test de Marche de 6 minutes', '410 m'), ('TM6', '410 m'),
    ('FEVG', '40 %'), ('Sit To Stand', '12 répétitions'),
])
def test_measurements_resolve_aliases_and_assessment_descriptions(requested, expected):
    engine = KinePatientEngine({}, {
        'tests': {
            'functional': [{'name': '6MWT', 'value': 410, 'unit': 'm'}],
            'cardiac': [{'name': "Fraction d’éjection ventriculaire gauche", 'value': 40, 'unit': '%'}],
            'physiotherapy_assessment': {'muscular': [
                {'description': 'Sit-to-stand', 'value': 12, 'unit': 'répétitions'},
            ]},
        },
    })
    response = engine.respond(f'Je vais réaliser le test {requested}.', 1)
    assert response['type'] == 'test_result'
    assert response['content'] == expected
    assert len(engine.runtime_state['obtained_vital_parameters']) == 1


def test_missing_measurement_is_not_fabricated_or_matched_inside_a_word():
    engine = KinePatientEngine({}, {'reference_vitals': {'pa': {'value': '120/80'}}})
    assert engine.respond('Je vais mesurer la capacité de marche.', 1)['type'] == 'test_result_unavailable'
    assert engine.respond('Je vais mesurer la PA.', 1)['content'] == '120/80'


def test_labeled_legacy_measurements_are_returned_exactly():
    engine = KinePatientEngine({}, {'tests': {'cardiac': ['FEVG : 40 %']}})
    assert engine.respond('Je vais réaliser le test FEVG.', 1)['content'] == '40 %'


def test_ordinary_patient_sentence_is_not_blocked_by_common_french_words():
    class LLM:
        def invoke(self, messages):
            return SimpleNamespace(content='Je ne peux pas faire de jardinage.')
    engine = KinePatientEngine({}, {
        'identity': {'hobbies': 'Ne peut plus jardiner'},
        'physiotherapy_assessment': {'note': 'Je ne peux pas faire plus de cinq minutes de marche sans dyspnée.'},
    }, LLM())
    assert engine.respond('Quels sont vos loisirs ?', 1)['type'] == 'patient_response'


def test_patient_retries_truncated_answer_and_keeps_followup_context():
    calls = []
    class LLM:
        def invoke(self, messages):
            calls.append(messages)
            if len(calls) == 1:
                return SimpleNamespace(content='Je passe mon temps à', response_metadata={'finish_reason': 'length'})
            return SimpleNamespace(content='Je passe mon temps à lire.', response_metadata={'finish_reason': 'stop'})
    engine = KinePatientEngine({}, {'identity': {'hobbies': 'Lecture'}}, LLM())
    result = engine.respond('À quoi ?', 1, [{'role': 'human', 'content': 'Quels sont vos loisirs ?'}])
    assert result['content'] == 'Je passe mon temps à lire.'
    assert len(calls) == 2
    assert any(message.content == 'Quels sont vos loisirs ?' for message in calls[1])


def test_patient_does_not_return_repeatedly_truncated_output():
    class LLM:
        def invoke(self, messages):
            return SimpleNamespace(content='Je sais que c’est un', response_metadata={})
    with pytest.raises(RuntimeError, match='incomplete'):
        KinePatientEngine({}, {}, LLM()).respond('Comment allez-vous ?', 1)


def test_teacher_deletion_preserves_content_and_reviews_with_foreign_keys(app):
    client = app.test_client()
    teacher_login(client)
    folder_id = client.post('/kine/folders', json={'name': 'À conserver'}).get_json()['id']
    case_id = create_case(client, folder_id)
    with app.app_context():
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        batch = KineCaseImportBatch(created_by=1)
        draft = KineCaseDraft(batch=batch, created_by=1, source_filename='test.pdf', source_path='test.pdf', source_sha256='a' * 64)
        exam = Exam(name='Examen conservé', created_by=1, start_at=datetime.utcnow(),
                    end_at=datetime.utcnow() + timedelta(hours=1), max_duration_minutes=30)
        simulation = SimulationSession(student_id=1, clinical_case_id=case_id, mode='training',
                                       reviewed_by=1, teacher_comments='Commentaire conservé', supplementary_score=15)
        db.session.add_all([draft, exam, simulation])
        db.session.commit()
        ids = batch.id, draft.id, exam.id, simulation.id
    admin_login(client)
    assert client.delete('/admin/teachers/1/delete').status_code == 200
    with app.app_context():
        assert db.session.get(Teacher, 1) is None
        assert db.session.get(PatientCase, case_id).patient_record is not None
        assert db.session.get(PathologyFolder, folder_id).created_by is None
        for model, item_id in zip((KineCaseImportBatch, KineCaseDraft, Exam), ids[:3]):
            assert db.session.get(model, item_id).created_by is None
        saved = db.session.get(SimulationSession, ids[3])
        assert saved.reviewed_by is None
        assert saved.teacher_comments == 'Commentaire conservé'
        assert saved.supplementary_score == 15


def test_direct_case_delete_cannot_destroy_simulation_history(app):
    client = app.test_client()
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': 'Historique'}).get_json()['id']
    case_id = create_case(client, folder)
    student_login(client)
    started = client.post('/kine/simulation/start', json={'case_id': case_id, 'mode': 'training'})
    assert started.status_code == 201
    teacher_login(client)
    assert client.delete(f'/kine/cases/{case_id}').status_code == 409
    with app.app_context():
        assert db.session.get(PatientCase, case_id) is not None
        assert SimulationSession.query.count() == 1
