"""Role-aware presentation checks against real routes and isolated fixture data."""
import pytest
from flask import render_template
from lxml import html
from test_kine_extension import app, teacher_login, student_login
from test_t06_t08 import fixture_case, start
from models import db, Student, Teacher


def shell(response):
    assert response.status_code == 200
    page = html.fromstring(response.data)
    assert len(page.xpath('//*[@id="main-content"]')) == 1
    assert len(page.xpath('//*[@id="app-navigation"]')) == 1
    assert len(page.xpath('//script[contains(@src,"app-shell.js")]')) == 1
    assert len(page.xpath('//script[contains(@src,"security.js")]')) == 1
    assert page.xpath('//link[contains(@href,"css/app.css")]')
    assert page.xpath('//button[@data-menu-open][@aria-controls="app-navigation"]')
    assert page.xpath('//button[@data-menu-close][text()="Fermer"]')
    assert not page.xpath('//*[@aria-label="Navigation principale"]//*[self::svg or self::i]')
    return page


@pytest.mark.parametrize('path', [
    '/kine/dashboard', '/kine/cases/new', '/kine/cases/1',
    '/kine/case-imports', '/kine/cases/1/criteria', '/kine/cases/1/aids',
    '/kine/cases/1/rehabilitation', '/kine/cases/1/incidents',
    '/kine/cases/1/etp', '/kine/etp', '/kine/cases/1/patient-preview',
])
def test_teacher_secondary_pages_share_shell_and_dependencies(app, path):
    client = app.test_client()
    fixture_case(client)
    page = shell(client.get(path))
    assert page.xpath('//a[contains(@href,"/kine/cases/new")]')
    assert len(page.xpath('//script[contains(@src,"kine-components.js")]')) == 1
    assert len(page.xpath('//script[contains(@src,"kine-delivery.js")]')) == 1


@pytest.mark.parametrize('path', ['/kine/student', '/kine/history', '/kine/cases/1/patient-record', '/kine/simulation/1/chat', '/kine/simulation/1/timeline'])
def test_student_shell_has_only_student_destinations_and_preserves_visibility(app, path):
    client = app.test_client()
    cid, _ = fixture_case(client)
    start(client, cid)
    page = shell(client.get(path))
    links = page.xpath('//*[@aria-label="Navigation principale"]//a/@href')
    assert any('/kine/history' in link for link in links)
    assert not any('/dashboard' in link or '/cases/new' in link or '/admin' in link or '/case-imports' in link for link in links)
    assert b'EXPECTED-SECRET' not in client.get(path).data
    assert b'THRESHOLD-SECRET' not in client.get(path).data


def test_technical_admin_navigation_does_not_expose_pedagogy(app):
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(user_type='admin', admin_authenticated=True)
    page = shell(client.get('/admin/'))
    assert len(page.xpath('//*[@data-app-tab]')) == 5
    assert not page.xpath('//*[@aria-label="Navigation principale"]//a[contains(@href,"/kine/")]')


def test_standard_teacher_navigation_preserves_existing_tabs(app):
    client = app.test_client()
    with app.app_context():
        db.session.get(Teacher,1).ecos_type='standard'
        db.session.commit()
    teacher_login(client)
    page = shell(client.get('/teacher/'))
    assert page.xpath('//*[@data-app-tab]/@data-app-tab') == ['create-cases-tab','stations-management-tab','student-performance-tab']
    assert not page.xpath('//*[@aria-label="Navigation principale"]//a[contains(@href,"/kine/")]')


def test_standard_student_navigation_preserves_existing_tabs(app):
    from blueprints.student import student_bp
    app.register_blueprint(student_bp, url_prefix='/student')
    with app.app_context():
        db.session.get(Student,1).ecos_type='standard'
        db.session.commit()
    client=app.test_client()
    student_login(client)
    page=shell(client.get('/student/'))
    assert page.xpath('//*[@data-app-tab]/@data-app-tab') == ['practice-tab','competition-tab','stats-tab']


def test_public_pages_and_all_templates_compile(app):
    for name in app.jinja_env.list_templates():
        app.jinja_env.get_template(name)
    for name in ('home.html','login.html','error.html'):
        with app.test_request_context('/login'):
            page=html.fromstring(render_template(name,workspace='kine',code=404))
            assert page.xpath('//link[contains(@href,"css/app.css")]')
            assert not page.xpath('//*[@id="app-navigation"]')
            assert page.xpath('//html[@lang="fr"]') or page.tag=='html'
