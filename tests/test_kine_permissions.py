"""D02 deterministic authorization matrix; fictitious people/documents only."""
from datetime import datetime, timedelta
import io
import pytest
from flask import g, has_app_context
from openpyxl import load_workbook
from sqlalchemy import text

from models import (db, Student, Teacher, AdminAccess, PatientCase, SimulationSession,
                    Exam, KineCaseAvailability, KineCaseImportBatch, KineCaseDraft,
                    TeacherStudentScope, TeacherGroupScope)
from case_versions import audience_payload, canonical, publish
from test_kine_extension import app, teacher_login, student_login
from test_teacher_report_regressions import admin_login


def pedagogical_login(client, app):
    with app.app_context():
        access = AdminAccess.query.filter_by(access_code='fixture-pedagogical').first()
        if not access:
            access = AdminAccess(access_code='fixture-pedagogical', admin_profile='pedagogical')
            db.session.add(access)
            db.session.commit()
        aid = access.id
    with client.session_transaction() as state:
        state.clear()
        state.update(user_type='admin', admin_authenticated=True, admin_access_id=aid)
    if has_app_context():
        g.pop('_login_user', None)


@pytest.fixture()
def population(app, tmp_path):
    app.config['KINE_IMPORT_FOLDER'] = str(tmp_path)
    with app.app_context():
        other = Student(student_code='900002', name='PRIVATE-STUDENT-B', ecos_type='kine', level='licence', group_name='Group B')
        standard = Student(student_code='900003', name='STANDARD-STUDENT', ecos_type='standard')
        teacher = Teacher(email='unassigned@example.test', name='Unassigned', ecos_type='kine', password_hash='x')
        case = PatientCase(case_number='PERM-KINE', specialty='kine', level='both', mode_availability='both', diagnosis='PRIVATE-CASE')
        stdcase = PatientCase(case_number='PERM-STANDARD', specialty='standard-fixture')
        db.session.add_all([other, standard, teacher, case, stdcase])
        db.session.flush()
        version = publish(case, 'fixture:population')
        db.session.flush()
        db.session.add(KineCaseAvailability(
            case_id=case.id, version_id=version.id,
            audience_json=canonical(audience_payload([1])),
            updated_actor='fixture:population',
        ))
        sims = [SimulationSession(student_id=sid, clinical_case_id=cid, status='completed',
                    conversation=[{'role': 'human', 'content': marker}],
                    evaluation_results={'points_earned': 11, 'points_total': 20, 'passed': False},
                    completed_at=datetime.utcnow())
                for sid, cid, marker in [(1, case.id, 'PRIVATE-A'), (other.id, case.id, 'PRIVATE-B'), (1, stdcase.id, 'PRIVATE-STANDARD')]]
        exam = Exam(name='PRIVATE-EXAM', created_by=teacher.id, start_at=datetime.utcnow() + timedelta(hours=1),
                    end_at=datetime.utcnow() + timedelta(hours=2), max_duration_minutes=30, students=[other], cases=[case])
        batch = KineCaseImportBatch(created_by=teacher.id)
        db.session.add(batch); db.session.flush()
        # Use the real storage contract and checksum; permissions stay under
        # exactly the same assertions now that downloads verify integrity.
        from blueprints.kine.routes_import import _write_source
        source, checksum = _write_source(batch.id, 'private-document.docx', b'PRIVATE-DOCUMENT-B')
        draft = KineCaseDraft(batch=batch, created_by=teacher.id, source_filename='private-document.docx',
                              source_path=source, source_sha256=checksum)
        db.session.add_all([*sims, exam, draft])
        db.session.commit()
        result = dict(b=other.id, standard=standard.id, teacher=teacher.id, case=case.id,
                      sim_a=sims[0].id, sim_b=sims[1].id, sim_std=sims[2].id,
                      exam=exam.id, batch=batch.id, draft=draft.id)
    return result


def as_role(app, population, role):
    client = app.test_client()
    if role == 'student_a': student_login(client)
    elif role == 'student_b': student_login(client, population['b'])
    elif role == 'teacher': teacher_login(client)
    elif role == 'unassigned': teacher_login(client, population['teacher'])
    elif role == 'technical': admin_login(client)
    elif role == 'pedagogical': pedagogical_login(client, app)
    return client


@pytest.mark.parametrize('role', ['anonymous', 'student_a', 'student_b', 'teacher', 'unassigned', 'technical', 'pedagogical'])
@pytest.mark.parametrize('surface', ['detail_json', 'detail_page', 'pdf', 'review', 'zip', 'student'])
def test_direct_result_matrix(app, population, role, surface):
    client = as_role(app, population, role)
    sid = population['sim_a']
    path = f'/kine/dashboard/simulation/{sid}'
    if surface == 'detail_json': response = client.get(path, headers={'Accept': 'application/json'})
    elif surface == 'detail_page': response = client.get(path)
    elif surface == 'pdf': response = client.get(path + '/pdf')
    elif surface == 'review': response = client.post(path + '/review', json={'teacher_comments': 'Fictitious review'})
    elif surface == 'zip': response = client.post('/kine/dashboard/conversations/pdf', json={'session_ids': [sid]})
    else: response = client.get('/kine/dashboard/student/1', headers={'Accept': 'application/json'})
    allowed = role in ('teacher', 'pedagogical')
    assert response.status_code == (200 if allowed else 404 if role == 'unassigned' else 403 if role == 'technical' else 401)
    if not allowed:
        assert b'PRIVATE-A' not in response.data
        assert response.mimetype not in ('application/pdf', 'application/zip')
        with app.app_context():
            assert db.session.get(SimulationSession, sid).teacher_comments is None


@pytest.mark.parametrize('role', ['teacher', 'unassigned', 'technical', 'pedagogical'])
@pytest.mark.parametrize('surface', ['dashboard', 'csv', 'xlsx'])
def test_collection_exports_use_live_follow_scope(app, population, role, surface):
    client = as_role(app, population, role)
    path = '/kine/dashboard' if surface == 'dashboard' else '/kine/dashboard/export?format=' + surface
    response = client.get(path, headers={'Accept': 'application/json'})
    if role == 'technical':
        assert response.status_code == 403
        return
    assert response.status_code == 200
    if surface == 'xlsx':
        data = str(list(load_workbook(io.BytesIO(response.data), read_only=True).active.values))
    else: data = response.get_data(as_text=True)
    assert ('PRIVATE-STUDENT-B' in data) == (role == 'pedagogical')
    assert 'PERM-STANDARD' not in data
    if role == 'unassigned':
        assert 'PERM-KINE' not in data


def test_mixed_zip_is_refused_atomically_and_standard_ids_are_refused(app, population):
    client = as_role(app, population, 'teacher')
    for other in [population['sim_b'], population['sim_std'], 999999]:
        result = client.post('/kine/dashboard/conversations/pdf', json={'session_ids': [population['sim_a'], other]})
        assert result.status_code == 404
        assert result.mimetype == 'application/json'
        assert client.get(f'/kine/dashboard/simulation/{other}/pdf').status_code == 404


@pytest.mark.parametrize('suffix', ['chat', 'timeline', 'progress'])
def test_student_cannot_access_standard_simulation_through_kine(app, population, suffix):
    client = as_role(app, population, 'student_a')
    response = client.get(f'/kine/simulation/{population["sim_std"]}/{suffix}', headers={'Accept': 'application/json'})
    assert response.status_code == 404
    assert b'PRIVATE-STANDARD' not in response.data
    history = client.get('/kine/history').get_data(as_text=True)
    assert 'PERM-STANDARD' not in history


@pytest.mark.parametrize('role', ['anonymous', 'student_a', 'teacher', 'technical', 'pedagogical'])
@pytest.mark.parametrize('surface', ['batch', 'draft', 'source', 'exam'])
def test_import_sources_previews_and_exam_rosters_are_protected(app, population, role, surface):
    paths = dict(batch=f'/kine/case-imports/{population["batch"]}', draft=f'/kine/case-import-drafts/{population["draft"]}',
                 source=f'/kine/case-import-drafts/{population["draft"]}/source', exam=f'/kine/exams/{population["exam"]}')
    response = as_role(app, population, role).get(paths[surface], headers={'Accept': 'application/json'})
    assert response.status_code == (200 if role == 'pedagogical' else 404 if role == 'teacher' else 403 if role == 'technical' else 401)
    if role != 'pedagogical':
        assert b'PRIVATE-DOCUMENT-B' not in response.data
        assert b'PRIVATE-STUDENT-B' not in response.data


def test_admin_explicit_assignments_group_membership_and_immediate_revocation(app, population):
    admin = as_role(app, population, 'technical')
    teacher = as_role(app, population, 'teacher')
    endpoint = '/admin/teachers/1/kine-scope'
    assert teacher.put(endpoint, json={'student_ids': [population['b']], 'group_names': []}).status_code == 401
    invalid = {'student_ids': [population['standard']], 'group_names': []}
    assert admin.put(endpoint, json=invalid).status_code == 400
    assert teacher.get(f'/kine/dashboard/student/{population["b"]}').status_code == 404
    assert admin.put(endpoint, json={'student_ids': [1], 'group_names': ['Group B']}).status_code == 200
    assert teacher.get(f'/kine/dashboard/student/{population["b"]}').status_code == 200
    # Group changes update scope at the next request; historical data unchanged.
    assert admin.patch(f'/admin/accounts/student/{population["b"]}', json={'group_name': 'Group C'}).status_code == 200
    assert teacher.get(f'/kine/dashboard/student/{population["b"]}').status_code == 404
    assert admin.put(endpoint, json={'student_ids': [population['b']], 'group_names': []}).status_code == 200
    assert teacher.get('/kine/dashboard/student/1').status_code == 404
    assert teacher.get(f'/kine/dashboard/student/{population["b"]}').status_code == 200
    assert admin.put(endpoint, json={'student_ids': [], 'group_names': []}).status_code == 200
    assert teacher.get(f'/kine/dashboard/student/{population["b"]}').status_code == 404


def test_exam_creation_and_level_updates_cannot_grant_self_following(app, population):
    teacher = as_role(app, population, 'teacher')
    assert teacher.patch(f'/kine/students/{population["b"]}/level', json={'level': 'master'}).status_code == 404
    assert teacher.patch('/kine/students/1/level', json={'level': 'master', 'group_name': 'Group B'}).status_code == 403
    base = dict(name='Scope attempt', start_at=(datetime.utcnow() + timedelta(hours=1)).isoformat(),
                end_at=(datetime.utcnow() + timedelta(hours=2)).isoformat(), max_duration_minutes=30, case_ids=[population['case']])
    for extra in [{'student_ids': [population['b']]}, {'group_names': ['Group B']}]:
        assert teacher.post('/kine/exams', json={**base, **extra}).status_code == 400
    assert teacher.post('/kine/exams', json={**base, 'student_ids': [1]}).status_code == 201


def test_technical_admin_cannot_read_kine_data_through_legacy_admin_urls(app, population):
    client = as_role(app, population, 'technical')
    for path in ['/admin/students/1/details', '/admin/stations/PERM-KINE/details']:
        assert client.get(path).status_code == 403
    assert client.get('/admin/students').get_json()['students'][0]['average_score'] is None
    assert 'PRIVATE-STUDENT-B' not in str(client.get('/admin/overview').get_json()['recent_activity'])
    stations = client.get('/admin/stations').get_json()['stations']
    assert all(s['case_number'] != 'PERM-KINE' for s in stations)
    # Account-only information remains available to technical administration.
    assert client.get('/admin/accounts/student/1').status_code == 200
    assert client.get('/admin/stations/PERM-STANDARD/details').status_code == 200


def test_two_admin_credentials_and_persisted_authority_ignore_forged_claims(app, population, monkeypatch):
    import auth
    monkeypatch.setattr(auth, 'ADMIN_ACCESS_CODE', 'fixture-tech-code')
    monkeypatch.setattr(auth, 'PEDAGOGICAL_ADMIN_ACCESS_CODE', 'fixture-ped-code')
    client = app.test_client()
    assert client.post('/login', data={'login_type': 'admin', 'access_code': 'fixture-tech-code', 'admin_profile': 'pedagogical'}).status_code == 302
    assert client.get('/kine/dashboard').status_code == 403
    with client.session_transaction() as state:
        state['admin_profile'] = 'pedagogical'
    assert client.get('/kine/dashboard').status_code == 403
    assert client.post('/login', data={'login_type': 'admin', 'access_code': 'fixture-ped-code'}).status_code == 302
    assert client.get('/kine/dashboard').status_code == 200
    with app.app_context():
        record = AdminAccess.query.filter_by(access_code='fixture-ped-code').one()
        record.admin_profile = 'technical'
        db.session.commit()
    assert client.get('/kine/dashboard').status_code == 403
    monkeypatch.setattr(auth, 'PEDAGOGICAL_ADMIN_ACCESS_CODE', 'fixture-tech-code')
    client.post('/logout')
    response = client.post('/login', data={'login_type': 'admin', 'access_code': 'fixture-tech-code'})
    assert '/login' in response.location
    assert client.get('/kine/dashboard').status_code == 401


def test_account_deletion_refused_with_results_and_following_intact(app, population):
    client = as_role(app, population, 'technical')
    with app.app_context():
        old = db.session.execute(text('SELECT conversation,evaluation_results FROM simulation_sessions ORDER BY id')).all()
    assert client.delete('/admin/students/1/delete').status_code == 409
    with app.app_context():
        assert db.session.get(Student, 1).account_status == 'active'
        assert TeacherStudentScope.query.filter_by(teacher_id=1, student_id=1).count() == 1
        assert db.session.execute(text('SELECT conversation,evaluation_results FROM simulation_sessions ORDER BY id')).all() == old


def test_standard_teacher_cannot_bypass_kine_permissions(app, population):
    with app.app_context():
        teacher = Teacher(email='standard@example.test', name='Standard teacher', ecos_type='standard', password_hash='x')
        db.session.add(teacher)
        db.session.commit()
        tid = teacher.id
    client = app.test_client()
    teacher_login(client, tid)
    assert client.get('/teacher/students/1/detailed_performance').status_code == 404
    assert client.delete('/teacher/delete_case/PERM-KINE').status_code == 404
    assert client.post('/teacher/edit_case/PERM-KINE', json={'edited_data': {'diagnosis': 'FORGED'}}).status_code == 404
    assert client.post('/teacher/save_edited_case', json={'case_number': 'PERM-KINE', 'specialty': 'cardio', 'edited_data': {'diagnosis': 'FORGED'}}).status_code == 404
    assert client.post('/teacher/edit_case/PERM-STANDARD', json={'edited_data': {'specialty': 'kine'}}).status_code == 404
    students = client.get('/teacher/students/performance').get_json()['students']
    assert {s['student_code'] for s in students} == {'900003'}
    assert client.get('/teacher/stations').status_code == 200
    assert client.post('/teacher/edit_case/PERM-STANDARD', json={'edited_data': {'diagnosis': 'Standard edit'}}).status_code == 200
    assert client.post('/teacher/edit_case/PERM-STANDARD', json={'edited_data': {'diagnosis': 'CSRF'}}, csrf=False).status_code == 403
    with app.app_context():
        assert db.session.get(PatientCase, population['case']).diagnosis == 'PRIVATE-CASE'


@pytest.mark.parametrize('role', ['anonymous', 'student_a', 'student_b', 'teacher', 'technical', 'pedagogical'])
def test_known_pdf_filename_cannot_bypass_object_authorization(app, population, role, monkeypatch, tmp_path):
    from account_security import legacy_pdf_download
    import tempfile
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))
    filename = 'known-kine-report.pdf'
    (tmp_path / filename).write_bytes(b'PRIVATE-PDF-A')
    app.add_url_rule('/download_pdf/<filename>', view_func=legacy_pdf_download)
    client = as_role(app, population, role)
    assert client.get('/download_pdf/' + filename).status_code == 404
    assert b'PRIVATE-PDF-A' not in client.get('/download_pdf/' + filename).data
    # Preserve a legitimate, explicitly session-bound old standard download.
    student_login(client, population['standard'])
    with client.session_transaction() as state:
        state['last_pdf'] = filename
    assert client.get('/download_pdf/' + filename).data == b'PRIVATE-PDF-A'


def test_report_generations_for_same_case_have_unique_names():
    from simple_pdf_generator import create_simple_consultation_pdf
    first = create_simple_consultation_pdf([], 'SAME-FICTITIOUS-CASE', {'points_earned': 1})
    second = create_simple_consultation_pdf([], 'SAME-FICTITIOUS-CASE', {'points_earned': 2})
    assert first and second and first != second


@pytest.mark.parametrize('role,surface', [
    ('student_a', 'chat'), ('student_a', 'timeline'), ('student_a', 'progress'),
    ('teacher', 'detail'), ('teacher', 'pdf'), ('teacher', 'source'), ('teacher', 'review'),
])
def test_suspended_open_cookie_cannot_access_pages_json_or_files(app, population, role, surface):
    client = as_role(app, population, role)
    if role == 'teacher' and surface == 'source':
        with app.app_context():
            draft = db.session.get(KineCaseDraft, population['draft'])
            draft.created_by = 1
            db.session.commit()
    admin = as_role(app, population, 'technical')
    kind = 'student' if role == 'student_a' else 'teacher'
    assert admin.post(f'/admin/accounts/{kind}/1/status', json={'action': 'suspend'}).status_code == 200
    if role == 'student_a': path = f'/kine/simulation/{population["sim_a"]}/{surface}'
    elif surface == 'source': path = f'/kine/case-import-drafts/{population["draft"]}/source'
    else: path = f'/kine/dashboard/simulation/{population["sim_a"]}' + ('' if surface == 'detail' else '/' + surface)
    if surface == 'review': response = client.post(path, json={'teacher_comments': 'FORGED'}, csrf=False)
    else: response = client.get(path, headers={'Accept': 'application/json'})
    assert response.status_code == 401
    assert b'PRIVATE-A' not in response.data and b'PRIVATE-DOCUMENT-B' not in response.data


def test_exam_sharing_depends_on_entire_roster_scope_and_revokes_immediately(app, population):
    teacher = as_role(app, population, 'teacher')
    admin = as_role(app, population, 'technical')
    path = f'/kine/exams/{population["exam"]}'
    assert teacher.get(path).status_code == 404
    admin.put('/admin/teachers/1/kine-scope', json={'student_ids': [population['b']], 'group_names': []})
    assert teacher.get(path).status_code == 200  # Sharing doesn't invent case/exam ownership rules.
    admin.put('/admin/teachers/1/kine-scope', json={'student_ids': [], 'group_names': []})
    assert teacher.get(path).status_code == 404
