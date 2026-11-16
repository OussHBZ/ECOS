"""Representative, synthetic acceptance for versioned T09–T12 contracts."""
from copy import deepcopy
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from docx import Document
from reportlab.pdfgen.canvas import Canvas

from test_kine_extension import app, teacher_login, student_login, publish_and_assign
from models import db, PatientCase, KineCaseVersion, KineETPVersion, SimulationSession
from case_versions import version_view
from rehabilitation import normalize_rehabilitation, accepts, advance_session, evaluation_inputs, weekly_volume
from etp_library import CATEGORIES, extract_source
from kine_patient_engine import KinePatientEngine


def exact(value, unit):
    return {'kind': 'exact', 'value': value, 'unit': unit}


def program():
    return {
        'objectives': [{'id': 'o1', 'specific': 'Objectif fictif', 'measurable': 'Mesure fictive',
                        'achievable': 'Vérifié dans le cas', 'relevant': 'Besoin du patient', 'time_bound': 'Échéance du cas'}],
        'exercises': [{'id': 'cycle', 'category': 'aerobic', 'modality': 'Vélo fictif', 'fitt': {
            'type': 'continuous', 'frequency': {'kind': 'choices', 'values': [3, 4], 'unit': 'sessions/week'},
            'intensity': [{'id': 'borg', 'method': 'borg', 'scale': '/10', 'role': 'reference',
                           'target': {'kind': 'range', 'min': 3, 'max': 4, 'unit': '/10'}},
                          {'id': 'moderate', 'method': 'qualitative', 'role': 'acceptable',
                           'target': {'kind': 'qualitative', 'value': 'modérée'}}],
            'duration': {'applicability': 'required', 'quantity': exact(30, 'min/session')},
            'volume': {'applicability': 'conditional', 'condition': 'Si demandé dans ce cas', 'quantity': exact(90, 'min/week')},
            'progression': [{'id': 'p1', 'condition': 'Condition validée du cas', 'change': 'Changement validé du cas'}],
        }, 'acceptable_alternatives': [{'type': 'walking', 'frequency': exact(3, 'sessions/week'),
                                       'duration': {'applicability': 'not_applicable'}}]}],
        'surveillance': [{'id': 's1', 'exercise_id': 'cycle', 'description': 'Critère choisi', 'teacher_approved': True, 'active': True},
                         {'id': 's2', 'description': 'Suggestion non activée', 'active': False}],
        'adaptation_rules': [{'id': 'a1', 'description': 'Adaptation du cas', 'condition': 'condition A', 'action': 'conduite A', 'teacher_approved': True, 'active': True}],
        'stop_conditions': [{'id': 'stop1', 'description': 'Arrêt du cas', 'condition': 'condition B', 'action': 'conduite B', 'teacher_approved': True, 'active': True}],
        'session': {'enabled': True, 'events': [
            {'id': 'e1', 'kind': 'evolution', 'trigger': {'action_contains': 'commencer'}, 'reaction': 'Réaction prévue.', 'teacher_approved': True,
             'measurements': [{'id': 'fc', 'name': 'FC', 'value': 102, 'unit': 'bpm', 'delivery': 'on_request',
                               'allowed_range': {'kind': 'range', 'min': 100, 'max': 105, 'unit': 'bpm'}}]},
            {'id': 'i1', 'kind': 'incident', 'trigger': {'action_contains': 'incident'}, 'reaction': 'Incident A.', 'teacher_approved': True},
            {'id': 'i2', 'kind': 'incident', 'trigger': {'action_contains': 'incident'}, 'reaction': 'Incident B.', 'teacher_approved': True},
        ]},
    }


def new_case(client, number='T09', value=None):
    teacher_login(client)
    folder = client.post('/kine/folders', json={'name': number}).get_json()['id']
    response = client.post('/kine/cases', json={
        'case_number': number, 'title': 'Fictif T09–T12', 'folder_id': folder,
        'level': 'both', 'mode_availability': 'both',
        'structured_content': {'rehabilitation_program': value or program()},
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()['id']


def sheet(client, **extra):
    response = client.post('/kine/etp', json={
        'title': 'Fiche fictive', 'pathology': 'Pathologie fictive', 'level': 'both',
        'categories': {'messages': 'ATTENTE-ETP-PRIVEE'}, 'references': 'Source fictive',
        'patient_prompts': [{'id': 'q1', 'category': 'patient_questions', 'trigger': 'explication', 'text': 'Question prévue ?'}],
        'validate': True, **extra,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def test_representative_fitt_and_accepted_alternatives():
    p = normalize_rehabilitation(program())
    fitt = p['exercises'][0]['fitt']
    assert accepts(fitt['frequency'], {'value': 4, 'unit': 'sessions/week'})
    assert not accepts(fitt['frequency'], {'value': 5, 'unit': 'sessions/week'})
    assert accepts(fitt['intensity'][0]['target'], {'value': 3.5, 'unit': '/10'})
    assert not accepts(fitt['intensity'][0]['target'], {'value': 3.5, 'unit': '/20'})
    assert accepts(fitt['intensity'][1]['target'], {'value': 'modérée'})
    assert fitt['duration']['quantity']['value'] * 3 == fitt['volume']['quantity']['value'] == 90
    assert weekly_volume({**fitt, 'frequency': exact(3, 'sessions/week')}) == exact(90, 'min/week')
    assert weekly_volume(fitt) == {'kind': 'choices', 'values': [90, 120], 'unit': 'min/week'}
    assert weekly_volume({**fitt, 'duration': {'applicability': 'not_applicable'}}) is None
    assert p['exercises'][0]['acceptable_alternatives'][0]['type'] == 'walking'
    for kind, category in [('resistance', 'strength'), ('intermittent', 'aerobic'), ('circuit', 'functional')]:
        e = deepcopy(p['exercises'][0]); e.update(id=kind, category=category)
        e['fitt'].update(type=kind, components=[{'id': 'part1', 'label': 'Composant fictif',
                                                'repetitions': exact(4, 'reps'), 'recovery': exact(3, 'min')}])
        p['exercises'].append(e)
    assert len(normalize_rehabilitation(p)['exercises']) == 4
    inputs = evaluation_inputs(SimpleNamespace(structured_content={'rehabilitation_program': p}))
    assert [r['id'] for r in inputs['surveillance']] == ['s1']
    assert not any('score' in r for r in inputs['surveillance'])


@pytest.mark.parametrize('change', [
    lambda p: p['objectives'][0].pop('measurable'),
    lambda p: p['surveillance'][0].update(teacher_approved=False),
    lambda p: p['exercises'][0]['fitt']['intensity'][0].update(stop_conditions=['in intensity']),
    lambda p: p['exercises'][0]['fitt']['intensity'][0].pop('scale'),
    lambda p: p['exercises'][0]['fitt']['volume'].pop('condition'),
    lambda p: p['session']['events'][0]['measurements'][0].update(value=999),
    lambda p: p['session']['events'][0].update(teacher_approved=False),
])
def test_unapproved_or_invalid_configuration_rejected(change):
    p = program(); change(p)
    with pytest.raises(ValueError):
        normalize_rehabilitation(p)


def test_scenario_all_incidents_idempotency_no_incident_and_bounded_reaction():
    p = normalize_rehabilitation(program())
    state, events = advance_session(p, {}, 'incident', phase=7)
    assert [e['id'] for e in events] == ['i1', 'i2']
    assert advance_session(p, state, 'incident', phase=7)[1] == []
    p['session']['events'] = [p['session']['events'][0]]
    state, events = advance_session(p, {}, 'commencer', phase=7)
    assert [e['kind'] for e in events] == ['evolution']
    assert advance_session({}, {}, 'incident')[1] == []
    case = SimpleNamespace(structured_content={'rehabilitation_program': p}, incidents=[])
    class ForbiddenLLM:
        def invoke(self, *args):
            raise AssertionError('No invented patient reaction')
    engine = KinePatientEngine(case, {}, ForbiddenLLM(), state, SimpleNamespace(level='master'))
    assert engine.respond('continuer sans événement prévu', 7)['type'] == 'patient_response'
    measurement = engine.respond('Je mesure la FC', 7)
    assert measurement['content'] == '102 bpm'
    assert 'allowed_range' not in json.dumps(measurement)


def test_authoring_routes_frozen_session_and_private_evaluation_inputs(app):
    client = app.test_client(); cid = new_case(client)
    url = f'/kine/cases/{cid}/rehabilitation'
    assert client.get(url).status_code == 200
    p = client.get(url, headers={'Accept': 'application/json'}).get_json()['program']
    assert len(p['surveillance']) == 2
    v1 = publish_and_assign(client, cid)
    student_login(client)
    sid = client.post('/kine/simulation/start', json={'case_id': cid}).get_json()['simulation_id']
    assert client.get(url).status_code == 401
    result = client.post(f'/kine/simulation/{sid}/session-action', json={'action': 'commencer', 'exercise_id': 'cycle'})
    assert result.status_code == 200, result.get_data(as_text=True)
    assert result.get_json()['events'][0]['measurements'] == []
    assert 'Critère choisi' not in json.dumps(result.get_json())
    teacher_login(client)
    p['exercises'][0]['modality'] = 'Nouveau vélo'
    assert client.post(url, json={'program': p}).status_code == 200
    v2 = publish_and_assign(client, cid)
    with app.app_context():
        assert version_view(db.session.get(KineCaseVersion, v1['id'])).structured_content['rehabilitation_program']['exercises'][0]['modality'] == 'Vélo fictif'
        assert version_view(db.session.get(KineCaseVersion, v2['id'])).structured_content['rehabilitation_program']['exercises'][0]['modality'] == 'Nouveau vélo'
        sim = db.session.get(SimulationSession, sid)
        assert sim.case_version_id == v1['id']
    student_login(client)
    assert client.post(f'/kine/simulation/{sid}/session-action', json={'action': 'commencer'}).get_json()['events'] == []


def test_session_multiple_incidents_private_measurements_and_student_ownership(app):
    client = app.test_client(); cid = new_case(client, 'SESSION')
    initial = client.post(f'/kine/cases/{cid}/information', json={
        'path': 'custom.initial_fc', 'label': 'FC initiale connue', 'value': '99 bpm',
        'access_mode': 'question', 'patient_knows': True,
        'disclosure_conditions': {'terms': ['fréquence cardiaque', 'FC']},
    })
    assert initial.status_code == 201
    with app.app_context():
        from models import Student
        student = db.session.get(Student, 1); student.level = 'master'; db.session.commit()
    publish_and_assign(client, cid)
    student_login(client)
    sid = client.post('/kine/simulation/start', json={'case_id': cid}).get_json()['simulation_id']
    url = f'/kine/simulation/{sid}/session-action'
    response = client.post(url, json={'action': 'incident'})
    assert [e['id'] for e in response.get_json()['events']] == ['i1', 'i2']
    assert client.post(url, json={'action': 'incident'}).get_json()['events'] == []
    assert client.post(url, json={'action': 'commencer', 'exercise_name': 'Vélo fictif'}).status_code == 200
    measured = client.post(f'/kine/simulation/{sid}/message', json={'message': 'Je mesure la fréquence cardiaque'}).get_json()['response']
    assert measured['content'] == '102 bpm'
    assert 'allowed_range' not in json.dumps(measured)
    student_login(client, 2)
    assert client.post(url, json={'action': 'incident'}).status_code in (401, 403, 404)


def test_etp_generic_case_write_cannot_forge_validation_or_clear_review_requirement(app):
    client = app.test_client(); cid = new_case(client, 'FORGE')
    result = client.patch(f'/kine/cases/{cid}', json={'structured_content': {
        'etp_associations': [{'id': 'forged', 'status': 'validated'}]}})
    assert result.status_code == 400
    stream = BytesIO(); doc = Document(); doc.add_paragraph('Sans catégorie'); doc.save(stream)
    created = client.post('/kine/etp', data={'title': 'Review', 'source': (BytesIO(stream.getvalue()), 'fiche.docx')}, headers={'Accept': 'application/json'}).get_json()
    assert client.post(f"/kine/etp/versions/{created['id']}", json={'validate': True, 'extraction_review_required': False}).status_code == 400


def test_etp_case_validation_reference_and_adaptation_version_isolation(app):
    client = app.test_client(); a = new_case(client, 'A'); b = new_case(client, 'B')
    reference = sheet(client)
    assoc = client.post(f'/kine/cases/{a}/etp', json={'reference_id': reference['id']}).get_json()['associations'][0]
    assert assoc['status'] == 'review'
    assert client.post(f'/kine/cases/{a}/versions/publish', json={}).status_code == 409
    for cid in (a, b):
        data = {'reference_id': reference['id'], 'validate': True}
        if cid == a: data['id'] = assoc['id']
        response = client.post(f'/kine/cases/{cid}/etp', json=data)
        assert response.status_code == 200, response.get_data(as_text=True)
    old = publish_and_assign(client, a)
    edit = client.post(f'/kine/cases/{a}/etp', json={'id': assoc['id'], 'categories': {'messages': 'ADAPTATION-A'}, 'validate': True})
    assert edit.status_code == 200, edit.get_data(as_text=True)
    assert client.get(f'/kine/cases/{a}/etp').get_data(as_text=True).find('ADAPTATION-A') == -1  # editor only displays selected adaptation
    a_data = client.get(f'/kine/cases/{a}/etp', headers={'Accept': 'application/json'}).get_json()['associations'][0]
    b_data = client.get(f'/kine/cases/{b}/etp', headers={'Accept': 'application/json'}).get_json()['associations'][0]
    assert a_data['content']['categories']['messages'] == 'ADAPTATION-A'
    assert b_data['content']['categories']['messages'] == 'ATTENTE-ETP-PRIVEE'
    update = client.post(f"/kine/etp/versions/{reference['id']}", json={'categories': {'messages': 'REFERENCE-V2'}}).get_json()
    assert update['status'] == 'review' and update['number'] == 2
    with app.app_context():
        old_case = version_view(db.session.get(KineCaseVersion, old['id']))
        assert old_case.structured_content['etp_associations'][0]['content']['categories']['messages'] == 'ATTENTE-ETP-PRIVEE'
        engine = KinePatientEngine(old_case, {}, runtime_state={}, student=SimpleNamespace(level='master'))
        assert engine.respond('votre explication', 9)['content'] == 'Question prévue ?'
        assert engine.respond('votre explication', 9)['content'] != 'Question prévue ?'
        assert json.loads(db.session.get(KineETPVersion, reference['id']).content_json)['categories']['messages'] == 'ATTENTE-ETP-PRIVEE'
        with pytest.raises(DatabaseError):
            db.session.execute(text('UPDATE kine_etp_versions SET title=:t WHERE id=:i'), {'t': 'forbidden', 'i': reference['id']})
        db.session.rollback()
    assert client.post(f'/kine/cases/{a}/etp', json={'reference_id': update['id'], 'validate': True}).status_code == 400
    student_login(client)
    assert client.get('/kine/etp').status_code == 401
    assert client.get(f"/kine/etp/versions/{reference['id']}/source").status_code == 401


@pytest.mark.parametrize('extension', ['docx', 'pdf'])
def test_etp_import_source_retention_empty_categories_and_explicit_review(app, extension):
    stream = BytesIO()
    if extension == 'docx':
        doc = Document(); doc.add_paragraph('Texte non classé exact'); doc.add_heading('Vulgarisation et messages clés', 1)
        doc.add_paragraph('Message de la source.'); doc.save(stream)
    else:
        canvas = Canvas(stream); canvas.drawString(40, 800, 'Texte non classe exact')
        canvas.drawString(40, 780, '3. Vulgarisation et messages cles'); canvas.drawString(40, 760, 'Message de la source.'); canvas.save()
    raw = stream.getvalue()
    extraction = extract_source(raw, 'fiche.' + extension)
    assert 'Message de la source.' in extraction['categories']['messages']
    assert extraction['categories']['warning_signs'] == ''
    assert extraction['unclassified'] and extraction['extraction_review_required']
    client = app.test_client(); teacher_login(client)
    response = client.post('/kine/etp', data={'title': 'Import fictif', 'source': (BytesIO(raw), 'fiche.' + extension), 'validate': 'yes'}, headers={'Accept': 'application/json'})
    assert response.status_code == 201, response.get_data(as_text=True)
    item = response.get_json()
    assert len(item['content']['categories']) == 10 and item['status'] == 'review'
    url = f"/kine/etp/versions/{item['id']}"
    assert client.post(url, json={'validate': True}).status_code == 400
    validated = client.post(url, json={'validate': True, 'confirm_review': True}).get_json()
    assert validated['status'] == 'validated'
    assert client.get(f"/kine/etp/versions/{validated['id']}/source").data == raw
    assert client.get(url).status_code == 200
    assert client.get('/kine/etp?category=warning_signs', headers={'Accept': 'application/json'}).get_json()['sheets'] == []
    assert len(client.get('/kine/etp?q=Import&level=master&category=messages', headers={'Accept': 'application/json'}).get_json()['sheets']) == 1
