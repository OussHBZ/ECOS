"""T06–T08 acceptance on isolated synthetic cases and sessions."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from test_kine_extension import app, teacher_login, student_login, publish_and_assign
from models import db, PatientCase, SimulationSession, Student, Teacher
from information_access import record_projection, matching_question_information, AmbiguousQuestion
from kine_patient_engine import KinePatientEngine
from patient_personality import personality_for, normalize_personality


def efforts():
    return [
        {'id': 'walk', 'name': '6MWT', 'protocol': 'Source fictive A', 'measurements': [
            {'id': 'fc-start', 'name': 'FC', 'moment': 'initial', 'actor': 'student', 'value': 0, 'unit': 'bpm', 'source': 'Source A', 'expected_type': 'range', 'expected_value': 'EXPECTED-SECRET', 'thresholds': 'THRESHOLD-SECRET'},
            {'id': 'fc-two', 'name': 'FC', 'moment': 'stage', 'moment_detail': '2 minutes', 'actor': 'student', 'value': 102, 'unit': 'bpm'},
            {'id': 'symptom', 'name': 'Fatigue', 'moment': 'end', 'actor': 'patient', 'patient_knows': False, 'value': 'PATIENT-UNKNOWN'},
            {'id': 'auto', 'name': 'SpO2', 'moment': 'recovery', 'actor': 'system', 'trigger': 'recovery', 'value': 97, 'unit': '%'},
            {'id': 'observer', 'name': 'Observation', 'moment': 'end', 'actor': 'teacher', 'status': 'unknown'},
        ]},
        {'id': 'cycle', 'name': 'Cycloergomètre', 'measurements': [
            {'id': 'fc-start', 'name': 'FC', 'moment': 'initial', 'actor': 'student', 'value': 71, 'unit': 'bpm'},
            {'id': 'missing', 'name': 'Douleur', 'moment': 'end', 'actor': 'student', 'status': 'not_evaluated'},
        ]},
    ]


def fixture_case(client):
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': 'T06-T08 fictif'}).get_json()['id']
    response = client.post('/kine/cases', json={
        'case_number': 'T06-T08', 'title': 'Patient fictif', 'folder_id': folder,
        'level': 'both', 'mode_availability': 'both',
        'structured_content': {'patient_personality': {
            'enabled': True, 'anxiety': 'very_anxious', 'trust': 'low',
            'transitions': [{'terms': ['prenons le temps'], 'after_occurrences': 2, 'trust': 'moderate'}],
        }},
        'patient_record': {'identity': {'name': 'Patient fictif'}, 'tests': {'effort_tests': efforts()}},
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    cid = response.get_json()['id']
    # Authored equivalent formulations carry no invented clinical data.
    fact = client.post(f'/kine/cases/{cid}/information', json={
        'path': 'custom.dyspnea', 'label': 'Dyspnée à la marche', 'value': 'FAIT-STABLE',
        'access_mode': 'question', 'patient_knows': True,
        'disclosure_conditions': {'terms': ['dyspnée']},
    })
    assert fact.status_code == 201, fact.get_data(as_text=True)
    publish_and_assign(client, cid)
    return cid, fact.get_json()['stable_id']


def start(client, cid):
    student_login(client)
    response = client.post('/kine/simulation/start', json={'case_id': cid, 'mode': 'training'})
    assert response.status_code == 201
    return response.get_json()['simulation_id']


def test_effort_round_trip_hidden_expectations_actors_and_independent_values(app):
    client = app.test_client()
    cid, fact = fixture_case(client)
    with app.app_context():
        case = db.session.get(PatientCase, cid)
        from effort_tests import normalize_effort_tests
        assert case.patient_record.tests['effort_tests'] == normalize_effort_tests(efforts())
        assert any(item.path.startswith('evaluation_expectations.effort_tests') for item in case.information_items)
    page = client.get(f'/kine/cases/{cid}').get_data(as_text=True)
    assert 'personality_anxiety' in page and 'effort_measurements[__INDEX__][expected_value]' in page
    assert 'data-information-editor' in page and 'kine-information-policy.js' in page
    sid = start(client, cid)
    url = f'/kine/simulation/{sid}/effort-tests'
    catalog = client.get(url).get_json()
    serialized = json.dumps(catalog)
    assert 'EXPECTED-SECRET' not in serialized and 'THRESHOLD-SECRET' not in serialized
    assert 'PATIENT-UNKNOWN' not in serialized and 'very_anxious' not in serialized
    for test_id, measurement_id, expected in [('walk', 'fc-start', 0), ('walk', 'fc-two', 102), ('cycle', 'fc-start', 71)]:
        result = client.post(url, json={'test_id': test_id, 'measurement_id': measurement_id})
        assert result.status_code == 200, result.get_data(as_text=True)
        assert result.get_json()['measurement']['value'] == expected
    for measurement_id in ('symptom', 'auto', 'observer'):
        assert client.post(url, json={'test_id': 'walk', 'measurement_id': measurement_id}).status_code in (403, 404)
    missing = client.post(url, json={'test_id': 'cycle', 'measurement_id': 'missing'}).get_json()['measurement']
    assert missing['status'] == 'not_evaluated' and 'value' not in missing
    assert client.post(url, json={'test_id': 'unknown', 'measurement_id': 'fc-start'}).status_code == 404
    event_url = f'/kine/simulation/{sid}/effort-event'
    assert client.post(event_url, json={'test_id': 'walk', 'event': 'unknown'}).get_json()['measurements'] == []
    assert client.post(event_url, json={'test_id': 'walk', 'event': 'recovery'}).get_json()['measurements'][0]['value'] == 97
    assert client.post(event_url, json={'test_id': 'walk', 'event': 'recovery'}).get_json()['measurements'] == []
    student_record = client.get(f'/kine/simulation/{sid}/patient-record', headers={'Accept': 'application/json'}).get_json()['record']
    assert student_record['effort_tests']['walk']['fc-start']['value'] == 0
    assert student_record['effort_tests']['cycle']['fc-start']['value'] == 71
    assert 'EXPECTED-SECRET' not in json.dumps(student_record)
    html = client.get(f'/kine/simulation/{sid}/chat').get_data(as_text=True)
    assert 'data-record-sidebar' in html and 'aria-controls="kine-record-sidebar"' in html
    assert 'EXPECTED-SECRET' not in html and 'very_anxious' not in html
    teacher_login(client)
    observed = client.post(f'/kine/teacher/simulation/{sid}/effort-measurement', json={
        'test_id': 'walk', 'measurement_id': 'observer', 'observed_value': 'Observation fictive',
    })
    assert observed.status_code == 200
    assert observed.get_json()['measurement']['source'] == 'teacher_reported'


def test_reformulations_recall_version_preservation_and_session_isolation(app):
    # Neutral dialogue now requires an available provider; absent service is
    # explicitly tested as 503 in T20. Preserve all recall/isolation assertions.
    app.config['GROQ_CLIENT'] = SimpleNamespace(invoke=lambda *a, **k: SimpleNamespace(content='Je vous écoute.'))
    client = app.test_client()
    cid, fact = fixture_case(client)
    a = start(client, cid)
    for message in ('Êtes-vous essoufflé quand vous marchez ?', 'Avez-vous du mal à respirer pendant l’effort ?', 'Est-ce que la marche vous coupe le souffle ?'):
        response = client.post(f'/kine/simulation/{a}/message', json={'message': message})
        assert response.status_code == 200
        assert response.get_json()['response']['content'] == 'FAIT-STABLE'
    for i in range(30):
        assert client.post(f'/kine/simulation/{a}/message', json={'message': f'Échange neutre {i}.'}).status_code == 200
    assert client.post(f'/kine/simulation/{a}/message', json={'message': 'Vous disiez ?'}).get_json()['response']['content'] == 'FAIT-STABLE'
    b = start(client, cid)
    assert client.get(f'/kine/simulation/{b}/information/{fact}').status_code == 404
    teacher_login(client)
    assert client.put(f'/kine/cases/{cid}/information/{fact}', json={'value': 'FAIT-V2'}).status_code == 200
    publish_and_assign(client, cid)
    student_login(client)
    assert client.post(f'/kine/simulation/{a}/message', json={'message': 'Dyspnée ?'}).get_json()['response']['content'] == 'FAIT-STABLE'
    c = start(client, cid)
    assert client.post(f'/kine/simulation/{c}/message', json={'message': 'Dyspnée ?'}).get_json()['response']['content'] == 'FAIT-V2'
    with app.app_context():
        db.session.add(Student(student_code='876543', name='Other', level='master', ecos_type='kine'))
        db.session.commit()
    student_login(client, 2)
    assert client.get(f'/kine/simulation/{a}/effort-tests').status_code == 404
    assert client.get(f'/kine/simulation/{a}/information/{fact}').status_code == 404


def test_preview_is_optional_private_stale_safe_and_has_no_student_side_effects(app):
    client = app.test_client()
    cid, fact = fixture_case(client)
    sid = start(client, cid)
    teacher_login(client)
    url = f'/kine/cases/{cid}/patient-preview'
    first = client.post(url, json={'message': 'Dyspnée ?'}).get_json()
    assert first['response']['content'] == 'Cela m’inquiète beaucoup. FAIT-STABLE' and first['preview_only'] is True
    second = client.post(url, json={}).get_json()
    assert second['preview_id'] != first['preview_id']
    with app.app_context():
        assert SimulationSession.query.count() == 1
        attempt = db.session.get(SimulationSession, sid)
        assert not attempt.conversation and not attempt.runtime_state
        assert fact not in {item.stable_id for item in attempt.information_disclosures}
    other_client = app.test_client()
    teacher_login(other_client)
    assert other_client.post(url, json={'preview_id': first['preview_id'], 'message': 'Dyspnée ?'}).status_code == 404
    assert client.put(f'/kine/cases/{cid}/information/{fact}', json={'value': 'changed'}).status_code == 200
    assert client.post(url, json={'preview_id': first['preview_id'], 'message': 'Dyspnée ?'}).status_code == 409
    student_login(client)
    assert client.get(url).status_code in (302, 401, 403)
    assert client.post(url, json={'message': 'Dyspnée ?'}).status_code in (302, 401, 403)


def test_personality_authored_progression_level_and_clinical_immutability():
    profile = {'enabled': True, 'anxiety': 'very_anxious', 'trust': 'low', 'transitions': [
        {'terms': ['prenons le temps'], 'after_occurrences': 2, 'trust': 'moderate'},
    ]}
    case = {'structured_content': {'patient_personality': profile}, 'emotional_state': 'anxious'}
    baseline = deepcopy(case)
    assert personality_for(case, 'licence') == {}
    assert personality_for(case, 'master', message='prenons le temps')['trust'] == 'low'
    history = [{'role': 'human', 'content': 'prenons le temps'}]
    evolved = personality_for(case, 'master', history, 'prenons le temps')
    assert evolved['trust'] == 'moderate' and evolved['anxiety'] == 'very_anxious'
    assert case == baseline
    engine = KinePatientEngine(case, {'identity': {'name': 'Camille'}}, student=SimpleNamespace(level='master'))
    assert 'very_anxious' in engine.build_system_prompt(2)
    engine = KinePatientEngine(case, {}, student=SimpleNamespace(level='licence'))
    assert 'very_anxious' not in engine.build_system_prompt(2)
    with pytest.raises(ValueError):
        normalize_personality({'enabled': True, 'transitions': [{'terms': ['bonjour'], 'after_occurrences': 1}]})


def test_semantic_router_cannot_choose_reserved_or_bypass_deepening(app):
    client = app.test_client()
    cid, fact = fixture_case(client)
    deep = client.post(f'/kine/cases/{cid}/information', json={
        'path': 'custom.deep', 'label': 'Précision protégée', 'value': 'DEEP-SECRET',
        'access_mode': 'deepening', 'patient_knows': True,
        'disclosure_conditions': {'terms': ['approfondir'], 'requires_information': [fact]},
    }).get_json()['stable_id']
    publish_and_assign(client, cid)
    sid = start(client, cid)
    with app.app_context():
        attempt = db.session.get(SimulationSession, sid)
        class Router:
            def invoke(self, messages):
                content = str(messages[0].content)
                assert 'EXPECTED-SECRET' not in content and 'THRESHOLD-SECRET' not in content
                return SimpleNamespace(content=json.dumps({'information_id': 'forged-reserved-id'}))
        assert matching_question_information(attempt.case_version, attempt, 'licence', 'Question sans correspondance', llm=Router()) is None
        reserved_id = next(item.stable_id for item in attempt.case_version.information_items if item.path.startswith('evaluation_expectations.'))
        class ForbiddenRouter:
            def __init__(self, chosen): self.chosen = chosen
            def invoke(self, messages):
                assert 'DEEP-SECRET' not in messages[0].content
                return SimpleNamespace(content=json.dumps({'information_id': self.chosen}))
        for chosen in (reserved_id, deep):
            assert matching_question_information(attempt.case_version, attempt, 'licence', 'Reformulation libre', llm=ForbiddenRouter(chosen)) is None
        class ValidRouter:
            def invoke(self, messages):
                return SimpleNamespace(content=json.dumps({'information_id': fact}))
        assert matching_question_information(attempt.case_version, attempt, 'licence', 'Reformulation libre', llm=ValidRouter()).stable_id == fact


def test_form_effort_and_profile_round_trip_clear_and_import_schema(app):
    from test_case_authoring import _authoring_form
    client = app.test_client()
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name':'T08 formulaire'}).get_json()['id']
    form = _authoring_form(folder, case_number='T08-FORM', personality_enabled='true', personality_anxiety='worried')
    values = {
        'effort_tests[0][id]':'marche', 'effort_tests[0][name]':'Marche fictive',
        'effort_tests[0][protocol]':'Page 2, source fictive',
        'effort_measurements[0][test_id]':'marche', 'effort_measurements[0][id]':'fc',
        'effort_measurements[0][name]':'FC', 'effort_measurements[0][moment]':'stage',
        'effort_measurements[0][moment_detail]':'2 minutes', 'effort_measurements[0][actor]':'student',
        'effort_measurements[0][status]':'value', 'effort_measurements[0][value]':'0',
        'effort_measurements[0][unit]':'bpm', 'effort_measurements[0][source]':'Page 2',
        'effort_measurements[0][expected_type]':'exact', 'effort_measurements[0][expected_value]':'SECRET-FORM',
    }
    for key, value in values.items(): form.add(key, value)
    response=client.post('/kine/cases',data=form,headers={'Accept':'application/json'})
    assert response.status_code==201, response.get_data(as_text=True)
    cid=response.get_json()['id']
    with app.app_context():
        case=db.session.get(PatientCase,cid)
        row=case.patient_record.tests['effort_tests'][0]['measurements'][0]
        assert row['value']=='0' and row['source']=='Page 2' and row['expected_value']=='SECRET-FORM'
        assert case.structured_content['patient_personality']['anxiety']=='worried'
        from blueprints.kine.routes_teacher import _case_form_payload
        with app.test_request_context():
            data=_case_form_payload(case)
            assert data['effort_tests'][0]['measurements'][0]['moment_detail']=='2 minutes'
            assert 'effort_tests' not in data['tests']
    # Save a second authoritative form with no rows: deleted measures cannot reappear.
    inventory=client.get(f'/kine/cases/{cid}/information').get_json()['information']
    measure_policy=next(item for item in inventory if item['path']=='effort_tests.marche.fc')
    assert client.put(f"/kine/cases/{cid}/information/{measure_policy['stable_id']}",json={'access_mode':'question'}).status_code==200
    cleared=_authoring_form(folder,case_number='T08-FORM',personality_enabled='false')
    assert client.post(f'/kine/cases/{cid}',data=cleared,headers={'Accept':'application/json'}).status_code==200
    with app.app_context():
        case=db.session.get(PatientCase,cid)
        assert not case.patient_record.tests.get('effort_tests')
        assert not any(item.path.startswith('effort_tests.') for item in case.information_items)
        assert case.structured_content['patient_personality']['enabled'] is False


def test_effort_and_personality_versions_remain_frozen(app):
    from case_versions import simulation_case
    client=app.test_client()
    cid,_=fixture_case(client)
    a=start(client,cid)
    teacher_login(client)
    with app.app_context(): folder=db.session.get(PatientCase,cid).folder_id
    changed=efforts();changed[0]['measurements'][0]['value']=55
    response=client.put(f'/kine/cases/{cid}',json={
        'case_number':'T06-T08','title':'Patient fictif V2','folder_id':folder,
        'level':'both','mode_availability':'both','patient_record':{'tests':{'effort_tests':changed}},
        'structured_content':{'patient_personality':{'enabled':True,'anxiety':'calm'}},
    })
    assert response.status_code==200,response.get_data(as_text=True)
    publish_and_assign(client,cid)
    b=start(client,cid)
    for sid,expected in ((a,0),(b,55)):
        value=client.post(f'/kine/simulation/{sid}/effort-tests',json={'test_id':'walk','measurement_id':'fc-start'})
        assert value.status_code==200 and value.get_json()['measurement']['value']==expected
    with app.app_context():
        assert simulation_case(db.session.get(SimulationSession,a)).structured_content['patient_personality']['anxiety']=='very_anxious'
        assert simulation_case(db.session.get(SimulationSession,b)).structured_content['patient_personality']['anxiety']=='calm'


def test_ambiguous_question_reveals_no_information_and_manual_measure_is_not_reference(app):
    client=app.test_client()
    cid,fact=fixture_case(client)
    other=client.post(f'/kine/cases/{cid}/information',json={
        'path':'custom.other','label':'Autre dyspnée','value':'OTHER-FACT',
        'access_mode':'question','patient_knows':True,'disclosure_conditions':{'terms':['dyspnée']},
    }).get_json()['stable_id']
    publish_and_assign(client,cid)
    sid=start(client,cid)
    response=client.post(f'/kine/simulation/{sid}/message',json={'message':'Dyspnée ?'}).get_json()
    assert response['response']['content']=='Pouvez-vous préciser votre question ?'
    assert {fact,other}.isdisjoint(response['revealed_information_ids'])
    observed=client.post(f'/kine/simulation/{sid}/effort-tests',json={
        'test_id':'walk','measurement_id':'fc-start','observed_value':'42',
    }).get_json()['measurement']
    assert observed['value']=='42' and observed['source']=='student_reported'
    record=client.get(f'/kine/simulation/{sid}/patient-record',headers={'Accept':'application/json'}).get_json()['record']
    assert not record.get('effort_tests')
    embedded=client.get(f'/kine/simulation/{sid}/patient-record?embedded=1').get_data(as_text=True)
    assert 'kine-record-embedded' in embedded and 'SECRET' not in embedded
    client.post(f'/kine/simulation/{sid}/pause',json={})
    assert client.post(f'/kine/simulation/{sid}/effort-tests',json={'test_id':'walk','measurement_id':'fc-start'}).status_code==409


def test_patient_effort_knowledge_and_reserved_policy_cannot_be_overridden(app):
    client=app.test_client()
    cid,_=fixture_case(client)
    policies=client.get(f'/kine/cases/{cid}/information').get_json()
    # Collection response is the teacher inventory; each setting remains server validated.
    rows=policies['information'] if isinstance(policies,dict) and 'information' in policies else policies
    reserved=next(row for row in rows if row['path'].startswith('evaluation_expectations.effort_tests'))
    assert client.put(f"/kine/cases/{cid}/information/{reserved['stable_id']}",json={'access_mode':'initial'}).status_code==400
    symptom=next(row for row in rows if row['path']=='effort_tests.walk.symptom')
    assert client.put(f"/kine/cases/{cid}/information/{symptom['stable_id']}",json={'patient_knows':True}).status_code==200
    publish_and_assign(client,cid)
    sid=start(client,cid)
    result=client.post(f'/kine/simulation/{sid}/message',json={'message':'Quelle fatigue ressentez-vous ?'})
    assert result.status_code==200,result.get_data(as_text=True)
    assert result.get_json()['response']['content']=='PATIENT-UNKNOWN'
    observed=client.get(f'/kine/simulation/{sid}/effort-tests').get_json()['measurements']
    assert observed[-1]['test_id']=='walk' and observed[-1]['source']=='patient'
    assert observed[-1]['value']=='PATIENT-UNKNOWN'


@pytest.mark.parametrize('patch', [
    {'id': 'bad.id'}, {'actor': 'administrator'}, {'moment': 'invented'},
    {'moment': 'stage'}, {'expected_type': 'auto-diagnosis'},
    {'actor': 'system'},
])
def test_effort_rejects_invalid_identity_actor_moment_and_unconfigured_rules(patch):
    from effort_tests import normalize_effort_tests
    row = {'id': 'm', 'name': 'FC', 'moment': 'initial', 'actor': 'student', **patch}
    with pytest.raises(ValueError):
        normalize_effort_tests([{'id': 't', 'name': 'test', 'measurements': [row]}])
