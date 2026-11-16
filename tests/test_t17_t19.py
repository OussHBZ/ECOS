"""Fictitious results only: reporting arithmetic, disclosure, D01 and stale writers."""
import csv
import io
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from flask import Flask
from PyPDF2 import PdfReader
from openpyxl import load_workbook
from test_kine_extension import app, teacher_login, student_login, create_case, publish_and_assign
from test_t13_t16 import setup_attempt, criterion, outcome
from test_kine_permissions import pedagogical_login
from test_teacher_report_regressions import admin_login
from models import db, SimulationSession, Student, Teacher, PatientCase, KineEvaluationChange
from criterion_evaluation import reference, calculate
from kine_reporting import aggregate, duration_minutes
from kine_transitions import claim, TransitionConflict


def reporting_attempt(client, app):
    teacher_login(client)
    folder=client.post('/kine/folders',json={'name':'Rapports fictifs'}).get_json()['id']
    cid=create_case(client,folder,activate=False)
    definitions = [{**criterion('a'), 'title':'Recueil fictif', 'step':'history', 'weight':'2'},
                   {**criterion('b'), 'title':'Décision fictive', 'step':'reasoning', 'weight':'4'},
                   {**criterion('na'), 'title':'NON-APPLICABLE', 'step':'etp', 'weight':'100'}]
    assert client.post(f'/kine/cases/{cid}/criteria',json={'criteria':definitions}).status_code==200
    publish_and_assign(client,cid)
    student_login(client)
    sid=client.post('/kine/simulation/start',json={'case_id':cid}).get_json()['simulation_id']
    with app.app_context():
        s=db.session.get(SimulationSession,sid);s.conversation=[{'role':'human','content':'Ma décision fictive'}];db.session.commit()
    return cid,sid


def save_result(app, sid, states=('correct', 'partial'), pending=False):
    with app.app_context():
        ref=json.loads(db.session.get(SimulationSession,sid).evaluation_reference_json)
    rows = [outcome('a', states[0], omission=False), outcome('b', 'pending' if pending else states[1], omission=True),
            {**outcome('na', 'incorrect'), 'applicable': False}]
    result = calculate(ref, rows)
    result['revision'] = 1
    with app.app_context():
        s = db.session.get(SimulationSession, sid)
        s.status = 'completed'; s.completed_at = datetime.utcnow()
        s.evaluation_results = result
        s.teacher_comments = 'COMMENTAIRE-PRIVE'
        db.session.commit()
    return result


def test_manually_calculated_totals_filters_and_exports(app):
    client = app.test_client(); cid, sid = reporting_attempt(client, app)
    save_result(app, sid)  # 2 + 2 / 6 = 13.33/20; not 0 for absent ETP.
    with app.app_context():
        source = db.session.get(SimulationSession, sid)
        for i, state in enumerate(['completed', 'completed', 'interrupted']):
            copy = SimulationSession(student_id=1, clinical_case_id=cid, case_version_id=source.case_version_id,
                frozen_student_level='licence', student_reference_json=source.student_reference_json,
                evaluation_reference_json=source.evaluation_reference_json, mode='exam' if i == 1 else 'training',
                status=state, started_at=datetime.utcnow()-timedelta(minutes=30),
                completed_at=datetime.utcnow() if state == 'completed' else None)
            db.session.add(copy); db.session.flush()
            if i == 0: final_id=copy.id
            if i == 1: pending_id=copy.id
        db.session.commit()
    save_result(app, final_id, ('incorrect','correct'))  # 0 + 4 / 6 = 13.33
    save_result(app, pending_id, pending=True)
    teacher_login(client)
    result = client.get('/kine/dashboard', headers={'Accept':'application/json'}).get_json()
    assert result['stats']['simulation_count'] == 4
    assert result['stats']['pending_count'] == 1 and result['stats']['scored_count'] == 2
    assert result['stats']['average_score'] == 13.33
    by_step = {r['key']: r for r in result['competencies']}
    assert 'etp' not in by_step
    assert by_step['history']['earned'] == 2 and by_step['history']['possible'] == 4
    assert by_step['reasoning']['earned'] == 6 and by_step['reasoning']['possible'] == 8
    assert by_step['reasoning']['omissions'] == 2 and by_step['reasoning']['provisional'] == 1
    assert by_step['reasoning']['percentage'] == 75
    version = result['sessions'][0]['case_version_id']
    filters=f'mode=training&status=completed&level=licence&student_id=1&version_id={version}&competency=reasoning&criterion=b&result=passed'
    filtered = client.get('/kine/dashboard?'+filters, headers={'Accept':'application/json'}).get_json()
    assert {r['id'] for r in filtered['sessions']} == {sid, final_id}
    exported = client.get('/kine/dashboard/export?format=csv&'+filters)
    csvrows = list(csv.DictReader(io.StringIO(exported.data.decode('utf-8-sig'))))
    assert {int(r['Tentative']) for r in csvrows} == {sid, final_id}
    assert all(len(json.loads(r['Critères évalués'])) == 1 for r in csvrows)
    xlsx = client.get('/kine/dashboard/export?format=xlsx&dataset=criteria&'+filters)
    values=list(load_workbook(io.BytesIO(xlsx.data)).active.values)
    assert len(values) == 3
    assert all(r[values[0].index('Critère')] == 'b' for r in values[1:])
    pending=client.get('/kine/dashboard/export?format=csv&dataset=criteria&result=pending').data.decode('utf-8-sig')
    assert 'À vérifier' in pending
    assert client.get('/kine/dashboard?mode=invalid').status_code == 400
    page=client.get('/kine/dashboard?'+filters).get_data(as_text=True)
    assert 'value="reasoning" selected' in page


def test_personal_reports_and_exam_policy_every_surface(app, tmp_path):
    client=app.test_client();cid,sid=reporting_attempt(client,app)
    save_result(app,sid)
    with app.app_context():
        s=db.session.get(SimulationSession,sid);s.mode='exam';db.session.commit()
    for path in [f'/kine/simulation/{sid}/evaluation', f'/kine/simulation/{sid}/chat',
                 f'/kine/simulation/{sid}/timeline', '/kine/history', '/kine/history?format=json']:
        response=client.get(path)
        assert response.status_code==200, path
        assert b'PREUVE-PRIVEE' not in response.data and b'COMMENTAIRE-PRIVE' not in response.data
        assert b'ATTENTE-PRIVEE' not in response.data and b'configured_safety' not in response.data
    score_pdf=client.get(f'/kine/simulation/{sid}/pdf')
    text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(score_pdf.data)).pages)
    assert '13.33' in text and 'PREUVE-PRIVEE' not in text and 'publication' in text
    teacher_login(client)
    assert client.post(f'/kine/dashboard/simulation/{sid}/feedback-publication',json={'revision':1}).status_code==200
    teacher_pdf=client.get(f'/kine/dashboard/simulation/{sid}/pdf')
    assert teacher_pdf.status_code==200
    student_login(client)
    published=client.get(f'/kine/simulation/{sid}/pdf')
    text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(published.data)).pages)
    assert 'PREUVE-PRIVEE' in text and 'COMMENTAIRE-PRIVE' in text and 'NON-APPLICABLE' not in text
    assert 'configured_safety' not in text
    history=client.get('/kine/history', headers={'Accept':'application/json'}).get_json()
    assert len(history['report']['competencies'])==2
    # Save representative outputs and real rendered HTML under the isolated run only.
    artifacts=Path.cwd().parent/'visual-t17-t19';artifacts.mkdir(exist_ok=True)
    for name,response in [('score-only.pdf',score_pdf),('personal.pdf',published),('teacher.pdf',teacher_pdf)]:
        (artifacts/name).write_bytes(response.data)
    (artifacts/'student.html').write_bytes(client.get('/kine/history').data)
    (artifacts/'feedback.html').write_bytes(client.get(f'/kine/simulation/{sid}/chat').data)
    teacher_login(client)
    (artifacts/'teacher.html').write_bytes(client.get('/kine/dashboard').data)
    assert client.post(f'/kine/dashboard/simulation/{sid}/review',json={'teacher_comments':'NOUVEAU-PRIVE'}).status_code==200
    student_login(client)
    assert not client.get('/kine/history', headers={'Accept':'application/json'}).get_json()['report']['competencies']


def test_report_owner_teacher_scope_and_no_technical_admin_access(app):
    client=app.test_client();cid,sid=reporting_attempt(client,app);save_result(app,sid)
    with app.app_context():
        other=Student(student_code='OUTSIDE',name='Outside',ecos_type='kine',level='licence')
        teacher=Teacher(name='Unassigned',email='outside@test.invalid',password_hash='x',ecos_type='kine')
        db.session.add_all([other,teacher]);db.session.commit();oid,tid=other.id,teacher.id
    student_login(client,oid)
    for suffix in ('evaluation','pdf','timeline','chat'):
        assert client.get(f'/kine/simulation/{sid}/{suffix}').status_code==404
    assert client.get('/kine/history', headers={'Accept':'application/json'}).get_json()['sessions']==[]
    for login in [lambda:teacher_login(client,tid), lambda:admin_login(client)]:
        login()
        for suffix in ('','/pdf','/evaluation-history'):
            assert client.get(f'/kine/dashboard/simulation/{sid}{suffix}').status_code in (403,404)
        assert client.post('/kine/dashboard/conversations/pdf',json={'session_ids':[sid]}).status_code in (403,404)
    teacher_login(client,tid)
    assert client.get('/kine/dashboard', headers={'Accept':'application/json'}).get_json()['sessions']==[]
    rows=list(csv.reader(io.StringIO(client.get('/kine/dashboard/export?format=csv').data.decode('utf-8-sig'))))
    assert len(rows)==1
    pedagogical_login(client,app)
    assert client.get(f'/kine/dashboard/simulation/{sid}/pdf').status_code==200


def test_abandon_reconnect_pause_and_completed_preservation(app):
    client=app.test_client();cid,sid=setup_attempt(client,app)
    assert client.post(f'/kine/simulation/{sid}/pause',json={}).status_code==200
    assert client.post(f'/kine/simulation/{sid}/reconnect',json={}).status_code==409
    assert client.post(f'/kine/simulation/{sid}/resume',json={}).status_code==200
    assert client.post(f'/kine/simulation/{sid}/reconnect',json={}).status_code==200
    assert client.post(f'/kine/simulation/{sid}/abandon',json={}).status_code==200
    for action in ('resume','complete','reconnect'):
        assert client.post(f'/kine/simulation/{sid}/{action}',json={}).status_code==409
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.status=='interrupted' and s.evaluation_results is None and s.conversation
        duration=duration_minutes(s)
        assert duration_minutes(s,datetime.utcnow()+timedelta(days=2))==duration
    result=client.post('/kine/simulation/start',json={'case_id':cid})
    new_id=result.get_json()['simulation_id']
    assert client.post(f'/kine/simulation/{new_id}/complete',json={}).status_code==200
    with app.app_context():
        s=db.session.get(SimulationSession,new_id);before=deepcopy(s.evaluation_results);log=deepcopy(s.timeline)
    for action in ('pause','resume','abandon','reconnect'):
        assert client.post(f'/kine/simulation/{new_id}/{action}',json={}).status_code==409
    assert client.post(f'/kine/simulation/{new_id}/complete',json={}).status_code==200
    with app.app_context():
        s=db.session.get(SimulationSession,new_id)
        assert s.evaluation_results==before and s.timeline==log and s.status=='completed'


@pytest.mark.parametrize('abandon', [False, True])
def test_exam_reconnection_deadline_and_no_replacement_attempt(app, monkeypatch, abandon):
    from test_t13_t16 import exam_attempt
    from blueprints.kine import routes_student
    client=app.test_client();sid,end=exam_attempt(client,app)
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        cid,eid=s.clinical_case_id,s.exam_id
        before=s.evaluation_reference_json
    assert client.post(f'/kine/simulation/{sid}/pause',json={}).status_code==409
    assert client.post(f'/kine/simulation/{sid}/reconnect',json={}).get_json()['deadline']==end.isoformat()+'Z'
    if abandon:
        assert client.post(f'/kine/simulation/{sid}/abandon',json={}).status_code==200
    class Clock(datetime):
        @classmethod
        def utcnow(cls):return end
    monkeypatch.setattr(routes_student,'datetime',Clock)
    assert client.post(f'/kine/simulation/{sid}/reconnect',json={}).status_code==409
    assert client.post('/kine/simulation/start',json={'case_id':cid,'exam_id':eid,'mode':'exam'}).status_code==409
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.evaluation_reference_json==before and s.total_paused_seconds==0
        assert s.status==('interrupted' if abandon else 'completed')
        assert (s.evaluation_results is None)==abandon


def test_legacy_projection_rejects_configuration_without_rewriting_results(app):
    from evaluation_lifecycle import student_result
    client=app.test_client();cid,sid=setup_attempt(client,app)
    legacy={'points_earned':14, 'passed':True, 'teacher_correction':'PRIVATE-CONFIG',
            'section_scores':[{'title':'Historique','justification':'Feedback conservé','configuration':'PRIVATE-CONFIG'}]}
    with app.app_context():
        s=db.session.get(SimulationSession,sid);s.status='completed';s.evaluation_results=legacy;db.session.commit()
        public=student_result(s)
        assert 'PRIVATE-CONFIG' not in json.dumps(public)
        assert public['section_scores'][0]['justification']=='Feedback conservé'
        assert s.evaluation_results==legacy


def test_teacher_pdf_keeps_long_conversation_and_escapes_markup(app):
    client=app.test_client();cid,sid=reporting_attempt(client,app);save_result(app,sid)
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        s.conversation=[{'role':'human','content':('Échange fictif conservé. '*400)+'<fin> DERNIERE-PHRASE'}]
        db.session.commit()
    teacher_login(client)
    response=client.get(f'/kine/dashboard/simulation/{sid}/pdf')
    assert response.status_code==200
    text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(response.data)).pages)
    assert 'DERNIERE-PHRASE' in text and '<fin>' in text
    # PDF line/page breaks can split phrases; every original token must survive.
    dialogue=text.split('Dialogue de la consultation',1)[1].split('Nombre total de messages:',1)[0]
    for token in ('Échange', 'fictif', 'conservé.'):
        assert dialogue.split().count(token)==400
    artifacts=Path.cwd().parent/'visual-t17-t19'
    artifacts.mkdir(exist_ok=True)
    (artifacts/'long-conversation.pdf').write_bytes(response.data)


@pytest.mark.parametrize('terminal', ['completed', 'interrupted'])
def test_late_patient_response_cannot_modify_closed_attempt(app, monkeypatch, terminal):
    from blueprints.kine import routes_student
    client=app.test_client();cid,sid=setup_attempt(client,app)
    saved={}
    def respond(*args, **kwargs):
        # A second transaction closes the attempt while the first waits for the patient.
        with app.app_context():
            other=db.session.get(SimulationSession,sid)
            if terminal=='completed':
                routes_student._complete_simulation(other)
            else:
                claim(other,('in_progress',),'interrupted')
                other.runtime_state={**other.runtime_state,'interrupted_at':datetime.utcnow().isoformat()}
                db.session.commit()
            saved.update(conversation=deepcopy(other.conversation), timeline=deepcopy(other.timeline),
                         evaluation=deepcopy(other.evaluation_results), runtime=deepcopy(other.runtime_state))
        return {'content':'RÉPONSE-TARDIVE','type':'patient_response'}
    monkeypatch.setattr(routes_student.KinePatientEngine,'respond',respond)
    response=client.post(f'/kine/simulation/{sid}/message',json={'message':'Bonjour, comment vous sentez-vous ?'})
    assert response.status_code==409
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.status==terminal and s.conversation==saved['conversation']
        assert s.timeline==saved['timeline'] and s.runtime_state==saved['runtime']
        assert s.evaluation_results==saved['evaluation']


@pytest.mark.parametrize('interruption', ['paused','interrupted','completed'])
def test_real_concurrent_completion_and_interruption(tmp_path, interruption):
    application=Flask('race')
    application.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///'+str(tmp_path/'race.db'), GROQ_CLIENT=None)
    db.init_app(application)
    with application.app_context():
        db.create_all()
        student=Student(student_code='RACE',name='Race',ecos_type='kine',level='licence')
        case=PatientCase(case_number='RACE',specialty='kine',level='both')
        db.session.add_all([student,case]);db.session.flush()
        attempt=SimulationSession(student_id=student.id,clinical_case_id=case.id,status='in_progress')
        db.session.add(attempt);db.session.commit();sid=attempt.id
    barrier=Barrier(2)
    def worker(action):
        with application.app_context():
            s=db.session.get(SimulationSession,sid);barrier.wait(timeout=10)
            try:
                if action=='completed':
                    from blueprints.kine.routes_student import _complete_simulation
                    _complete_simulation(s)
                else:
                    claim(s,('in_progress',),action);db.session.commit()
                return 'ok'
            except TransitionConflict:
                db.session.rollback();return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,a) for a in ('completed',interruption)]
        outcomes=[f.result(timeout=20) for f in futures]
    assert 'ok' in outcomes
    with application.app_context():
        s=db.session.get(SimulationSession,sid)
        assert SimulationSession.query.count()==1
        if s.status=='completed':
            assert s.evaluation_results and KineEvaluationChange.query.count()==1
        else:
            assert s.status==interruption and s.evaluation_results is None
            assert KineEvaluationChange.query.count()==0
