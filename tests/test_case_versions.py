"""T03: publication storage tested independently of release/exam policy."""
import json
from datetime import datetime
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_kine_extension import app, teacher_login, create_case
from models import (db, ExamCaseVersion, KineCaseAvailability, PatientCase,
                    Student, SimulationSession, KineCaseVersion)
from case_versions import (save_draft, publish, version_view, freeze_simulation,
                           simulation_case, simulation_student, version_metadata)


def case_fixture(app):
    client = app.test_client()
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': 'Fictitious version folder'}).get_json()['id']
    return create_case(client, folder, activate=False)


def test_publication_snapshot_includes_all_existing_content_and_draft_is_separate(app):
    cid = case_fixture(app)
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        first = publish(case, 'teacher:1')
        db.session.commit()
        original = first.content_json
        frozen = version_view(first)
        assert frozen.patient_record.identity['name'] == 'A.B.'
        assert frozen.patient_record.medications[0].inn == 'bisoprolol'
        assert frozen.patient_record.interventions[0].timing == '2026-01-01'
        assert frozen.pathology_folder.name == 'Fictitious version folder'
        assert frozen.incidents[0].scripted_reaction == 'Chest pain'
        case.diagnosis = 'FICTITIOUS-V2'
        case.patient_record.identity = {'name': 'FICTITIOUS-V2'}
        case.incidents[0].scripted_reaction = 'FICTITIOUS-V2'
        draft = save_draft(case)
        db.session.commit()
        assert draft.id != first.id and draft.number == 2 and draft.status == 'draft'
        assert first.content_json == original
        with pytest.raises(ValueError, match='publiée'):
            version_view(draft)
        second = publish(case, 'teacher:1', draft.content_sha256)
        db.session.commit()
        assert first.content_json == original
        assert version_view(second).diagnosis == 'FICTITIOUS-V2'
        assert version_view(first).diagnosis == 'Heart failure'


def test_published_rows_resist_orm_and_raw_sql_changes_and_delete(app):
    cid = case_fixture(app)
    with app.app_context():
        version = publish(db.session.get(PatientCase, cid), 'teacher:1')
        db.session.commit()
        vid = version.id
        version.content_json = '{}'
        with pytest.raises(ValueError, match='immuable'):
            db.session.commit()
        db.session.rollback()
        for statement in ['UPDATE kine_case_versions SET content_json=:value WHERE id=:id',
                          'DELETE FROM kine_case_versions WHERE id=:id']:
            with pytest.raises(IntegrityError, match='immutable'):
                db.session.execute(text(statement), {'value': '{}', 'id': vid})
                db.session.commit()
            db.session.rollback()
        assert version_view(db.session.get(KineCaseVersion, vid)).diagnosis == 'Heart failure'


def test_simulation_reference_and_level_are_immutable_and_independent_of_profile(app):
    cid = case_fixture(app)
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        version = publish(case, 'teacher:1')
        student = db.session.get(Student, 1)
        simulation = SimulationSession(student_id=student.id, clinical_case_id=cid)
        freeze_simulation(simulation, version, student)
        db.session.add(simulation)
        db.session.commit()
        sid = simulation.id
        original = simulation.evaluation_reference_json
        assert json.loads(original)['validation_threshold'] == '12'
        assert json.loads(original)['engine'] == 'kardiox_criteria_v1'
        student.level = 'master'
        case.diagnosis = 'FICTITIOUS-CHANGED'
        db.session.commit()
        assert simulation_student(simulation).level == 'licence'
        assert simulation_case(simulation).diagnosis == 'Heart failure'
        assert version_metadata(simulation)['reference_origin'] == 'captured_at_start'
        for column, value in [('frozen_student_level', 'master'), ('evaluation_reference_json', '{}'), ('case_version_id', None)]:
            with pytest.raises(IntegrityError, match='immutable'):
                db.session.execute(text(f'UPDATE simulation_sessions SET {column}=:v WHERE id=:id'), {'v': value, 'id': sid})
                db.session.commit()
            db.session.rollback()
        assert db.session.get(SimulationSession, sid).evaluation_reference_json == original


def test_publishing_stale_draft_hash_is_refused(app):
    cid = case_fixture(app)
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        old_hash = save_draft(case).content_sha256
        db.session.commit()
        case.diagnosis = 'FICTITIOUS-CONCURRENT-EDIT'
        db.session.commit()
        with pytest.raises(ValueError, match='changé'):
            publish(case, 'teacher:1', old_hash)
        db.session.rollback()
        assert KineCaseVersion.query.filter_by(status='published').count() == 0


@pytest.mark.parametrize('role', ['anonymous', 'student', 'technical', 'teacher', 'pedagogical'])
@pytest.mark.parametrize('surface', ['list', 'content', 'download', 'publish'])
def test_private_publication_route_permission_matrix(app, role, surface):
    from test_kine_extension import student_login
    from test_teacher_report_regressions import admin_login
    from test_kine_permissions import pedagogical_login
    cid = case_fixture(app)
    owner = app.test_client()
    teacher_login(owner)
    published = owner.post(f'/kine/cases/{cid}/versions/publish', json={})
    assert published.status_code == 201
    vid = published.get_json()['id']
    client = app.test_client()
    if role == 'student': student_login(client)
    elif role == 'technical': admin_login(client)
    elif role == 'teacher': teacher_login(client)
    elif role == 'pedagogical': pedagogical_login(client, app)
    base = f'/kine/cases/{cid}/versions'
    if surface == 'publish': response = client.post(base + '/publish', json={})
    else: response = client.get(base + ('' if surface == 'list' else '/' + str(vid) + ('/download' if surface == 'download' else '')))
    expected = (201 if surface == 'publish' else 200) if role in ('teacher', 'pedagogical') else (403 if role == 'technical' else 401)
    assert response.status_code == expected
    if role not in ('teacher', 'pedagogical'):
        assert b'Heart failure' not in response.data


def test_case_and_incident_edits_save_draft_without_changing_publication(app):
    cid = case_fixture(app)
    client = app.test_client()
    teacher_login(client)
    version = client.post(f'/kine/cases/{cid}/versions/publish', json={}).get_json()['id']
    with app.app_context():
        original = db.session.get(KineCaseVersion, version).content_json
    assert client.post(f'/kine/cases/{cid}/incidents', json={'trigger_condition': 'fictitious', 'scripted_reaction': 'FICTITIOUS-NEW'}).status_code == 201
    with app.app_context():
        assert db.session.get(KineCaseVersion, version).content_json == original
        draft = KineCaseVersion.query.filter_by(case_id=cid, status='draft').one()
        assert len(json.loads(draft.content_json)['incidents']) == 2
    assert client.delete(f'/kine/cases/{cid}').status_code == 409
    assert client.post(f'/kine/cases/{cid}/lifecycle', json={'action': 'archive'}).status_code == 200
    with app.app_context():
        assert db.session.get(KineCaseVersion, version).content_json == original


def test_frozen_history_record_does_not_restore_new_attempt_access_and_other_student_is_refused(app):
    from test_kine_extension import student_login
    cid = case_fixture(app)
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        version = publish(case, 'teacher:1')
        historical = {'legacy_marker': 'UNCHANGED', 'points_earned': 14, 'passed': True}
        simulation = SimulationSession(student_id=1, clinical_case_id=cid, status='completed', evaluation_results=historical)
        freeze_simulation(simulation, version, db.session.get(Student, 1))
        db.session.add(simulation)
        db.session.commit()
        sid = simulation.id
        case.is_archived = True
        case.case_number = 'FICTITIOUS-RENAMED'
        case.patient_record.identity = {'name': 'FICTITIOUS-V2'}
        db.session.add(Student(student_code='990002', name='Fictitious B', ecos_type='kine', level='licence'))
        db.session.commit()
    client = app.test_client()
    student_login(client)
    result = client.get(f'/kine/simulation/{sid}/patient-record', headers={'Accept': 'application/json'})
    assert result.status_code == 200
    assert result.get_json()['record']['identity']['name'] == 'A.B.'
    page = client.get(f'/kine/simulation/{sid}/patient-record').get_data(as_text=True)
    assert 'commencer</button>' not in page
    history = client.get('/kine/history', headers={'Accept': 'application/json'}).get_json()['sessions'][0]
    assert history['case_number'] == 'KINE-001' and history['case_version_number'] == 1
    # T17's public projection must keep scores without exposing arbitrary
    # internal keys. Preservation is checked on the actual stored result.
    assert history['evaluation_results']['points_earned'] == 14
    assert history['evaluation_results']['passed'] is True
    assert 'legacy_marker' not in history['evaluation_results']
    with app.app_context():
        assert db.session.get(SimulationSession, sid).evaluation_results == historical
    assert client.post('/kine/simulation/start', json={'case_id': cid}).status_code == 403
    student_login(client, 2)
    assert client.get(f'/kine/simulation/{sid}/patient-record', headers={'Accept': 'application/json'}).status_code == 404
    teacher_login(client)
    teacher_history = client.get('/kine/dashboard/student/1').get_json()['sessions']
    assert teacher_history[0]['case_number'] == 'KINE-001'


def test_completion_consumes_captured_grid_and_level_not_live_configuration(app, monkeypatch):
    import kine_evaluation
    from blueprints.kine.routes_student import _complete_simulation
    cid = case_fixture(app)
    with app.app_context():
        version = publish(db.session.get(PatientCase, cid), 'teacher:1')
        student = db.session.get(Student, 1)
        simulation = SimulationSession(student_id=1, clinical_case_id=cid)
        freeze_simulation(simulation, version, student)
        db.session.add(simulation)
        db.session.commit()
        student.level = 'master'
        db.session.commit()
        def forbidden_live_grid(*args):
            raise AssertionError('Frozen completion must not load current grid')
        monkeypatch.setattr(kine_evaluation, 'get_kine_evaluation_grid', forbidden_live_grid)
        result = _complete_simulation(simulation)
        assert result['level'] == 'licence' and result['validation_threshold'] == 12
        assert result['student']['level'] == 'Licence'


def test_message_runtime_uses_v1_or_v2_reference_and_never_mutable_working_copy(app, monkeypatch):
    import blueprints.kine.routes_student as routes
    from test_kine_extension import student_login
    cid = case_fixture(app)
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        first = publish(case, 'teacher:1')
        a = SimulationSession(student_id=1, clinical_case_id=cid)
        freeze_simulation(a, first, db.session.get(Student, 1))
        db.session.add(a)
        db.session.commit()
        case.diagnosis = 'FICTITIOUS-V2'
        second = publish(case, 'teacher:1')
        b = SimulationSession(student_id=1, clinical_case_id=cid)
        freeze_simulation(b, second, db.session.get(Student, 1))
        db.session.add(b)
        db.session.commit()
        aid, bid = a.id, b.id
        case.diagnosis = 'FICTITIOUS-UNPUBLISHED'
        db.session.commit()
    class FakePatient:
        def __init__(self, clinical_case, *args, **kwargs):
            self.case = clinical_case
        def respond(self, *args):
            return {'type': 'patient', 'content': self.case.diagnosis}
    monkeypatch.setattr(routes, 'KinePatientEngine', FakePatient)
    client = app.test_client()
    student_login(client)
    assert client.post(f'/kine/simulation/{aid}/message', json={'message': 'Fictitious question'}).get_json()['response']['content'] == 'Heart failure'
    assert client.post(f'/kine/simulation/{bid}/message', json={'message': 'Fictitious question'}).get_json()['response']['content'] == 'FICTITIOUS-V2'


def test_unavailable_frozen_engine_is_refused_without_recomputing_result(app):
    from test_kine_extension import student_login
    cid = case_fixture(app)
    with app.app_context():
        version = publish(db.session.get(PatientCase, cid), 'teacher:1')
        simulation = SimulationSession(student_id=1, clinical_case_id=cid)
        freeze_simulation(simulation, version, db.session.get(Student, 1))
        reference = json.loads(simulation.evaluation_reference_json)
        reference['engine_sha256'] = 'unavailable-fixture-engine'
        simulation.evaluation_reference_json = json.dumps(reference)
        db.session.add(simulation)
        db.session.commit()
        sid = simulation.id
    client = app.test_client()
    student_login(client)
    assert client.post(f'/kine/simulation/{sid}/complete', json={}).status_code == 409
    with app.app_context():
        assert db.session.get(SimulationSession, sid).evaluation_results is None


def test_public_start_uses_only_assigned_publication_and_old_attempt_stays_on_v1(app):
    from test_kine_extension import student_login
    cid = case_fixture(app)
    client = app.test_client()
    student_login(client)
    assert client.get(f'/kine/cases/{cid}/patient-record').status_code == 403
    assert client.post('/kine/simulation/start', json={'case_id': cid}).status_code == 403

    teacher_login(client)
    first = client.post(f'/kine/cases/{cid}/versions/publish', json={}).get_json()
    assert client.put(f'/kine/cases/{cid}/availability', json={
        'version_id': first['id'], 'student_ids': [1],
    }).status_code == 200
    student_login(client)
    started_a = client.post('/kine/simulation/start', json={'case_id': cid})
    assert started_a.status_code == 201
    aid = started_a.get_json()['simulation_id']
    assert started_a.get_json()['version_reference']['case_version_id'] == first['id']

    with app.app_context():
        case = db.session.get(PatientCase, cid)
        case.diagnosis = 'FICTITIOUS-V2'
        case.patient_record.identity = {'name': 'FICTITIOUS-V2'}
        db.session.commit()
    teacher_login(client)
    second = client.post(f'/kine/cases/{cid}/versions/publish', json={}).get_json()
    assert second['number'] == 2

    # Publishing does not silently change the assigned version.
    student_login(client)
    still_v1 = client.post('/kine/simulation/start', json={'case_id': cid}).get_json()
    assert still_v1['version_reference']['case_version_id'] == first['id']
    teacher_login(client)
    assert client.put(f'/kine/cases/{cid}/availability', json={
        'version_id': second['id'], 'student_ids': [1],
    }).status_code == 200
    student_login(client)
    started_b = client.post('/kine/simulation/start', json={'case_id': cid})
    assert started_b.status_code == 201
    bid = started_b.get_json()['simulation_id']
    with app.app_context():
        a = db.session.get(SimulationSession, aid)
        b = db.session.get(SimulationSession, bid)
        assert simulation_case(a).diagnosis == 'Heart failure'
        assert simulation_case(b).diagnosis == 'FICTITIOUS-V2'
        assert json.loads(a.evaluation_reference_json)['validation_threshold'] == '12'
        assert json.loads(a.evaluation_reference_json)['referential'] == 'kardiox_criteria_v1:licence'


def test_exam_keeps_programmed_version_after_v2_and_profile_or_archive_changes(app):
    from datetime import timedelta
    from test_kine_extension import student_login
    cid = case_fixture(app)
    client = app.test_client()
    teacher_login(client)
    first = client.post(f'/kine/cases/{cid}/versions/publish', json={}).get_json()
    now = datetime.utcnow()
    exam = client.post('/kine/exams', json={
        'name': 'Fictitious versioned exam',
        'start_at': (now - timedelta(minutes=1)).isoformat(),
        'end_at': (now + timedelta(hours=1)).isoformat(),
        'max_duration_minutes': 20,
        'case_version_ids': [first['id']], 'student_ids': [1],
    })
    assert exam.status_code == 201
    assert exam.get_json()['case_versions'][0]['version_id'] == first['id']
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        case.diagnosis = 'FICTITIOUS-EXAM-V2'
        db.session.commit()
    second = client.post(f'/kine/cases/{cid}/versions/publish', json={}).get_json()
    assert second['id'] != first['id']
    student_login(client)
    started = client.post('/kine/simulation/start', json={
        'case_id': cid, 'mode': 'exam', 'exam_id': exam.get_json()['id'],
    })
    assert started.status_code == 201
    sid = started.get_json()['simulation_id']
    with app.app_context():
        simulation = db.session.get(SimulationSession, sid)
        db.session.get(Student, 1).level = 'master'
        db.session.get(PatientCase, cid).is_archived = True
        db.session.commit()
        assert simulation.case_version_id == first['id']
        assert simulation.frozen_student_level == 'licence'
        assert simulation_case(simulation).diagnosis == 'Heart failure'
    history = client.get('/kine/history', headers={'Accept': 'application/json'}).get_json()['sessions']
    item = next(row for row in history if row['id'] == sid)
    assert item['case_version_number'] == 1 and item['case_number'] == 'KINE-001'
