"""Final milestone: fictitious data, actual routes/factory, no external service."""
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
from PyPDF2 import PdfReader
from test_kine_extension import app, teacher_login, student_login, BrowserTestClient, create_case, publish_and_assign
from test_t13_t16 import setup_attempt
from models import db, Student, Teacher, TeacherStudentScope, SimulationSession, KineEvaluationChange


class Patient:
    def invoke(self, *args, **kwargs):
        return SimpleNamespace(content='Je vous écoute.', response_metadata={})


def test_kardiox_transport_budget_and_no_sdk_retry(monkeypatch):
    import app as factory
    configured=[];calls=[]
    class Transport:
        def __init__(self,**kwargs):configured.append(kwargs)
        def invoke(self,*a,**k):calls.append(1);raise TimeoutError('PRIVATE-PROVIDER-BODY')
    monkeypatch.setattr(factory,'ChatGroq',Transport)
    client=factory.FallbackGroqClient('fake',None,['fictitious'],{'temperature':0,'max_tokens':100,'timeout':10,'max_retries':0})
    with pytest.raises(TimeoutError):client.invoke([])
    assert len(calls)==1 and configured[0]['timeout']==10 and configured[0]['max_retries']==0


def test_extraction_logs_do_not_contain_response(caplog):
    from document_processor import DocumentExtractionAgent
    agent=DocumentExtractionAgent(SimpleNamespace(invoke=lambda *a:SimpleNamespace(content='{PRIVATE-CLINICAL-BODY invalid json}')))
    agent.state={'raw_text':'FICTITIOUS DOCUMENT','images':[]}
    agent._is_physio_case=lambda:True
    caplog.set_level('DEBUG',logger='document_processor')
    with pytest.raises(RuntimeError):agent._extract_structured_data_with_llm()
    assert 'PRIVATE-CLINICAL-BODY' not in caplog.text


def test_measurement_retries_preserve_one_observation(app):
    from test_t06_t08 import fixture_case, start
    c=app.test_client();cid,_=fixture_case(c);sid=start(c,cid)
    for teacher in (False,True):
        if teacher:teacher_login(c)
        url=f'/kine/teacher/simulation/{sid}/effort-measurement' if teacher else f'/kine/simulation/{sid}/effort-tests'
        body={'test_id':'walk','measurement_id':'observer' if teacher else 'fc-start',
              'observed_value':'FICTITIOUS','request_id':'teacher' if teacher else 'student'}
        first=c.post(url,json=body);assert first.status_code==200,first.text
        replay=c.post(url,json=body);assert replay.status_code==200 and replay.json['replayed']
        assert replay.json['measurement']==first.json['measurement']
        assert c.post(url,json={**body,'observed_value':'CHANGED'}).status_code==400
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert len(s.runtime_state['effort_measurements'])==2
        assert sum(e['action']=='effort_measurement' for e in s.timeline)==2


def test_retry_keeps_original_phase_and_prior_context(app,monkeypatch):
    from blueprints.kine import routes_student
    c=app.test_client();cid,sid=setup_attempt(c,app)
    monkeypatch.setattr(routes_student,'matching_question_information',lambda *a,**k:None)
    seen=[]
    def respond(self,message,phase,history):
        seen.append((message,phase,[r['content'] for r in history]))
        if len(seen)==1:raise TimeoutError()
        return {'type':'patient_response','content':'Réponse fictive.'}
    monkeypatch.setattr(routes_student.KinePatientEngine,'respond',respond)
    url=f'/kine/simulation/{sid}/message'
    old={'message':'Original','request_id':'original'}
    assert c.post(url,json=old).status_code==503
    assert c.post(f'/kine/simulation/{sid}/progress',json={'phase':7}).status_code==200
    assert c.post(url,json={'message':'Later','request_id':'later'}).status_code==200
    assert c.post(url,json=old).status_code==200
    assert seen[0]==seen[2] and seen[1][1]==7
    with app.app_context():
        rows=db.session.get(SimulationSession,sid).conversation
        assert sum(r.get('request_id')=='original' and r['role']=='human' for r in rows)==1
        assert sum(r.get('request_id')=='later' for r in rows)==2


@pytest.mark.parametrize('failure', ['missing', 'timeout', 'unavailable', 'empty', 'null', 'object'])
def test_outage_saved_message_retry_no_duplicate(app, monkeypatch, failure):
    client=app.test_client(); cid,sid=setup_attempt(client,app)
    from blueprints.kine import routes_student
    monkeypatch.setattr(routes_student, 'matching_question_information', lambda *a, **k: None)
    class Broken:
        def invoke(self, *a, **k):
            if failure in ('timeout','unavailable'):
                raise TimeoutError('PRIVATE-PROVIDER-BODY')
            return SimpleNamespace(content={'empty':'', 'null':None, 'object':{}}[failure])
    app.config['GROQ_CLIENT']=None if failure=='missing' else Broken()
    url=f'/kine/simulation/{sid}/message'; body={'message':'Bonjour, comment allez-vous ?', 'request_id':'delivery-1'}
    r=client.post(url,json=body)
    assert r.status_code==503, r.get_data(as_text=True)
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert len([m for m in s.conversation if m.get('request_id')=='delivery-1'])==1
        assert s.evaluation_results is None
    assert client.get(f'/kine/simulation/{sid}/chat').status_code==200
    app.config['GROQ_CLIENT']=Patient()
    first=client.post(url,json=body); assert first.status_code==200,first.get_data(as_text=True)
    second=client.post(url,json=body); assert second.status_code==200 and second.json['replayed']
    assert first.json['response']==second.json['response']
    assert client.post(url,json={**body,'message':'Different payload'}).status_code==400
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert [m['role'] for m in s.conversation if m.get('request_id')=='delivery-1']==['human','assistant']
        assert sum(e.get('action')=='student_message' for e in s.timeline)==1


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    import app as factory
    monkeypatch.setenv('GROQ_API_KEY','fictional-not-a-secret')
    monkeypatch.setenv('SECRET_KEY','fictional-isolated-session-key')
    monkeypatch.setenv('SEED_DEMO_ACCOUNTS','false')
    monkeypatch.setattr(factory,'load_dotenv',lambda:None)
    monkeypatch.setattr(factory,'create_groq_client',lambda *a:(Patient(),'simulated'))
    monkeypatch.setattr(factory,'FallbackGroqClient',lambda *a,**k:Patient())
    original=factory.Flask
    def isolated_flask(*args,**kwargs):
        return original(*args,instance_path=str(tmp_path/'instance'),**kwargs)
    monkeypatch.setattr(factory,'Flask',isolated_flask)
    application=factory.create_app()
    application.config.update(TESTING=True, KINE_QUESTION_ROUTER=None)
    application.test_client_class=BrowserTestClient
    with application.app_context():
        teacher=Teacher(email='teacher@example.test',name='Teacher',password_hash='x',ecos_type='kine')
        student=Student(student_code='123456',name='Student',level='licence',ecos_type='kine')
        db.session.add_all([teacher,student]);db.session.flush()
        assert teacher.id==student.id==1
        db.session.add(TeacherStudentScope(teacher_id=teacher.id,student_id=student.id));db.session.commit()
    yield application
    with application.app_context():
        db.session.remove(); db.engine.dispose()


def test_factory_standard_and_kardiox_branding(integrated):
    client=integrated.test_client()
    for path in ('/','/login','/login?workspace=kine'):
        r=client.get(path,follow_redirects=True)
        assert r.status_code==200,(path,r.status_code)
    cid,sid=setup_attempt(client,integrated)
    for path in ('/kine/student','/kine/history',f'/kine/simulation/{sid}/chat'):
        r=client.get(path);assert r.status_code==200
        assert 'KardioX' in r.text and 'Simuler. Raisonner. Rééduquer.' in r.text
    teacher_login(client)
    assert client.get('/kine/dashboard').status_code==200


@pytest.mark.parametrize('different_case', [False, True])
def test_concurrent_students_and_single_closure(integrated, monkeypatch, different_case):
    app=integrated; client=app.test_client(); cid,sid=setup_attempt(client,app)
    from blueprints.kine import routes_student
    monkeypatch.setattr(routes_student,'matching_question_information',lambda *a,**k:None)
    from test_t09_t12 import new_case
    second_cid=new_case(client,number='LOAD-SECOND') if different_case else cid
    if different_case:
        second_version=publish_and_assign(client,second_cid)['id']
    count=8
    with app.app_context():
        source=db.session.get(SimulationSession,sid)
        ids=[(1,sid)]
        for n in range(2,count+1):
            student=Student(student_code=f'LOAD-{n}',name=f'Fictitious {n}',ecos_type='kine',level='licence')
            db.session.add(student);db.session.flush()
            alternate=different_case and n%2==0
            attempt=SimulationSession(student_id=student.id,clinical_case_id=second_cid if alternate else cid,status='in_progress',mode='training',
                case_version_id=second_version if alternate else source.case_version_id, student_reference_json=source.student_reference_json,
                evaluation_reference_json=source.evaluation_reference_json, frozen_student_level=source.frozen_student_level)
            db.session.add(attempt);db.session.flush();ids.append((student.id,attempt.id))
        db.session.commit()
    barrier=Barrier(count)
    def worker(pair):
        uid,attempt=pair; c=app.test_client();student_login(c,uid)
        barrier.wait(timeout=20); start=time.perf_counter()
        body={'message':f'Bonjour, je suis étudiant {uid}.','request_id':f'load-{uid}'}
        r=c.post(f'/kine/simulation/{attempt}/message',json=body)
        assert r.status_code==200,r.get_data(as_text=True)
        assert c.post(f'/kine/simulation/{attempt}/message',json=body).json['replayed']
        assert c.get(f'/kine/simulation/{ids[(uid)%count][1]}/chat').status_code==404
        return time.perf_counter()-start
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=count) as pool:
        timings=list(pool.map(worker,ids))
    elapsed=time.perf_counter()-start
    barrier=Barrier(count)
    def close(_):
        c=app.test_client(); student_login(c);barrier.wait(timeout=20)
        return c.post(f'/kine/simulation/{sid}/complete',json={}).status_code
    with ThreadPoolExecutor(max_workers=count) as pool:
        closes=list(pool.map(close,range(count)))
    assert set(closes)<={200,409} and 200 in closes,closes
    with app.app_context():
        for uid,attempt in ids:
            rows=db.session.get(SimulationSession,attempt).conversation
            delivered=[m for m in rows if m.get('request_id')==f'load-{uid}']
            assert [m['role'] for m in delivered]==['human','assistant']
            assert all(m.get('request_id') in (None,f'load-{uid}') for m in rows)
        assert KineEvaluationChange.query.filter_by(simulation_id=sid).count()==1
    proof=Path.cwd().parent/f'load-t20-t22-{different_case}.json'
    proof.write_text(json.dumps({'concurrent_clients':count,'rounds':1,'provider':'simulated',
        'database':'temporary SQLite','message_and_replay_seconds':timings,'wall_seconds':elapsed,
        'concurrent_close_statuses':closes},indent=2),encoding='utf-8')


def test_pending_duplicate_and_concurrent_update(integrated, monkeypatch):
    app=integrated;c=app.test_client();cid,sid=setup_attempt(c,app)
    from blueprints.kine import routes_student
    monkeypatch.setattr(routes_student,'matching_question_information',lambda *a,**k:None)
    entered=Event();release=Event()
    def slow(*args,**kwargs):
        entered.set();assert release.wait(15)
        return {'type':'patient_response','content':'Réponse tardive fictive.'}
    monkeypatch.setattr(routes_student.KinePatientEngine,'respond',slow)
    body={'message':'Bonjour','request_id':'parallel'};url=f'/kine/simulation/{sid}/message'
    def send():
        c=app.test_client();student_login(c);return c.post(url,json=body).status_code
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(send);assert entered.wait(15)
        try:
            assert c.post(url,json=body).status_code==409
            assert c.post(url,json={**body,'request_id':'different'}).status_code==409
            # Another independent update must never be overwritten by the old
            # response, even when the ORM reloads expired objects after commit.
            with app.app_context():
                s=db.session.get(SimulationSession,sid)
                s.runtime_state={**s.runtime_state,'concurrent_marker':'KEEP'};db.session.commit()
        finally:release.set()
        assert future.result(timeout=15)==409
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.runtime_state['concurrent_marker']=='KEEP'
        assert len([m for m in s.conversation if m.get('request_id')=='parallel'])==1
        state=dict(s.runtime_state);state['message_delivery']={**state['message_delivery'],
            'started_at':(datetime.utcnow()-timedelta(seconds=301)).isoformat()};s.runtime_state=state;db.session.commit()
    assert c.post(url,json=body).status_code==200
    with app.app_context():
        assert len([m for m in db.session.get(SimulationSession,sid).conversation if m.get('request_id')=='parallel'])==2


def test_eight_concurrent_exam_closures(integrated):
    from test_t13_t16 import exam_attempt
    c=integrated.test_client();sid,deadline=exam_attempt(c,integrated)
    barrier=Barrier(8)
    def close(_):
        client=integrated.test_client();student_login(client)
        barrier.wait(timeout=20)
        return client.post(f'/kine/simulation/{sid}/complete',json={}).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses=list(pool.map(close,range(8)))
    assert 200 in statuses and set(statuses)<={200,409},statuses
    with integrated.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.mode=='exam' and s.status=='completed'
        assert KineEvaluationChange.query.filter_by(simulation_id=sid).count()==1
        assert sum(e['action']=='simulation_completed' for e in s.timeline)==1
    (Path.cwd().parent/'exam-closure-t20-t22.json').write_text(json.dumps({'concurrent_requests':8,'statuses':statuses,'closures':1}),encoding='utf-8')


@pytest.mark.parametrize('level', ['licence','master'])
@pytest.mark.parametrize('mode', ['training','exam'])
@pytest.mark.parametrize('incident', [False,True])
def test_integrated_journey_versions_review_pdf(integrated, level, mode, incident):
    from test_t09_t12 import new_case, program
    from test_t13_t16 import criterion
    from models import PatientCase
    app=integrated;c=app.test_client();p=program()
    if not incident:p['session']['events']=[]
    cid=new_case(c,value=p)
    assert c.post(f'/kine/cases/{cid}/criteria',json={'criteria':[criterion()]}).status_code==200
    v1=publish_and_assign(c,cid)
    with app.app_context():
        db.session.get(Student,1).level=level;db.session.commit()
    start={'case_id':cid,'mode':mode}
    if mode=='exam':
        now=datetime.utcnow()
        r=c.post('/kine/exams',json={'name':'Recette intégrée','start_at':(now-timedelta(minutes=1)).isoformat(),
            'end_at':(now+timedelta(minutes=10)).isoformat(),'max_duration_minutes':8,
            'case_version_ids':[v1['id']],'student_ids':[1]})
        assert r.status_code==201,r.text
        start['exam_id']=r.json['id']
    student_login(c);r=c.post('/kine/simulation/start',json=start)
    assert r.status_code==201,r.text
    sid=r.json['simulation_id']
    teacher_login(c)
    changed=criterion();changed['expected']='V2-PRIVATE'
    assert c.post(f'/kine/cases/{cid}/criteria',json={'criteria':[changed]}).status_code==200
    v2=publish_and_assign(c,cid);assert v2['id']!=v1['id']
    student_login(c)
    assert c.post(f'/kine/simulation/{sid}/progress',json={'phase':7}).status_code==200
    body={'message':'incident','request_id':'scenario'}
    r=c.post(f'/kine/simulation/{sid}/message',json=body)
    assert r.status_code==200,r.text
    events=r.json['response'].get('events',[])
    assert any(e['kind']=='incident' for e in events)==(incident and level=='master')
    assert c.post(f'/kine/simulation/{sid}/message',json=body).json['replayed']
    action={'action':'continuer','exercise_name':'Vélo fictif','request_id':'action-1'}
    r=c.post(f'/kine/simulation/{sid}/session-action',json=action);assert r.status_code==200,r.text
    replay=c.post(f'/kine/simulation/{sid}/session-action',json=action)
    assert replay.status_code==200 and replay.json['replayed']
    visual=Path.cwd().parent/'visual-t20-t22';visual.mkdir(exist_ok=True)
    prefix=f'{level}-{mode}-{incident}'
    (visual/f'{prefix}-chat.html').write_bytes(c.get(f'/kine/simulation/{sid}/chat').data)
    r=c.post(f'/kine/simulation/{sid}/complete',json={});assert r.status_code==200,r.text
    assert r.json['evaluation']['result_status']=='pending'
    teacher_login(c)
    review={'criterion_id':'c1','status':'acceptable','reason':'Contrôle fictif de recette','revision':1,'evidence_message_ids':['message_1']}
    r=c.post(f'/kine/dashboard/simulation/{sid}/classification',json=review)
    assert r.status_code==200,r.text
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.case_version_id==v1['id'] and s.frozen_student_level==level
        assert s.evaluation_results['points_earned']==20
    student_login(c)
    before=c.get(f'/kine/simulation/{sid}/pdf');assert before.status_code==200
    text=''.join(page.extract_text() for page in PdfReader(io.BytesIO(before.data)).pages)
    assert ('ATTENDU-PRIVE' in text)==(mode=='training')
    teacher_login(c)
    assert c.post(f'/kine/dashboard/simulation/{sid}/feedback-publication',json={'revision':2}).status_code==200
    (visual/f'{prefix}-teacher.html').write_bytes(c.get('/kine/dashboard').data)
    teacher_pdf=c.get(f'/kine/dashboard/simulation/{sid}/pdf');assert teacher_pdf.status_code==200
    (visual/f'{prefix}-teacher.pdf').write_bytes(teacher_pdf.data)
    student_login(c)
    r=c.get(f'/kine/simulation/{sid}/pdf');assert r.status_code==200
    text=''.join(page.extract_text() for page in PdfReader(io.BytesIO(r.data)).pages)
    assert all(word in text for word in ('KardioX','Simuler. Raisonner. Rééduquer.','ATTENDU-PRIVE'))
    (visual/f'{prefix}-personal.pdf').write_bytes(r.data)
    (visual/f'{prefix}-history.html').write_bytes(c.get('/kine/history').data)
    (visual/f'{prefix}-feedback.html').write_bytes(c.get(f'/kine/simulation/{sid}/chat').data)


def test_backup_restore_database_documents_and_refusals(integrated,tmp_path,monkeypatch):
    from scripts.backup_restore import backup,restore,DATABASE
    import sqlite3,zipfile
    app=integrated;c=app.test_client();cid,sid=setup_attempt(c,app)
    assert c.post(f'/kine/simulation/{sid}/complete',json={}).status_code==200
    root=Path(app.instance_path).parent
    app.config['UPLOAD_FOLDER']=str(root/'uploads')
    teacher_login(c)
    folder=c.post('/kine/folders',json={'name':'Restauration fictive'}).json['id']
    uploaded=c.post('/kine/cases',data={'case_number':'RESTORE-DOC','folder_id':str(folder),
        'title':'Original fictif','level':'both','mode_availability':'both',
        'documents':(io.BytesIO(b'FICTITIOUS ORIGINAL DOCUMENT'),'original.pdf')},headers={'Accept':'application/json'})
    assert uploaded.status_code==201,uploaded.text
    from models import KineCaseDocument
    with app.app_context():
        stored=KineCaseDocument.query.filter_by(clinical_case_id=uploaded.json['id']).one()
        original_route=f'/kine/cases/{stored.clinical_case_id}/documents/{stored.stable_id}'
    assert c.get(original_route).data==b'FICTITIOUS ORIGINAL DOCUMENT'
    document=root/'uploads/clinical/source.txt';document.parent.mkdir(parents=True);document.write_text('SOURCE FICTIVE',encoding='utf-8')
    image=root/'static/images/cases/fictitious.bin';image.parent.mkdir(parents=True);image.write_bytes(b'\x00\x01document')
    archive=tmp_path.parent/(tmp_path.name+'-backup.zip')
    with pytest.raises(ValueError):backup(root,archive)
    manifest=backup(root,archive,quiesced=True)
    destination=tmp_path.parent/(tmp_path.name+'-restored')
    assert restore(archive,destination)==manifest
    assert (destination/document.relative_to(root)).read_bytes()==document.read_bytes()
    assert (destination/image.relative_to(root)).read_bytes()==image.read_bytes()
    # Start the actual factory on the restored DB, in a new instance directory;
    # never rewrite old file paths inside immutable clinical versions.
    import app as factory
    from flask import Flask
    monkeypatch.setattr(factory,'Flask',lambda *a,**k:Flask(*a,instance_path=str(destination/'instance'),**k))
    restored_app=factory.create_app()
    restored_app.config.update(TESTING=True,UPLOAD_FOLDER=str(destination/'uploads'),KINE_RESTORED_UPLOAD_ROOT=str(root/'uploads'))
    restored_app.test_client_class=BrowserTestClient
    restored_client=restored_app.test_client();teacher_login(restored_client)
    assert restored_client.get(original_route).data==b'FICTITIOUS ORIGINAL DOCUMENT'
    student_login(restored_client)
    assert restored_client.get(f'/kine/simulation/{sid}/pdf').status_code==200
    with sqlite3.connect(root/DATABASE) as before,sqlite3.connect(destination/DATABASE) as after:
        for table in ('student','simulation_sessions','kine_case_versions','kine_case_documents','kine_evaluation_changes','schema_migrations'):
            assert before.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()==after.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
    with pytest.raises(ValueError):restore(archive,destination)
    corrupted=tmp_path.parent/(tmp_path.name+'-corrupt.zip')
    with zipfile.ZipFile(archive) as src,zipfile.ZipFile(corrupted,'w') as dst:
        for name in src.namelist():dst.writestr(name,b'corrupt' if name==DATABASE else src.read(name))
    with pytest.raises(ValueError,match='checksum'):restore(corrupted,tmp_path/'must-not-exist')
    assert not (tmp_path/'must-not-exist').exists()
