"""T13–T16: synthetic criteria, exact scores, disclosure and review boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from test_kine_extension import app, teacher_login, student_login, publish_and_assign, create_case
from models import db, PatientCase, SimulationSession, KineEvaluationChange, Student, Exam, Teacher
from criterion_evaluation import normalize_criteria, reference, calculate, evaluate


def criterion(cid='c1', **overrides):
    return dict(id=cid, title='Critère fictif', expected='ATTENDU-PRIVE', alternatives=['ALTERNATIVE-PRIVEE'],
                step='history', type='information_gathering', active=True, teacher_approved=True, weight='1', **overrides)


def outcome(cid='c1', status='correct', **extra):
    return dict(id=cid, status=status, applicable=True, justification='PREUVE-PRIVEE', evidence=[], **extra)


@pytest.mark.parametrize('status,factor', [('correct',1),('acceptable',1),('partial',.5),('incorrect',0),('dangerous',0)])
def test_coefficients(status, factor):
    result = calculate(reference([criterion()], 'licence'), [outcome(status=status)])
    assert result['points_earned'] == 20*factor


@pytest.mark.parametrize('level,threshold', [('licence',12),('master',14)])
def test_exact_boundaries_and_rounding(level, threshold):
    for earned in [Fraction(threshold,20), Fraction(threshold,20)-Fraction(1,100000), Fraction(threshold,20)+Fraction(1,100000)]:
        a=criterion(); a['weight']=str(earned)
        b=criterion('c2'); b['weight']=str(1-earned)
        r=calculate(reference([a,b],level),[outcome(),outcome('c2','incorrect')])
        assert r['passed'] == (earned*20>=threshold)
        assert r['rounded_below_threshold'] == (earned*20<threshold)
    assert calculate(reference([criterion()],level),[outcome()])['score_display']=='20.00'


def test_inactive_nonapplicable_omission_and_zero():
    c=criterion(); c['active']=False
    assert calculate(reference([c],'licence'),[outcome(status='pending')])['result_status']=='not_calculable'
    c['active']=True; c['weight']='0'
    assert calculate(reference([c],'licence'),[outcome(status='pending')])['result_status']=='not_calculable'
    c['weight']='1'
    row=outcome();row['applicable']=False
    assert calculate(reference([c],'licence'),[row])['result_status']=='not_calculable'
    r=evaluate([],reference([c],'licence'))
    assert r['points_earned']==0 and r['maximum_weight']=='1' and r['criteria'][0]['omission']


def test_critical_eliminatory_and_uncertain_no_cap():
    a=criterion();a['weight']='99'
    b=criterion('c2');b['safety']={'consequence':'critical','on_status':['incorrect']}
    rows=[outcome(),outcome('c2','incorrect')]
    assert calculate(reference([a,b],'licence'),rows)['passed'] is True
    b['safety']['consequence']='eliminatory'
    r=calculate(reference([a,b],'licence'),rows)
    assert r['points_earned']==19.8 and r['passed'] is False and 'elimination_cap' not in r
    b['safety']['consequence']='review'
    r=calculate(reference([a,b],'licence'),rows)
    assert r['points_earned'] is None and r['passed'] is None
    rows[1]['safety_resolution']='critical'
    assert calculate(reference([a,b],'licence'),rows)['passed'] is True


class LLM:
    def __init__(self, **overrides): self.overrides=overrides
    def invoke(self, messages, options):
        self.messages=messages
        row=dict(id='c1',status='acceptable',reliable=True,novel=False,omission=False,evidence_message_ids=['message_1'],justification='Question équivalente reconnue.')
        row.update(self.overrides)
        return SimpleNamespace(content=json.dumps({'criteria':[row]}))


def test_semantics_negative_patient_alternative_and_outage():
    conversation=[{'role':'human','content':'Question équivalente ?'},{'role':'assistant','content':'Non.'}]
    r=evaluate(conversation, reference([criterion()],'licence'),llm=LLM())
    assert r['points_earned']==20 and r['criteria'][0]['status']=='acceptable'
    assert r['criteria'][0]['evidence'][0]['quote']=='Question équivalente ?'
    assert 'ALTERNATIVE-PRIVEE' in LLMContext(conversation)
    for llm in [None, SimpleNamespace(invoke=lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))]:
        r=evaluate(conversation,reference([criterion()],'licence'),llm=llm)
        assert r['result_status']=='pending' and r['passed'] is None and r['points_earned'] is None
    alternative=[{'role':'human','content':'ALTERNATIVE-PRIVEE'},{'role':'assistant','content':'Non.'}]
    r=evaluate(alternative,reference([criterion()],'licence'),llm=LLM(status='incorrect'))
    assert r['points_earned']==20 and r['criteria'][0]['status']=='acceptable'


def LLMContext(conversation):
    llm=LLM();evaluate(conversation,reference([criterion()],'licence'),llm=llm)
    return llm.messages[1].content


def setup_attempt(client, app, mode='training'):
    teacher_login(client)
    folder=client.post('/kine/folders',json={'name':'T13 fictif'}).get_json()['id']
    cid=create_case(client,folder,activate=False)
    r=client.post(f'/kine/cases/{cid}/criteria',json={'criteria':[criterion()]})
    assert r.status_code==200,r.get_data(as_text=True)
    version=publish_and_assign(client,cid)
    student_login(client)
    r=client.post('/kine/simulation/start',json={'case_id':cid})
    assert r.status_code==201,r.get_data(as_text=True)
    sid=r.get_json()['simulation_id']
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        s.mode=mode
        s.conversation=[{'role':'human','content':'Une question fictive ?'}]
        db.session.commit()
    return cid,sid


def test_versions_review_permissions_history_and_publication(app):
    client=app.test_client();cid,sid=setup_attempt(client,app,'exam')
    # No exam association in this fixture: complete as training, then mark exam for disclosure checks.
    with app.app_context():
        s=db.session.get(SimulationSession,sid);s.mode='training';db.session.commit()
    r=client.post(f'/kine/simulation/{sid}/complete',json={})
    assert r.status_code==200 and r.get_json()['evaluation']['result_status']=='pending'
    with app.app_context():
        s=db.session.get(SimulationSession,sid);s.mode='exam';s.teacher_comments='COMMENTAIRE-PRIVE';db.session.commit()
        assert len(KineEvaluationChange.query.all())==1
    review={'criterion_id':'c1','status':'acceptable','reason':'Vérification explicite','revision':1,'evidence_message_ids':['message_1']}
    assert client.post(f'/kine/dashboard/simulation/{sid}/classification',json=review).status_code in (401,403)
    teacher_login(client)
    assert client.post(f'/kine/dashboard/simulation/{sid}/feedback-publication',json={'revision':1}).status_code==409
    assert client.post(f'/kine/dashboard/simulation/{sid}/classification',json={**review,'evidence_message_ids':['patient_1']}).status_code==400
    result=client.post(f'/kine/dashboard/simulation/{sid}/classification',json=review)
    assert result.status_code==200,result.get_data(as_text=True)
    assert result.get_json()['evaluation']['points_earned']==20
    assert client.post(f'/kine/dashboard/simulation/{sid}/classification',json=review).status_code==409
    history=client.get(f'/kine/dashboard/simulation/{sid}/evaluation-history').get_json()['changes']
    assert history[1]['before']['criteria'][0]['status']=='pending'
    assert history[1]['after']['criteria'][0]['status']=='acceptable'
    assert history[1]['after']['criteria'][0]['evidence'][0]['quote']=='Une question fictive ?'
    student_login(client)
    paths=[f'/kine/simulation/{sid}/{p}' for p in ['evaluation','chat','timeline','timeline?format=json','patient-record','patient-record?format=json','effort-tests','progress']]+['/kine/history?format=json','/kine/history','/kine/student',f'/kine/cases/{cid}/patient-record']
    for path in paths:
        response=client.get(path)
        assert response.status_code==200,(path,response.status_code)
        for secret in ['ATTENDU-PRIVE','ALTERNATIVE-PRIVEE','COMMENTAIRE-PRIVE','Vérification explicite']:
            assert secret not in response.get_data(as_text=True),(path,secret)
    assert 'criteria' not in client.post(f'/kine/simulation/{sid}/complete',json={}).get_json()['evaluation']
    from PyPDF2 import PdfReader
    from io import BytesIO
    pdf=client.get(f'/kine/simulation/{sid}/pdf')
    assert pdf.status_code==200
    assert 'ATTENDU-PRIVE' not in ''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages)
    teacher_login(client)
    assert client.post(f'/kine/dashboard/simulation/{sid}/feedback-publication',json={'revision':2}).status_code==200
    teacher_pdf=client.get(f'/kine/dashboard/simulation/{sid}/pdf')
    assert teacher_pdf.status_code==200
    teacher_page=client.get(f'/kine/dashboard/simulation/{sid}')
    assert teacher_page.status_code==200 and 'Vérification des classifications' in teacher_page.get_data(as_text=True)
    student_login(client)
    result=client.get(f'/kine/simulation/{sid}/evaluation').get_json()['evaluation']
    assert result['criteria'][0]['expected']=='ATTENDU-PRIVE'
    assert 'safety' not in result['criteria'][0] and 'teacher_approved' not in json.dumps(result)
    teacher_login(client)
    r=client.post(f'/kine/dashboard/simulation/{sid}/classification',json={**review,'revision':3,'status':'partial'})
    assert r.status_code==200 and r.get_json()['evaluation']['points_earned']==10
    student_login(client)
    assert 'criteria' not in client.get(f'/kine/simulation/{sid}/evaluation').get_json()['evaluation']
    with app.app_context():
        with pytest.raises(Exception):
            db.session.execute(text("UPDATE kine_evaluation_changes SET reason='edited'"));db.session.commit()
        db.session.rollback()
        with pytest.raises(Exception):
            db.session.execute(text('DELETE FROM kine_evaluation_changes'));db.session.commit()
        db.session.rollback()


def test_authoring_validation_and_frozen_threshold(app):
    client=app.test_client();cid,sid=setup_attempt(client,app)
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        ref=json.loads(s.evaluation_reference_json)
        assert ref['criteria'][0]['expected']=='ATTENDU-PRIVE' and ref['validation_threshold']=='12'
    teacher_login(client)
    assert client.get(f'/kine/cases/{cid}/criteria').status_code==200
    assert client.get(f'/kine/cases/{cid}').status_code==200
    assert client.post('/kine/evaluation/thresholds',json={'licence':13,'master':15}).status_code==403
    invalid=criterion();invalid['weight']='NaN'
    assert client.post(f'/kine/cases/{cid}/criteria',json={'criteria':[invalid]}).status_code==400
    altered=criterion();altered['expected']='NOUVELLE-ATTENTE'
    assert client.post(f'/kine/cases/{cid}/criteria',json={'criteria':[altered]}).status_code==200
    with app.app_context():
        assert json.loads(db.session.get(SimulationSession,sid).evaluation_reference_json)==ref


def test_conditional_criteria_do_not_exclude_expected_omission():
    c=criterion();c['applicability']={'kind':'event','event_id':'incident-a'}
    ref=reference([c],'licence')
    assert evaluate([],ref,timeline=[])['result_status']=='not_calculable'
    r=evaluate([],ref,timeline=[{'action':'session_event','details':{'id':'incident-a'}}])
    assert r['result_status']=='failed' and r['maximum_weight']=='1' and r['points_earned']==0


def test_shared_evidence_for_distinct_competencies_and_no_patient_evidence():
    class TwoCriteria:
        def invoke(self,*args):
            return SimpleNamespace(content=json.dumps({'criteria':[
                {'id':cid,'status':'correct','reliable':True,'novel':False,'evidence_message_ids':['message_1'],'justification':'Preuve distincte du même énoncé.'}
                for cid in ('c1','c2')]}))
    c=criterion('c2');c['type']='justification'
    r=evaluate([{'role':'human','content':'Question et justification fictives.'},{'role':'assistant','content':'Non.'}],reference([criterion(),c],'licence'),llm=TwoCriteria())
    assert r['points_earned']==20
    assert all(row['evidence'][0]['message_id']=='message_1' for row in r['criteria'])


@pytest.mark.parametrize('overrides', [{'novel':True},{'reliable':False},{'evidence_message_ids':['patient_1']},{'evidence_message_ids':[]},{'status':'invented'}])
def test_uncertainty_never_becomes_error(overrides):
    r=evaluate([{'role':'human','content':'Proposition inhabituelle'}],reference([criterion()],'licence'),llm=LLM(**overrides))
    assert r['result_status']=='pending' and r['points_earned'] is None


def exam_attempt(client, app):
    cid,_=setup_attempt(client,app)
    teacher_login(client)
    version=client.get(f'/kine/cases/{cid}/versions').get_json()['versions'][0]
    now=datetime.utcnow()
    r=client.post('/kine/exams',json={'name':'Examen fictif T16','start_at':(now-timedelta(minutes=1)).isoformat(),
        'end_at':(now+timedelta(minutes=5)).isoformat(),'max_duration_minutes':2,'case_version_ids':[version['id']],'student_ids':[1]})
    assert r.status_code==201,r.get_data(as_text=True)
    eid=r.get_json()['id']
    student_login(client)
    r=client.post('/kine/simulation/start',json={'case_id':cid,'mode':'exam','exam_id':eid})
    assert r.status_code==201,r.get_data(as_text=True)
    return r.get_json()['simulation_id'],datetime.fromisoformat(r.get_json()['deadline'].removesuffix('Z'))


def test_expiry_frozen_deadline_all_mutations_and_cli(app,monkeypatch):
    from blueprints.kine import routes_student, routes_evaluation
    client=app.test_client();sid,end=exam_attempt(client,app)
    with app.app_context():
        s=db.session.get(SimulationSession,sid);s.exam.end_at+=timedelta(days=1);s.exam.max_duration_minutes=500
        s.conversation=[{'role':'human','content':'Interaction avant échéance'}];db.session.commit()
    class Clock(datetime):
        @classmethod
        def utcnow(cls):return end
    monkeypatch.setattr(routes_student,'datetime',Clock)
    monkeypatch.setattr(routes_evaluation,'datetime',Clock)
    # Close without a student request. No AI call should be needed.
    app.config['GROQ_CLIENT']=SimpleNamespace(invoke=lambda *a: pytest.fail('Expiry must not wait for AI'))
    result=app.test_cli_runner().invoke(args=['kine','expire-exams'])
    assert result.exit_code==0,result.output
    for route,data in [('message',{'message':'Trop tard'}),('test-request',{'test_name':'Trop tard'}),('progress',{'phase':1}),
                       ('session-action',{'action':'Trop tard'}),('effort-tests',{}),('pause',{}),('resume',{})]:
        r=client.post(f'/kine/simulation/{sid}/{route}',json=data)
        assert r.status_code in (403,409),(route,r.status_code)
    assert client.get(f'/kine/simulation/{sid}/aids').status_code==403
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.status=='completed' and s.completed_at==end
        assert s.conversation==[{'role':'human','content':'Interaction avant échéance'}]
        assert s.evaluation_results['result_status']=='pending'
        assert len(KineEvaluationChange.query.filter_by(simulation_id=sid).all())==1


def test_crossing_deadline_during_patient_call_keeps_accepted_message(app,monkeypatch):
    from blueprints.kine import routes_student
    client=app.test_client();sid,end=exam_attempt(client,app)
    now=[end-timedelta(seconds=1)]
    class Clock(datetime):
        @classmethod
        def utcnow(cls):return now[0]
    monkeypatch.setattr(routes_student,'datetime',Clock)
    monkeypatch.setattr(routes_student,'matching_question_information',lambda *a,**kw:None)
    def slow(*args,**kwargs):
        now[0]=end
        return {'type':'patient_response','content':'Réponse tardive'}
    monkeypatch.setattr(routes_student.KinePatientEngine,'respond',slow)
    response=client.post(f'/kine/simulation/{sid}/message',json={'message':'Question reçue à temps'})
    assert response.status_code==409
    with app.app_context():
        s=db.session.get(SimulationSession,sid)
        assert s.status=='completed' and s.completed_at==end
        assert [m['content'] for m in s.conversation]==['Question reçue à temps']


def test_review_scope_and_threshold_admin(app):
    from test_kine_permissions import admin_login, pedagogical_login
    client=app.test_client();cid,sid=setup_attempt(client,app)
    client.post(f'/kine/simulation/{sid}/complete',json={})
    with app.app_context():
        teacher=Teacher(email='no-scope@example.test',name='Sans attribution',ecos_type='kine',password_hash='x')
        student=Student(student_code='900090',name='Autre',ecos_type='kine')
        db.session.add_all([teacher,student]);db.session.commit();tid=teacher.id;other=student.id
    teacher_login(client,tid)
    assert client.post(f'/kine/dashboard/simulation/{sid}/classification',json={}).status_code==404
    assert client.get(f'/kine/dashboard/simulation/{sid}/evaluation-history').status_code==404
    admin_login(client)
    assert client.post(f'/kine/dashboard/simulation/{sid}/classification',json={}).status_code==403
    assert client.post('/kine/evaluation/thresholds',json={'licence':13,'master':15}).status_code==403
    pedagogical_login(client,app)
    assert client.post('/kine/evaluation/thresholds',json={'licence':13,'master':15}).status_code==200
    teacher_login(client)
    assert client.get(f'/kine/cases/{cid}/criteria',headers={'Accept':'application/json'}).get_json()['thresholds']=={'licence':'13','master':'15'}
    with app.app_context():
        assert json.loads(db.session.get(SimulationSession,sid).evaluation_reference_json)['validation_threshold']=='12'
    student_login(client,other)
    for path in ['evaluation','pdf','chat','timeline','patient-record','effort-tests','progress','aids']:
        assert client.get(f'/kine/simulation/{sid}/{path}').status_code==404,path


def test_aids_separate_channel_frozen_access_and_validation(app):
    client=app.test_client();cid,sid=setup_attempt(client,app)
    teacher_login(client)
    item=client.post(f'/kine/cases/{cid}/information',json={'path':'custom.hint','label':'Information fictive','value':'Réponse réservée à la question',
        'access_mode':'question','patient_knows':True,'disclosure_conditions':{'terms':['exemple']}}).get_json()['stable_id']
    aid={'id':'a1','text':'Explorez le contexte de cette information.','information_id':item,'active':True,'teacher_approved':True,'no_direct_answer':True}
    assert client.post(f'/kine/cases/{cid}/aids',json={'aids':[aid]}).status_code==200
    publish_and_assign(client,cid)
    student_login(client)
    assert client.get(f'/kine/simulation/{sid}/aids').get_json()['aids']==[]
    sid2=client.post('/kine/simulation/start',json={'case_id':cid}).get_json()['simulation_id']
    result=client.get(f'/kine/simulation/{sid2}/aids').get_json()
    assert result['channel']=='pedagogical' and result['aids']==[{'id':'a1','text':aid['text']}]
    with app.app_context():
        assert db.session.get(SimulationSession,sid2).conversation==[]
