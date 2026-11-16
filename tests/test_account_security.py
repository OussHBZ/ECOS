"""T02 identity, forgery and additive migration; D02 scope has its own matrix."""
from datetime import datetime, timedelta
from contextlib import closing
import shutil
import sqlite3
from html.parser import HTMLParser

import pytest
from sqlalchemy.engine import Connection

from account_migrations import VERSION, upgrade_account_lifecycle
from models import db, Exam, PatientCase, SimulationSession, Student, Teacher, AdminAccess, TeacherStudentScope, TeacherGroupScope
from test_kine_extension import app, create_case, teacher_login
from test_teacher_report_regressions import admin_login
from test_migration_baseline import legacy_file, history, healthy


def prepare_passwords(app):
    with app.app_context():
        db.session.get(Student, 1).set_password('fixture-password')
        db.session.get(Teacher, 1).set_password('fixture-password')
        db.session.commit()


def login(client, role, password='fixture-password'):
    payload = dict(login_type=role, workspace='kine', password=password)
    payload.update({'student_code': '123456'} if role == 'student' else {'teacher_email': 'teacher@example.test'})
    return client.post('/login', data=payload)


@pytest.mark.parametrize('role,landing', [('student', '/kine/student'), ('teacher', '/kine/dashboard')])
def test_suspension_revokes_open_sessions_and_reactivation_requires_login(app, role, landing):
    prepare_passwords(app)
    admin = app.test_client()
    admin_login(admin)
    used = app.test_client()
    untouched = app.test_client()
    assert login(used, role).status_code == 302
    assert login(untouched, role).status_code == 302
    assert used.get(landing).status_code == 200
    assert admin.post(f'/admin/accounts/{role}/1/status', json={'action': 'suspend'}).status_code == 200
    assert used.get(landing, headers={'Accept': 'application/json'}).status_code == 401
    # An unused old cookie cannot become valid again when the account is reactivated.
    assert admin.post(f'/admin/accounts/{role}/1/status', json={'action': 'reactivate'}).status_code == 200
    assert untouched.get(landing, headers={'Accept': 'application/json'}).status_code == 401
    assert login(used, role).status_code == 302
    assert used.get(landing).status_code == 200


@pytest.mark.parametrize('role', ['student', 'teacher'])
def test_suspended_account_cannot_login_or_modify_own_status(app, role):
    prepare_passwords(app)
    client = app.test_client()
    login(client, role)
    assert client.post(f'/admin/accounts/{role}/1/status', json={'action': 'reactivate'}).status_code == 401
    admin = app.test_client()
    admin_login(admin)
    admin.post(f'/admin/accounts/{role}/1/status', json={'action': 'suspend'})
    response = login(client, role)
    # Existing stale session first gets revoked; the subsequent login is refused too.
    response = login(client, role)
    assert '/login' in response.location
    with client.session_transaction() as state:
        assert not state.get('_user_id')


@pytest.mark.parametrize('role', ['student', 'teacher'])
def test_password_reset_revokes_open_session(app, role):
    prepare_passwords(app)
    client = app.test_client()
    login(client, role)
    admin = app.test_client()
    admin_login(admin)
    endpoint = '/admin/students/1/reset-password' if role == 'student' else '/admin/teachers/1/reset-password'
    assert admin.post(endpoint, json={'password': 'new-fixture-password'}).status_code == 200
    landing = '/kine/student' if role == 'student' else '/kine/dashboard'
    assert client.get(landing, headers={'Accept': 'application/json'}).status_code == 401
    assert '/login' in login(client, role).location
    assert login(client, role, 'new-fixture-password').status_code == 302
    assert client.get(landing).status_code == 200


@pytest.mark.parametrize('body', ['json', 'form'])
def test_missing_or_foreign_csrf_token_refuses_admin_mutation(app, body):
    client = app.test_client()
    admin_login(client)
    arguments = {'json': {'action': 'suspend'}} if body == 'json' else {'data': {'action': 'suspend'}}
    assert client.post('/admin/accounts/student/1/status', csrf=False, **arguments).status_code == 403
    foreign = app.test_client().get('/csrf-token').get_json()['csrf_token']
    assert client.post('/admin/accounts/student/1/status', csrf=False,
        headers={'X-CSRF-Token': foreign}, **arguments).status_code == 403
    with app.app_context():
        assert db.session.get(Student, 1).account_status == 'active'


@pytest.mark.parametrize('headers', [{'Origin': 'https://foreign.invalid'}, {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}])
def test_forged_origin_refused_even_with_valid_csrf_token(app, headers):
    admin = app.test_client()
    admin_login(admin)
    assert admin.post('/admin/accounts/student/1/status', json={'action': 'suspend'}, headers=headers).status_code == 403
    with app.app_context():
        assert db.session.get(Student, 1).account_status == 'active'


def test_login_csrf_required_and_token_response_not_cacheable(app):
    prepare_passwords(app)
    client = app.test_client()
    assert client.post('/login', csrf=False,
        data={'login_type': 'student', 'student_code': '123456', 'password': 'fixture-password'}).status_code == 403
    token = client.get('/csrf-token')
    assert token.headers['Cache-Control'] == 'no-store'
    assert set(token.get_json()) == {'csrf_token'}
    assert login(client, 'student').status_code == 302


def test_teacher_session_identity_cannot_be_rebound_and_payload_role_ignored(app):
    client = app.test_client()
    teacher_login(client)
    assert client.post('/admin/accounts/student/1/status', json={
        'action': 'suspend', 'user_type': 'admin', 'admin_authenticated': True}).status_code == 401
    with client.session_transaction() as state:
        state['teacher_id'] = 999
    assert client.get('/kine/cases', headers={'Accept': 'application/json'}).status_code == 401


@pytest.mark.parametrize('surface', ['chat', 'timeline', 'progress'])
def test_student_cannot_substitute_another_students_session_id(app, surface):
    teacher = app.test_client()
    teacher_login(teacher)
    folder = teacher.post('/kine/folders', json={'name': 'Security fixture'}).get_json()['id']
    case_id = create_case(teacher, folder)
    with app.app_context():
        other = Student(student_code='820002', name='Fictif B', level='licence', ecos_type='kine')
        other.set_password('fixture-password')
        db.session.add(other)
        db.session.flush()
        simulation = SimulationSession(student_id=1, clinical_case_id=case_id,
            conversation=[{'role': 'human', 'content': 'PRIVATE-A-MARKER'}])
        db.session.add(simulation)
        db.session.commit()
        sid = simulation.id
    client = app.test_client()
    client.post('/login', data={'login_type': 'student', 'workspace': 'kine',
                               'student_code': '820002', 'password': 'fixture-password'})
    response = client.get(f'/kine/simulation/{sid}/{surface}', headers={'Accept': 'application/json'})
    assert response.status_code == 404
    assert b'PRIVATE-A-MARKER' not in response.data


def test_anonymous_request_cannot_close_another_students_exam(app):
    with app.app_context():
        case = PatientCase(case_number='SEC-EXAM', specialty='kine')
        exam = Exam(name='Fictif', start_at=datetime.utcnow() - timedelta(hours=2),
                    end_at=datetime.utcnow() - timedelta(hours=1), max_duration_minutes=1)
        simulation = SimulationSession(student_id=1, clinical_case=case, exam=exam, mode='exam',
            started_at=datetime.utcnow() - timedelta(hours=2))
        db.session.add(simulation)
        db.session.commit()
        sid = simulation.id
    assert app.test_client().get('/kine/history', headers={'Accept': 'application/json'}).status_code == 401
    with app.app_context():
        assert db.session.get(SimulationSession, sid).status == 'in_progress'
        assert db.session.get(SimulationSession, sid).evaluation_results is None


def remove_new_columns(app):
    with app.app_context():
        db.session.add(AdminAccess(access_code='legacy-fixture-code', last_used=datetime(2020, 1, 1)))
        db.session.commit()
        with db.engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE teacher_student_scopes')
            connection.exec_driver_sql('DROP TABLE teacher_group_scopes')
            connection.exec_driver_sql('ALTER TABLE admin_access DROP COLUMN admin_profile')
            for table in ('student', 'teacher'):
                for column in ('account_status', 'auth_version'):
                    connection.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN {column}')


def test_account_migration_is_additive_repeated_and_preserves_legacy_histories(legacy_file):
    app, path = legacy_file
    original = history(path)
    remove_new_columns(app)
    backup = path.with_name('before-accounts.sqlite')
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    with app.app_context():
        upgrade_account_lifecycle(db.engine)
        upgrade_account_lifecycle(db.engine)
        access = AdminAccess.query.filter_by(access_code='legacy-fixture-code').one()
        assert access.admin_profile == 'technical'
        assert access.last_used == datetime(2020, 1, 1)
        assert TeacherStudentScope.query.count() == TeacherGroupScope.query.count() == 0
        assert db.session.execute(db.text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar() == 1
        # This helper only adds account columns; the fixture intentionally also
        # lacks unrelated older columns. Query the new columns without ORM-wide
        # loading, which would require those other migrations first.
        assert tuple(db.session.execute(db.text(
            'SELECT account_status,auth_version FROM student WHERE id=1')).one()) == ('active', 0)
    assert history(path) == original
    healthy(path)
    restored = path.with_name('restored-before-accounts.sqlite')
    shutil.copyfile(backup, restored)
    assert history(restored) == original
    healthy(restored)
    with closing(sqlite3.connect(restored)) as connection:
        assert 'account_status' not in {c[1] for c in connection.execute('PRAGMA table_info(student)')}


def test_account_migration_resumes_without_marking_partial_ddl_applied(legacy_file, monkeypatch):
    app, path = legacy_file
    original = history(path)
    remove_new_columns(app)
    execute = Connection.exec_driver_sql

    def fail(connection, statement, *args, **kwargs):
        if 'ALTER TABLE teacher ADD COLUMN auth_version' in statement:
            raise RuntimeError('fixture DDL interruption')
        return execute(connection, statement, *args, **kwargs)

    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr(Connection, 'exec_driver_sql', fail)
            with pytest.raises(RuntimeError, match='fixture DDL interruption'):
                upgrade_account_lifecycle(db.engine)
        assert db.session.execute(db.text('SELECT count(*) FROM schema_migrations')).scalar() == 0
        upgrade_account_lifecycle(db.engine)
        assert db.session.get(Teacher, 1) is None  # No account created by the migration.
    assert history(path) == original
    healthy(path)


def test_account_migration_refuses_changed_applied_checksum(legacy_file):
    app, path = legacy_file
    original = history(path)
    with app.app_context():
        upgrade_account_lifecycle(db.engine)
        db.session.execute(db.text('UPDATE schema_migrations SET checksum=:bad'), {'bad': 'fixture-invalid'})
        db.session.commit()
        with pytest.raises(RuntimeError, match='checksum mismatch'):
            upgrade_account_lifecycle(db.engine)
    assert history(path) == original


def test_account_migration_refuses_incompatible_existing_column(legacy_file):
    app, path = legacy_file
    original = history(path)
    with app.app_context():
        with db.engine.begin() as connection:
            connection.exec_driver_sql('ALTER TABLE student DROP COLUMN account_status')
            connection.exec_driver_sql('ALTER TABLE student ADD COLUMN account_status TEXT')
        with pytest.raises(RuntimeError, match='Incompatible account schema'):
            upgrade_account_lifecycle(db.engine)
        assert db.session.execute(db.text('SELECT count(*) FROM schema_migrations')).scalar() == 0
    assert history(path) == original


@pytest.mark.parametrize('incompatible', ['admin_profile', 'scope'])
def test_account_migration_refuses_incompatible_authority_schema(legacy_file, incompatible):
    app, path = legacy_file
    original = history(path)
    with app.app_context():
        with db.engine.begin() as connection:
            if incompatible == 'admin_profile':
                connection.exec_driver_sql('ALTER TABLE admin_access DROP COLUMN admin_profile')
                connection.exec_driver_sql('ALTER TABLE admin_access ADD COLUMN admin_profile TEXT')
            else:
                connection.exec_driver_sql('DROP TABLE teacher_group_scopes')
                connection.exec_driver_sql('CREATE TABLE teacher_group_scopes (teacher_id INTEGER)')
        with pytest.raises(RuntimeError, match='Incompatible'):
            upgrade_account_lifecycle(db.engine)
        assert db.session.execute(db.text('SELECT count(*) FROM schema_migrations')).scalar() == 0
    assert history(path) == original


def test_logout_is_post_and_csrf_protected(app):
    prepare_passwords(app)
    client = app.test_client()
    login(client, 'student')
    assert client.get('/logout').status_code == 405
    assert client.get('/kine/student').status_code == 200
    assert client.post('/logout', csrf=False).status_code == 403
    assert client.post('/logout').status_code == 302
    assert client.get('/kine/student', headers={'Accept': 'application/json'}).status_code == 401


@pytest.mark.parametrize('role,url', [('anonymous', '/login'), ('admin', '/admin/'), ('teacher', '/kine/cases/new')])
def test_rendered_native_post_forms_carry_session_csrf(app, role, url):
    class Forms(HTMLParser):
        def __init__(self):
            super().__init__()
            self.forms, self.current, self.meta = [], None, None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'meta' and attrs.get('name') == 'csrf-token':
                self.meta = attrs['content']
            if tag == 'form':
                self.current = {'post': attrs.get('method', '').lower() == 'post', 'token': None}
            if tag == 'input' and self.current is not None and attrs.get('name') == 'csrf_token':
                self.current['token'] = attrs.get('value')

        def handle_endtag(self, tag):
            if tag == 'form' and self.current is not None:
                self.forms.append(self.current)
                self.current = None

    prepare_passwords(app)
    client = app.test_client()
    if role == 'admin':
        admin_login(client)
    elif role == 'teacher':
        teacher_login(client)
    response = client.get(url)
    assert response.status_code == 200
    parser = Forms()
    parser.feed(response.get_data(as_text=True))
    posts = [form for form in parser.forms if form['post']]
    assert posts and parser.meta
    assert all(form['token'] == parser.meta for form in posts)
    if role == 'anonymous':
        # Native form submission, deliberately without the test client's header.
        assert client.post('/login', csrf=False, data={'login_type': 'student', 'workspace': 'kine',
            'student_code': '123456', 'password': 'fixture-password', 'csrf_token': posts[0]['token']}).status_code == 302


def test_logout_form_keeps_reverse_proxy_prefix(app):
    client = app.test_client()
    teacher_login(client)
    response = client.get('/kine/cases/new', environ_overrides={'SCRIPT_NAME': '/ecos'})
    assert response.status_code == 200
    assert 'action="/ecos/logout"' in response.get_data(as_text=True)


@pytest.mark.parametrize('role', ['anonymous', 'student', 'teacher'])
def test_profile_management_is_admin_only_and_ignores_forged_role(app, role):
    client = app.test_client()
    if role == 'student':
        prepare_passwords(app)
        login(client, role)
    elif role == 'teacher':
        teacher_login(client)
    assert client.get('/admin/accounts/student/1', headers={'Accept': 'application/json'}).status_code == 401
    assert client.patch('/admin/accounts/student/1', json={'name': 'FORGED', 'user_type': 'admin'}).status_code == 401
    with app.app_context():
        assert db.session.get(Student, 1).name == 'Student'


def test_admin_edits_profiles_without_exposing_credentials_or_rewriting_results(app):
    with app.app_context():
        case = PatientCase(case_number='PROFILE-FIXTURE', specialty='kine')
        simulation = SimulationSession(student_id=1, clinical_case=case, status='completed',
            conversation=[{'role': 'human', 'content': 'HISTORY-UNCHANGED'}],
            evaluation_results={'student': {'name': 'Original historical name'}, 'legacy': True})
        db.session.add(simulation)
        db.session.commit()
        sid = simulation.id
        original = db.session.execute(db.text(
            'SELECT conversation,evaluation_results FROM simulation_sessions WHERE id=:id'), {'id': sid}).one()
    admin = app.test_client()
    admin_login(admin)
    result = admin.patch('/admin/accounts/student/1', json={'name': 'Updated fixture', 'group_name': 'G2', 'class_name': 'C2'})
    assert result.status_code == 200
    assert result.get_json()['group_name'] == 'G2'
    assert not {'password_hash', 'auth_version', 'password'} & result.get_json().keys()
    assert admin.patch('/admin/accounts/student/1', json={'account_status': 'active'}).status_code == 400
    assert admin.patch('/admin/accounts/student/1', json={'level': 'invalid', 'name': 'ROLLBACK'}).status_code == 400
    assert admin.patch('/admin/accounts/teacher/1', json={'email': 'new-fixture@example.test', 'name': 'Updated teacher'}).status_code == 200
    with app.app_context():
        assert db.session.get(Student, 1).name == 'Updated fixture'
        assert db.session.get(Teacher, 1).email == 'new-fixture@example.test'
        current = db.session.execute(db.text(
            'SELECT conversation,evaluation_results FROM simulation_sessions WHERE id=:id'), {'id': sid}).one()
        assert current == original
