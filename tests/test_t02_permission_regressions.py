"""T02 re-audit: private draft metadata and mixed legacy histories, fictitious only."""
import hashlib
import io
import json
from datetime import datetime

import pytest
from sqlalchemy import text
from models import db, Teacher, StudentPerformance, KineCaseDraft, KineCaseImportBatch
from test_kine_extension import app, teacher_login, student_login
from test_kine_permissions import population, as_role


@pytest.mark.parametrize('role', ['teacher', 'pedagogical'])
def test_import_duplicate_search_cannot_probe_other_teachers_private_sources(app, population, role, tmp_path):
    content = b'FICTITIOUS-PRIVATE-WORD-SOURCE'
    with app.app_context():
        draft = db.session.get(KineCaseDraft, population['draft'])
        draft.source_sha256 = hashlib.sha256(content).hexdigest()
        draft.source_filename = 'private-source.docx'
        db.session.commit()
    app.config['KINE_IMPORT_FOLDER'] = str(tmp_path)
    client = as_role(app, population, role)
    response = client.post('/kine/case-imports', data={
        'documents': (io.BytesIO(content), 'private-source.docx')}, headers={'Accept': 'application/json'})
    assert response.status_code == 201
    result = response.get_json()['drafts'][0]
    assert (result['status'] == 'duplicate') == (role == 'pedagogical')
    if role == 'teacher':
        assert result['duplicate_reason'] is None
        # Own uploads still participate in duplicate detection.
        again = client.post('/kine/case-imports', data={
            'documents': (io.BytesIO(content), 'private-source.docx')}, headers={'Accept': 'application/json'})
        assert again.get_json()['drafts'][0]['status'] == 'duplicate'


def test_private_draft_content_is_not_a_duplicate_oracle(app, population):
    with app.app_context():
        other = db.session.get(KineCaseDraft, population['draft'])
        other.extracted_data = {'case_number': 'UNPUBLISHED-SECRET', 'title': 'Private draft title'}
        own = KineCaseDraft(batch=KineCaseImportBatch(created_by=1), created_by=1,
            source_filename='own.docx', source_path='unused', source_sha256='c' * 64)
        db.session.add(own)
        db.session.commit()
        own_id = own.id
    client = as_role(app, population, 'teacher')
    response = client.patch(f'/kine/case-import-drafts/{own_id}', json={
        'extracted_data': {'case_number': 'UNPUBLISHED-SECRET', 'title': 'Private draft title'}})
    assert response.status_code == 200
    assert response.get_json()['duplicate_reason'] is None


@pytest.fixture()
def mixed_history(app, population):
    with app.app_context():
        teacher = Teacher(name='Standard only', email='mixed@example.test', ecos_type='standard', password_hash='x')
        rows = [StudentPerformance(student_id=population['standard'], case_number=case,
            percentage_score=score, points_earned=1, points_total=1,
            evaluation_results_json='{"marker":"' + marker + '"}',
            conversation_transcript_json='[{"role":"human","content":"' + marker + '"}]')
            for case, score, marker in [('PERM-KINE', 97, 'PRIVATE-LEGACY-KINE'),
                                        ('PERM-STANDARD', 25, 'PUBLIC-STANDARD')]]
        db.session.add_all([teacher, *rows])
        db.session.commit()
        return {'teacher': teacher.id, 'private': rows[0].id}


@pytest.mark.parametrize('role', ['technical', 'standard_teacher'])
@pytest.mark.parametrize('surface', ['collection', 'detail', 'pdf'])
def test_standard_views_exclude_legacy_kine_results(app, population, mixed_history, role, surface):
    client = app.test_client()
    if role == 'standard_teacher':
        teacher_login(client, mixed_history['teacher'])
        paths = {'collection': '/teacher/students/performance',
                 'detail': f'/teacher/students/{population["standard"]}/detailed_performance',
                 'pdf': f'/teacher/download_student_report/{mixed_history["private"]}'}
    else:
        client = as_role(app, population, 'technical')
        paths = {'collection': '/admin/students',
                 'detail': f'/admin/students/{population["standard"]}/details',
                 'pdf': f'/admin/download_student_report/{mixed_history["private"]}'}
    response = client.get(paths[surface], headers={'Accept': 'application/json'})
    if surface == 'pdf':
        assert response.status_code in (403, 404)
    else:
        assert response.status_code == 200
        data = response.get_json()
        assert 'PERM-KINE' not in response.get_data(as_text=True)
        if surface == 'collection':
            student = next(s for s in data['students'] if s['student_code'] == '900003')
            assert student['average_score'] == 25
        else:
            assert len(data['performances']) == 1
    assert b'PRIVATE-LEGACY-KINE' not in response.data
    with app.app_context():
        assert db.session.get(StudentPerformance, mixed_history['private']).percentage_score == 97


@pytest.mark.parametrize('surface,method', [('patient-record', 'GET'), ('message', 'POST'),
    ('test-request', 'POST'), ('pause', 'POST'), ('resume', 'POST'), ('complete', 'POST'), ('progress', 'POST')])
def test_student_a_cannot_read_or_mutate_b_by_direct_id(app, population, surface, method):
    client = as_role(app, population, 'student_a')
    with app.app_context():
        before = db.session.execute(text('SELECT * FROM simulation_sessions ORDER BY id')).all()
    response = client.open(f'/kine/simulation/{population["sim_b"]}/{surface}', method=method,
        json={'message': 'Forged mutation', 'phase': 2}, headers={'Accept': 'application/json'})
    assert response.status_code == 404
    assert b'PRIVATE-B' not in response.data
    with app.app_context():
        assert db.session.execute(text('SELECT * FROM simulation_sessions ORDER BY id')).all() == before


def test_every_kine_route_refuses_anonymous_data_and_mutations(app, population):
    client = app.test_client()
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith('kine.'):
            continue
        values = {key: 1 for key in rule.arguments}
        path = app.url_map.bind('localhost').build(rule.endpoint, values)
        for method in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
            response = client.open(path, method=method, headers={'Accept': 'application/json'},
                                   **({'json': {}} if method != 'GET' else {}))
            assert response.status_code in (401, 403, 302), (method, path, response.status_code)
            assert b'PRIVATE-' not in response.data


def test_mixed_export_refused_before_any_pdf_generation(app, population, monkeypatch):
    import blueprints.kine.routes_dashboard as routes
    def forbidden(*args, **kwargs):
        pytest.fail('Unauthorized mixed selection generated a file')
    monkeypatch.setattr(routes, 'create_simple_consultation_pdf', forbidden)
    client = as_role(app, population, 'teacher')
    response = client.post('/kine/dashboard/conversations/pdf',
                           json={'session_ids': [population['sim_a'], population['sim_b']]})
    assert response.status_code == 404
    assert b'PRIVATE-' not in response.data


@pytest.mark.parametrize('role', ['teacher', 'pedagogical'])
@pytest.mark.parametrize('surface', ['draft_json', 'draft_html', 'batch_json', 'batch_html'])
def test_stored_duplicate_warning_is_projected_without_changing_private_history(app, population, role, surface):
    warning = f'Correspond au brouillon #{population["draft"]}.'
    with app.app_context():
        own = KineCaseDraft(batch=KineCaseImportBatch(created_by=1), created_by=1,
            source_filename='own.docx', source_path='unused', source_sha256='d' * 64,
            status='duplicate', duplicate_reason=warning, validation_issues=[warning],
            extracted_data={'case_number': 'OWN-DRAFT'})
        db.session.add(own)
        db.session.commit()
        own_id, batch_id = own.id, own.batch_id
    client = as_role(app, population, role)
    path = f'/kine/case-import-drafts/{own_id}' if surface.startswith('draft') else f'/kine/case-imports/{batch_id}'
    response = client.get(path, headers={'Accept': 'application/json' if surface.endswith('json') else 'text/html'})
    assert response.status_code == 200
    assert (warning in response.get_data(as_text=True)) == (role == 'pedagogical')
    with app.app_context():
        own = db.session.get(KineCaseDraft, own_id)
        assert own.duplicate_reason == warning and own.validation_issues == [warning]


@pytest.mark.parametrize('kind', ['csv', 'xlsx'])
def test_same_clock_tick_exports_cannot_overwrite_another_authorized_dataset(monkeypatch, kind):
    import simple_pdf_generator as exports
    from pathlib import Path
    class FrozenClock:
        @staticmethod
        def now():
            return datetime(2020, 1, 1)
    monkeypatch.setattr(exports, 'datetime', FrozenClock)
    generate = exports.export_kine_dashboard_csv if kind == 'csv' else exports.export_kine_dashboard_excel
    first = Path(generate([{'student_name': 'AUTHORIZED-A'}]))
    saved = first.read_bytes()
    second = Path(generate([{'student_name': 'PRIVATE-B'}]))
    assert first != second
    assert first.read_bytes() == saved
