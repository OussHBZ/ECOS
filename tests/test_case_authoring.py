"""T05 case-authoring acceptance tests with fictitious data only."""

import io
import json

from werkzeug.datastructures import MultiDict

from test_kine_extension import app, student_login, teacher_login
from models import db, KineCaseDocument, KineCaseVersion, PatientCase


def _folder(client):
    return client.post('/kine/folders', json={'name': 'T05 dossier fictif'}).get_json()['id']


def _authoring_form(folder_id, **overrides):
    values = MultiDict([
        ('form_version', '3'), ('case_number', 'T05-001'),
        ('title', 'Cas fictif T05'), ('folder_id', str(folder_id)),
        ('level', 'both'), ('mode_availability', 'both'),
        ('difficulty', 'medium'), ('subpathology', 'Sous-pathologie fictive'),
        ('rehabilitation_phase', 'phase_ii'), ('planned_sessions', '12'),
        ('wizard_page', '4'), ('wizard_completed_pages', '1'),
        ('wizard_completed_pages', '2'), ('identity_first_name', 'Camille'),
        ('identity_last_name', 'Fictif'), ('height_cm', '170'),
        ('weight_kg', '68'), ('medical_diagnosis', 'Diagnostic médical fictif'),
        ('diagnosis', 'Diagnostic kinésithérapique fictif'),
        ('clinical_synthesis', 'Synthèse conservée'),
        ('medical_prescription_diagnosis', 'Diagnostic prescription'),
        ('physiotherapy_frequency', 'Fréquence explicitement saisie'),
        ('medications[0][therapeutic_class]', 'Famille fictive'),
        ('medications[0][inn]', 'DCI fictive'),
        ('medications[0][dosage]', 'Dose du document'),
        ('medications[0][frequency]', 'Fréquence du document'),
        ('parameters[0][name]', 'Pression artérielle'),
        ('parameters[0][status]', 'value'),
        ('parameters[0][value]', '125'),
        ('parameters[0][secondary_value]', '80'),
        ('parameters[0][unit]', 'mmHg'),
        ('assessment_pain[0][description]', 'Douleur'),
        ('assessment_pain[0][status]', 'absent'),
        ('assessment_pain[0][value]', 'valeur à supprimer'),
        ('assessment_pain[0][unit]', 'unité à supprimer'),
    ])
    for key, value in overrides.items():
        values.setlist(key, value if isinstance(value, list) else [value])
    return values


def test_eight_page_draft_round_trip_states_documents_and_publication(app, tmp_path):
    app.config['KINE_DOCUMENT_FOLDER'] = str(tmp_path)
    client = app.test_client()
    teacher_login(client)
    folder_id = _folder(client)

    page = client.get('/kine/cases/new')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert html.count('data-case-page=') == 8
    for title in ('Dossier clinique', 'Anamnèse', 'Bilans', 'Raisonnement clinique',
                  'Objectifs', 'Prescription', 'Éducation thérapeutique',
                  'Vérification finale'):
        assert title in html

    form = _authoring_form(folder_id)
    form.add('documents', (io.BytesIO(b'original-clinical-document'), 'bilan.pdf'))
    form.add('source_document', (io.BytesIO(b'original-source'), 'source.pdf'))
    created = client.post(
        '/kine/cases', data=form, content_type='multipart/form-data',
        headers={'Accept': 'application/json'},
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    case_id = created.get_json()['id']

    with app.app_context():
        case = db.session.get(PatientCase, case_id)
        assert case.authoring_status == 'draft'
        assert case.authoring_progress['current_page'] == 4
        assert case.authoring_progress['completed_pages'] == [1, 2]
        assert case.difficulty == 'medium' and case.planned_sessions == 12
        assert case.patient_record.identity['first_name'] == 'Camille'
        pressure = case.patient_record.reference_vitals['Pression artérielle']
        assert pressure['value'] == '125' and pressure['secondary_value'] == '80'
        pain = case.patient_record.tests['physiotherapy_assessment']['pain'][0]
        assert pain['status'] == 'absent' and 'value' not in pain and 'unit' not in pain
        assert case.patient_record.medications[0].dosage == 'Dose du document'
        assert case.structured_content['prescriptions']['medical']['diagnosis'] == 'Diagnostic prescription'
        assert {item.kind for item in case.documents} == {'source', 'clinical'}
        clinical = next(item for item in case.documents if item.kind == 'clinical')
        stable_id = clinical.stable_id
        before_document_ids = {item.stable_id for item in case.documents}
        draft = KineCaseVersion.query.filter_by(case_id=case_id, status='draft').one()
        snapshot = json.loads(draft.content_json)
        assert {item['stable_id'] for item in snapshot['case_documents']} == before_document_ids

    downloaded = client.get(f'/kine/cases/{case_id}/documents/{stable_id}')
    assert downloaded.status_code == 200
    assert downloaded.data == b'original-clinical-document'

    # An authoritative form submission clears removed values but keeps original files.
    edited = _authoring_form(
        folder_id, title='Cas fictif T05 édité', wizard_page='8',
        identity_first_name='', clinical_synthesis='',
    )
    edited.setlist('wizard_completed_pages', [str(value) for value in range(1, 8)])
    response = client.post(
        f'/kine/cases/{case_id}', data=edited,
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    with app.app_context():
        case = db.session.get(PatientCase, case_id)
        assert case.title.endswith('édité')
        assert case.patient_record.identity.get('first_name') in (None, '')
        assert case.structured_content['reasoning']['clinical_synthesis'] in (None, '')
        assert {item.stable_id for item in case.documents} == before_document_ids
        assert any(item.get('stable_id') == stable_id for item in case.patient_record.available_documents)

    published = client.post(f'/kine/cases/{case_id}/versions/publish', json={})
    assert published.status_code == 201
    with app.app_context():
        assert db.session.get(PatientCase, case_id).authoring_status == 'published'

    student_login(client)
    forbidden = client.get(f'/kine/cases/{case_id}/documents/{stable_id}')
    assert forbidden.status_code in (302, 401, 403)


def test_draft_validation_missing_fields_pressure_double_submit_and_refused_file(app, tmp_path):
    app.config['KINE_DOCUMENT_FOLDER'] = str(tmp_path)
    client = app.test_client()
    teacher_login(client)
    folder_id = _folder(client)

    partial = client.post('/kine/cases', data={
        'form_version': '3', 'case_number': 'T05-PARTIAL',
        'level': 'both', 'mode_availability': 'both', 'wizard_page': '1',
    }, headers={'Accept': 'application/json'})
    assert partial.status_code == 201
    case_id = partial.get_json()['id']
    publish = client.post(f'/kine/cases/{case_id}/versions/publish', json={})
    assert publish.status_code == 409
    assert {'Titre du cas absent.', 'Dossier pathologique absent.'} <= set(
        publish.get_json()['validation_issues']
    )

    invalid_pressure = _authoring_form(folder_id, case_number='T05-BP')
    invalid_pressure.setlist('parameters[0][secondary_value]', [''])
    response = client.post('/kine/cases', data=invalid_pressure, headers={'Accept': 'application/json'})
    assert response.status_code == 400
    assert 'deux valeurs' in response.get_json()['error']

    refused = _authoring_form(folder_id, case_number='T05-REFUSED')
    refused.add('documents', (io.BytesIO(b'not-allowed'), 'payload.exe'))
    response = client.post(
        '/kine/cases', data=refused, content_type='multipart/form-data',
        headers={'Accept': 'application/json'},
    )
    assert response.status_code == 400 and 'Format de fichier refusé' in response.get_json()['error']

    valid = _authoring_form(folder_id, case_number='T05-DOUBLE')
    first = client.post('/kine/cases', data=valid, headers={'Accept': 'application/json'})
    assert first.status_code == 201
    second = client.post(
        '/kine/cases', data=_authoring_form(folder_id, case_number='T05-DOUBLE'),
        headers={'Accept': 'application/json'},
    )
    assert second.status_code == 409
    with app.app_context():
        assert PatientCase.query.filter_by(case_number='T05-DOUBLE').count() == 1
        assert KineCaseDocument.query.filter_by(clinical_case_id=case_id).count() == 0


def test_pdf_import_keeps_source_and_uncertainty_without_inventing_data(app, tmp_path):
    class IncompletePdfAgent:
        def process_file(self, path, extension, case_number, specialty):
            assert extension == '.pdf' and specialty == 'kine'
            return {
                'case_number': 'T05-IMPORT-PDF',
                'patient_info': {},
                'extraction_uncertainties': [
                    'Valeur illisible dans le tableau des constantes.'
                ],
            }

    app.config.update(
        DOCUMENT_AGENT=IncompletePdfAgent(), KINE_IMPORT_FOLDER=str(tmp_path),
    )
    client = app.test_client()
    teacher_login(client)
    batch = client.post('/kine/case-imports', data={
        'documents': (io.BytesIO(b'%PDF-fictitious-incomplete'), 'incomplet.pdf'),
    }, content_type='multipart/form-data', headers={'Accept': 'application/json'})
    assert batch.status_code == 201
    processed = client.post(batch.get_json()['process_url'], json={'limit': 1}).get_json()
    draft = processed['drafts'][0]
    assert draft['status'] == 'incomplete'
    assert any('Valeur illisible' in issue for issue in draft['validation_issues'])
    source = client.get(draft['source_url'])
    assert source.status_code == 200 and source.data == b'%PDF-fictitious-incomplete'
    refused_validation = client.patch(draft['detail_url'], json={
        'action': 'validate', 'extracted_data': draft['extracted_data'],
    })
    assert refused_validation.status_code == 409

    invalid = client.post('/kine/case-imports', data={
        'documents': (io.BytesIO(b'no'), 'source.exe'),
    }, content_type='multipart/form-data', headers={'Accept': 'application/json'})
    assert invalid.status_code == 400
    assert 'Format non pris en charge' in invalid.get_json()['error']

    student_login(client)
    assert client.get(draft['source_url']).status_code in (302, 401, 403)

