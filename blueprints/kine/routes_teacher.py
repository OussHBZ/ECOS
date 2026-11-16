import json
import os
import tempfile
import hashlib
import mimetypes
from datetime import datetime
from io import BytesIO
import re
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from flask import current_app, jsonify, redirect, render_template, request, send_file, url_for

from kine_permissions import kine_permission_required, scoped_students, scoped_exams
from document_processor import DocumentExtractionAgent
from case_versions import save_draft, version_view
from effort_tests import normalize_effort_tests
from patient_personality import normalize_personality
from information_access import (
    ACCESS_MODES, IMPORTANCE_LEVELS, canonical as information_canonical,
    information_payload, value_type, case_information_values,
)
from models import (CaseInformation, KineCaseAvailability, KineCaseVersion,
                    ExamCaseVersion, KineCaseDocument)
from models import (
    Exam, Incident, Intervention, Medication, PathologyFolder, PatientCase,
    PatientRecord, Student, db,
)


CASE_DIFFICULTIES = {'easy', 'medium', 'hard'}
REHABILITATION_PHASES = {'hospitalisation', 'phase_ii', 'phase_iii'}
INFORMATION_STATES = {'value', 'ras', 'absent', 'not_evaluated', 'unknown'}
CASE_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'}
MAX_CASE_DOCUMENT_BYTES = 25 * 1024 * 1024
WIZARD_PAGES = (
    'dossier_clinique', 'anamnese', 'bilans', 'raisonnement_clinique',
    'objectifs', 'prescription', 'etp', 'verification_finale',
)

from . import kine_bp
from .common import (
    CASE_LEVELS, MODES, canonicalize_medical_tests, error,
    normalize_vital_parameters, parse_datetime, parse_indexed_form, payload,
    teacher_id, validate_vital_parameter_rows, wants_json,
)


def _document_storage_root():
    base = (
        current_app.config.get('KINE_DOCUMENT_FOLDER')
        or current_app.config.get('UPLOAD_FOLDER')
        or tempfile.gettempdir()
    )
    root = os.path.abspath(os.path.join(base, 'kine_case_documents'))
    os.makedirs(root, exist_ok=True)
    return root


def _document_descriptor(item):
    return {
        'stable_id': item.stable_id,
        'filename': item.original_filename,
        'kind': item.kind,
    }


def _store_case_uploads(case):
    """Store accepted originals once; return paths created by this transaction."""
    candidates = []
    for field, kind in (
        ('source_document', 'source'),
        ('medical_prescription_document', 'medical_prescription'),
        ('physiotherapy_prescription_document', 'physiotherapy_prescription'),
    ):
        item = request.files.get(field)
        if item and item.filename:
            candidates.append((item, kind))
    candidates.extend(
        (item, 'clinical') for item in request.files.getlist('documents')
        if item and item.filename
    )
    if not candidates:
        return []
    directory = os.path.abspath(os.path.join(_document_storage_root(), str(case.id)))
    os.makedirs(directory, exist_ok=True)
    created_paths = []
    try:
        for uploaded, kind in candidates:
            original = os.path.basename(uploaded.filename)
            extension = os.path.splitext(original)[1].lower()
            if extension not in CASE_DOCUMENT_EXTENSIONS:
                raise ValueError(
                    f'Format de fichier refusé pour « {original} ». '
                    'Utilisez PDF, DOC, DOCX, JPG, JPEG ou PNG.'
                )
            content = uploaded.read(MAX_CASE_DOCUMENT_BYTES + 1)
            if len(content) > MAX_CASE_DOCUMENT_BYTES:
                raise ValueError(f'Le fichier « {original} » dépasse 25 Mo.')
            stable_id = str(uuid4())
            safe_name = secure_filename(original) or f'document{extension}'
            stored_path = os.path.abspath(os.path.join(directory, f'{stable_id}_{safe_name}'))
            try:
                contained = os.path.commonpath((directory, stored_path)) == directory
            except ValueError:
                contained = False
            if not contained:
                raise ValueError('Chemin de document invalide.')
            with open(stored_path, 'xb') as stream:
                stream.write(content)
            created_paths.append(stored_path)
            db.session.add(KineCaseDocument(
                clinical_case=case, stable_id=stable_id, kind=kind,
                original_filename=original, stored_path=stored_path,
                sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                mime_type=uploaded.mimetype or mimetypes.guess_type(original)[0],
                created_by=teacher_id(),
            ))
        db.session.flush()
        record = case.patient_record or PatientRecord(clinical_case=case)
        legacy = [
            item for item in (record.available_documents or [])
            if not (isinstance(item, dict) and item.get('stable_id'))
        ]
        record.available_documents = legacy + [
            _document_descriptor(item) for item in case.documents if item.kind != 'source'
        ]
        db.session.add(record)
        return created_paths
    except Exception:
        for path in created_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise


def _remove_transaction_files(paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def _list_form_values(name):
    values = request.form.getlist(name)
    return [value.strip() for value in values if value and value.strip()]


def _structured_content(data, case=None):
    current = dict(case.structured_content if case else {})
    from criterion_evaluation import normalize_criteria
    if not request.is_json and 'criteria_json' in data:
        current['evaluation_criteria'] = normalize_criteria(json.loads(data['criteria_json']))
    if request.is_json:
        supplied = data.get('structured_content')
        if supplied is not None:
            if not isinstance(supplied, dict):
                raise ValueError('Le contenu structuré du cas doit être un objet.')
            if supplied.get('etp_associations', current.get('etp_associations', [])) != current.get('etp_associations', []):
                raise ValueError('Utilisez l’éditeur ETP pour associer et valider une fiche.')
            current.update(supplied)
        if 'rehabilitation_program' in current:
            from rehabilitation import normalize_rehabilitation
            current['rehabilitation_program'] = normalize_rehabilitation(current['rehabilitation_program'])
        if 'patient_personality' in current:
            current['patient_personality'] = normalize_personality(current['patient_personality'])
        current['evaluation_criteria'] = normalize_criteria(current.get('evaluation_criteria', []))
        return current
    current['patient_personality'] = normalize_personality({
        'enabled': data.get('personality_enabled') == 'true',
        **{key.removeprefix('personality_'): value for key, value in data.items() if key.startswith('personality_') and key != 'personality_enabled'},
        'transitions': parse_indexed_form('personality_transitions'),
    })
    current.update({
        'social_context': {
            'environment': data.get('social_environment'),
            'social_barriers': _list_form_values('social_barriers'),
            'social_barriers_other': data.get('social_barriers_other'),
            'professional_situation': data.get('professional_situation'),
            'family_support': data.get('family_support'),
            'daily_autonomy': data.get('daily_autonomy'),
            'social_objectives': data.get('social_objectives'),
        },
        'anamnese': {
            'onset': data.get('disease_onset'),
            'initial_reason': data.get('initial_reason'),
            'initial_symptoms': _list_form_values('initial_symptoms'),
            'initial_symptoms_other': data.get('initial_symptoms_other'),
            'evolution': data.get('disease_evolution'),
            'important_events': _list_form_values('important_events'),
            'care_already_received': _list_form_values('care_already_received'),
            'current_situation': data.get('current_situation'),
        },
        'diagnostic_context': {
            'associated_diagnoses': _list_form_values('associated_diagnoses'),
            'associated_diagnoses_other': data.get('associated_diagnoses_other'),
            'clinical_phase': data.get('clinical_phase'),
            'diagnosis_date': data.get('diagnosis_date'),
            'clinical_state': data.get('clinical_state'),
        },
        'reasoning': {
            'clinical_synthesis': data.get('clinical_synthesis'),
            'expected_physiotherapy_diagnosis': data.get('diagnosis'),
            'hypotheses': _repeatable(data, 'reasoning_hypotheses'),
            'safety_points': _repeatable(data, 'safety_points'),
        },
        'objectives': _repeatable(data, 'therapeutic_objectives'),
        'rehabilitation_prescription': {
            'modalities': _repeatable(data, 'rehabilitation_modalities'),
            'notes': data.get('rehabilitation_notes'),
            'integration_status': 'prepared_for_T09_T10',
        },
        'prescriptions': {
            'medical': {
                'diagnosis': data.get('medical_prescription_diagnosis'),
                'indication': data.get('medical_prescription_indication'),
                'objectives': data.get('medical_prescription_objectives'),
                'precautions': data.get('medical_prescription_precautions'),
                'contraindications': data.get('medical_prescription_contraindications'),
            },
            'physiotherapy': {
                'objectives': data.get('physiotherapy_prescription_objectives'),
                'care_type': data.get('physiotherapy_care_type'),
                'frequency': data.get('physiotherapy_frequency'),
                'session_duration': data.get('physiotherapy_session_duration'),
                'precautions': data.get('physiotherapy_precautions'),
                'contraindications': data.get('physiotherapy_contraindications'),
            },
        },
        'etp': {
            'items': _repeatable(data, 'etp_items'),
            'integration_status': 'prepared_for_T12',
        },
    })
    return current


def _validate_information_states(rows, label):
    for row in rows:
        state = str(row.get('status') or 'value')
        if state not in INFORMATION_STATES:
            raise ValueError(f'État invalide pour {label}.')
        row['status'] = state
        if state != 'value':
            # Preserve an explicit state without stale values reappearing.
            for key in ('value', 'secondary_value', 'unit'):
                row.pop(key, None)
        if (str(row.get('name') or '').lower() in ('pression artérielle', 'pa', 'blood pressure')
                and state == 'value'):
            if not row.get('value') or not row.get('secondary_value'):
                raise ValueError('La pression artérielle requiert deux valeurs.')


def _publication_issues(case):
    """Only structural authoring requirements; no clinical values are inferred."""
    issues = []
    for value, message in (
        (case.case_number, 'Numéro du cas absent.'),
        (case.title, 'Titre du cas absent.'),
        (case.folder_id, 'Dossier pathologique absent.'),
        (case.level, 'Niveau absent.'),
        (case.mode_availability, "Mode d’utilisation absent."),
    ):
        if value in (None, ''):
            issues.append(message)
    return issues


@kine_bp.route('/teacher')
@kine_permission_required('cases.manage')
def teacher_kine_home():
    return redirect(url_for('kine.teacher_dashboard'))


def _case_payload(case):
    return {
        'id': case.id, 'case_number': case.case_number, 'title': case.title,
        'specialty': case.specialty,
        'folder_id': case.folder_id, 'level': case.level,
        'mode_availability': case.mode_availability,
        'pedagogical_objectives': case.pedagogical_objectives,
        'emotional_state': case.emotional_state, 'is_archived': case.is_archived,
        'difficulty': case.difficulty, 'subpathology': case.subpathology,
        'rehabilitation_phase': case.rehabilitation_phase,
        'planned_sessions': case.planned_sessions,
        'pedagogical_summary': case.pedagogical_summary,
        'authoring_status': case.authoring_status,
        'authoring_progress': case.authoring_progress,
    }


def _case_form_payload(case):
    """Return every persisted case field in the extraction/form schema."""
    record = case.patient_record
    stored_tests = canonicalize_medical_tests(record.tests or {}) if record else {}
    categorized_tests = {
        key: value for key, value in stored_tests.items()
        if key not in ('physiotherapy_assessment', 'vital_parameters', 'exertion_kinetics', 'effort_tests')
    }
    assessment = stored_tests.get('physiotherapy_assessment') or {}
    return {
        **_case_payload(case),
        'patient_info': record.identity or {} if record else {},
        'medical_context': record.medical_context or {} if record else {},
        'history': record.medical_history or {} if record else {},
        'comorbidities': record.comorbidities or [] if record else [],
        'procedures': [{
            'type': item.intervention_type,
            'date': item.timing,
            'complications': item.complications,
        } for item in (record.interventions if record else [])],
        'medications': [{
            'therapeutic_class': item.therapeutic_class, 'inn': item.inn,
            'dosage': item.dosage, 'frequency': item.frequency,
            'effect': item.effect, 'physiotherapy_precautions': item.physiotherapy_precautions,
        } for item in (record.medications if record else [])],
        'tests': categorized_tests,
        'effort_tests': stored_tests.get('effort_tests') or [],
        'vital_parameters': normalize_vital_parameters(stored_tests),
        'reference_vitals': record.reference_vitals or {} if record else {},
        'prescriptions': {
            'medical': record.medical_prescription if record else None,
            'physiotherapy': record.physiotherapy_prescription if record else None,
        },
        'available_documents': record.available_documents or [] if record else [],
        'physiotherapy_assessment': assessment,
        'incidents': [_incident_payload(item) for item in case.incidents],
        'diagnosis': case.diagnosis,
        'directives': case.directives,
        'evaluation_checklist': case.evaluation_checklist or [],
        'information_access': [information_payload(item) for item in case.information_items],
        'structured_content': case.structured_content,
        'case_documents': [{
            **_document_descriptor(item), 'size_bytes': item.size_bytes,
            'sha256': item.sha256,
            'download_url': url_for('kine.case_document', case_id=case.id, stable_id=item.stable_id),
        } for item in case.documents],
    }


def _repeatable(data, name):
    value = data.get(name) if hasattr(data, 'get') else None
    if isinstance(value, list):
        return value
    rows = parse_indexed_form(name)
    if rows or request.form.get('form_version') in ('2', '3'):
        return rows
    extracted = _extracted_form_data()
    return extracted.get(name, []) if isinstance(extracted.get(name), list) else []


def _extracted_form_data():
    raw = request.form.get('extracted_case_data') if not request.is_json else None
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _record_data(data):
    if request.is_json:
        record_data = data.get('patient_record') or {}
        tests = record_data.get('tests') or {}
        validate_vital_parameter_rows(tests.get('vital_parameters') or [])
        if 'effort_tests' in tests:
            tests['effort_tests'] = normalize_effort_tests(tests['effort_tests'])
        return record_data
    extracted = _extracted_form_data()
    prescriptions = extracted.get('prescriptions') or {}
    base = {
        'identity': extracted.get('patient_info') or {},
        'medical_context': extracted.get('medical_context') or {},
        'medical_history': extracted.get('history') or {},
        'comorbidities': extracted.get('comorbidities') or [],
        'tests': extracted.get('tests') or {},
        'reference_vitals': extracted.get('reference_vitals') or {},
        'medical_prescription': prescriptions.get('medical'),
        'physiotherapy_prescription': prescriptions.get('physiotherapy'),
        'available_documents': extracted.get('available_documents') or [],
    }
    assessment = {}
    for domain in ('general_condition', 'pain', 'dyspnea', 'respiratory', 'muscular',
                   'joint', 'neurological', 'balance', 'gait', 'scar', 'exertion_parameters'):
        assessment[domain] = parse_indexed_form(f'assessment_{domain}')
        _validate_information_states(assessment[domain], f'le bilan {domain}')
    tests = _repeatable(data, 'tests')
    parameters = _repeatable(data, 'parameters')
    _validate_information_states(tests, 'les examens complémentaires')
    _validate_information_states(parameters, 'les constantes initiales')
    # Unlike legacy extracted repeaters, an empty structured list is meaningful:
    # it means the teacher deleted every vital-parameter row.
    vital_parameters = parse_indexed_form('vital_parameters')
    validate_vital_parameter_rows(vital_parameters)
    form_record = {
        'identity': {
            'name': data.get('identity_name'),
            'first_name': data.get('identity_first_name'),
            'last_name': data.get('identity_last_name'),
            'age': data.get('identity_age'),
            'gender': data.get('identity_gender'), 'family_situation': data.get('family_situation'),
            'occupation': data.get('occupation'), 'height_cm': data.get('height_cm'),
            'weight_kg': data.get('weight_kg'), 'bmi': data.get('bmi'),
            'social_context': data.get('social_context'),
            'housing': data.get('housing'),
            'physical_activity': data.get('physical_activity'),
            'physical_activity_other': data.get('physical_activity_other'),
            'tobacco': data.get('tobacco'), 'tobacco_details': data.get('tobacco_details'),
            'alcohol': data.get('alcohol'), 'alcohol_details': data.get('alcohol_details'),
            'diet': data.get('diet'),
        },
        'medical_context': {
            'main_diagnosis': (
                data.get('medical_diagnosis')
                if data.get('form_version') == '3' else data.get('diagnosis')
            ),
            'illness_history': data.get('illness_history'),
            'admission_reason': data.get('initial_reason'),
            'associated_diagnoses': _list_form_values('associated_diagnoses'),
            'clinical_phase': data.get('clinical_phase'),
            'diagnosis_date': data.get('diagnosis_date'),
            'clinical_state': data.get('clinical_state'),
        },
        'medical_history': {
            'cardiovascular': data.get('history_cardiovascular'), 'medical': data.get('history_medical'),
            'surgical': data.get('history_surgical'), 'allergies': data.get('history_allergies'),
            'risk_factors': data.get('risk_factors'),
            'personal': data.get('history_personal'),
        },
        'tests': {
            'items': tests,
            'physiotherapy_assessment': assessment,
            'vital_parameters': vital_parameters,
        },
        'reference_vitals': {
            item.get('name'): {
                'value': item.get('value'),
                'secondary_value': item.get('secondary_value'),
                'unit': item.get('unit'),
                'condition': item.get('condition'),
                'status': item.get('status') or 'value',
            }
            for item in parameters if item.get('name')
        },
        'medical_prescription': data.get('medical_prescription'),
        'physiotherapy_prescription': data.get('physiotherapy_prescription'),
        'available_documents': [],
    }
    authoritative_form = data.get('form_version') in ('2', '3')
    for section in ('identity', 'medical_context', 'medical_history', 'reference_vitals'):
        if authoritative_form and section == 'reference_vitals':
            base[section] = form_record[section]
        else:
            base.setdefault(section, {}).update({key: value for key, value in form_record[section].items() if authoritative_form or value not in (None, '')})
    form_tests = form_record['tests']
    if tests or authoritative_form:
        categorized = {key: [] for key in ('cardiac', 'vascular', 'biological', 'imaging', 'other')}
        for item in tests:
            if not isinstance(item, dict):
                categorized['other'].append(item)
                continue
            category = item.get('category') if item.get('category') in categorized else 'other'
            categorized[category].append({key: value for key, value in item.items() if key != 'category'})
        # Legacy result lists (e.g. functional) are also displayed by the form.
        # Remove their old copies before saving the edited visible rows.
        if authoritative_form:
            base['tests'] = {key: value for key, value in base['tests'].items() if not isinstance(value, list)}
        # Preserve values outside the visible medical-result categories.
        for category in categorized:
            base['tests'][category] = categorized[category]
        base['tests'].pop('items', None)
    if any(assessment.values()) or authoritative_form:
        base.setdefault('tests', {})['physiotherapy_assessment'] = assessment
    if form_tests.get('vital_parameters') or authoritative_form:
        base.setdefault('tests', {})['vital_parameters'] = form_tests['vital_parameters']
        base['tests'].pop('exertion_kinetics', None)
    if authoritative_form or 'effort_tests' in data:
        effort = _repeatable(data, 'effort_tests')
        measures = _repeatable(data, 'effort_measurements')
        for test in effort:
            test['measurements'] = []
        by_id = {test.get('id'): test for test in effort}
        for row in measures:
            test_id = row.pop('test_id', None)
            if test_id not in by_id:
                raise ValueError('Une mesure vise un test à l’effort absent.')
            if 'patient_knows' in row:
                row['patient_knows'] = row['patient_knows'] == 'true'
            by_id[test_id]['measurements'].append(row)
        base['tests']['effort_tests'] = normalize_effort_tests(effort)
    base['tests'] = canonicalize_medical_tests(base.get('tests') or {})
    for field in ('medical_prescription', 'physiotherapy_prescription'):
        if form_record.get(field) or authoritative_form:
            base[field] = form_record[field]
    if form_record['available_documents']:
        base['available_documents'] = list(dict.fromkeys((base.get('available_documents') or []) + form_record['available_documents']))
    return base


def _apply_case(case, data):
    case.case_number = str(data.get('case_number') or case.case_number or '').strip()
    if not case.case_number:
        raise ValueError('Le numéro du cas est obligatoire.')
    with db.session.no_autoflush:
        duplicate = PatientCase.query.filter_by(case_number=case.case_number).first()
    if duplicate and duplicate.id != case.id:
        raise ValueError('Ce numéro de cas existe déjà. Choisissez un autre numéro.')
    case.specialty = 'kine'
    case.title = str(data.get('title') or case.title or '').strip() or None
    case.folder_id = int(data.get('folder_id')) if data.get('folder_id') else None
    if case.folder_id and not PathologyFolder.query.filter_by(id=case.folder_id, specialty='kine', is_archived=False).first():
        raise ValueError('Sélectionnez un dossier pathologique actif de kinésithérapie.')
    case.level = str(data.get('level') or case.level or 'both').lower()
    case.mode_availability = str(data.get('mode_availability') or case.mode_availability or 'both').lower()
    if case.level not in CASE_LEVELS:
        raise ValueError('Invalid case level')
    if case.mode_availability not in MODES:
        raise ValueError('Invalid mode availability')
    case.pedagogical_objectives = data.get('pedagogical_objectives')
    case.emotional_state = data.get('emotional_state') or 'cooperative'
    difficulty = str(data.get('difficulty') or case.difficulty or '').lower() or None
    if difficulty and difficulty not in CASE_DIFFICULTIES:
        raise ValueError('Difficulté invalide.')
    case.difficulty = difficulty
    case.subpathology = data.get('subpathology') or None
    phase = str(data.get('rehabilitation_phase') or case.rehabilitation_phase or '').lower() or None
    if phase and phase not in REHABILITATION_PHASES:
        raise ValueError('Phase de rééducation invalide.')
    case.rehabilitation_phase = phase
    sessions = data.get('planned_sessions')
    if sessions not in (None, ''):
        try:
            sessions = int(sessions)
        except (TypeError, ValueError):
            raise ValueError('Le nombre de séances doit être un entier.')
        if sessions < 0:
            raise ValueError('Le nombre de séances ne peut pas être négatif.')
    else:
        sessions = None
    case.planned_sessions = sessions
    case.pedagogical_summary = data.get('pedagogical_summary') or None
    extracted = _extracted_form_data()
    if 'diagnosis' in data:
        case.diagnosis = data.get('diagnosis') or None
    elif case.diagnosis is None and extracted.get('diagnosis'):
        case.diagnosis = extracted.get('diagnosis')
    if data.get('form_version') in ('2', '3'):
        case.diagnosis = data.get('diagnosis') or None
    case.directives = data.get('directives')
    checklist = _repeatable(data, 'evaluation_checklist')
    if checklist or data.get('form_version') in ('2', '3') or 'evaluation_checklist' in data:
        case.evaluation_checklist = checklist
    if data.get('form_version') == '3' or request.is_json and 'structured_content' in data:
        case.structured_content = _structured_content(data, case)
        current_page = data.get('wizard_page')
        try:
            current_page = max(1, min(8, int(current_page or 1)))
        except (TypeError, ValueError):
            current_page = 1
        completed = sorted({
            int(value) for value in (
                request.form.getlist('wizard_completed_pages') if not request.is_json
                else data.get('wizard_completed_pages') or []
            ) if str(value).isdigit() and 1 <= int(value) <= 8
        })
        case.authoring_progress = {
            'current_page': current_page,
            'completed_pages': completed,
            'page_keys': list(WIZARD_PAGES),
        }
        case.authoring_status = 'draft'


def _apply_record(case, data, replace_children=True):
    record_data = _record_data(data)
    source_values_before = dict(case_information_values(case))
    record = case.patient_record or PatientRecord(clinical_case=case)
    for field in ('identity', 'medical_context', 'medical_history', 'comorbidities', 'tests',
                  'reference_vitals', 'medical_prescription', 'physiotherapy_prescription', 'available_documents'):
        if field in record_data:
            value = record_data.get(field)
            if field == 'tests':
                value = canonicalize_medical_tests(value or {})
            if value is None:
                if field in ('comorbidities', 'available_documents'):
                    value = []
                elif field in ('identity', 'medical_context', 'medical_history', 'tests', 'reference_vitals'):
                    value = {}
            setattr(record, field, value)
    # Existing original uploads remain attached when an edit submits no new
    # files.  Only the legacy free-text descriptors are supplied by the form;
    # protected document descriptors are rebuilt from server-side rows.
    if case.documents:
        legacy_documents = [
            item for item in (record.available_documents or [])
            if not (isinstance(item, dict) and item.get('stable_id'))
        ]
        record.available_documents = legacy_documents + [
            _document_descriptor(item) for item in case.documents
            if item.kind != 'source'
        ]
    if replace_children:
        record.interventions.clear()
        for item in _repeatable(data, 'procedures'):
            date_value = item.get('date')
            record.interventions.append(Intervention(
                intervention_type=item.get('type') or item.get('intervention_type') or 'Procedure',
                timing=date_value,
                complications=item.get('complications'),
            ))
        record.medications.clear()
        for item in _repeatable(data, 'medications'):
            record.medications.append(Medication(
                therapeutic_class=item.get('therapeutic_class') or 'Unspecified', inn=item.get('inn'),
                dosage=item.get('dosage'), frequency=item.get('frequency'),
                effect=item.get('effect'), physiotherapy_precautions=item.get('precautions') or item.get('physiotherapy_precautions'),
            ))
    db.session.add(record)
    # Removing a source fact also removes its working policy, even when that
    # policy was authored. Custom facts without a source row remain untouched.
    source_values_after = dict(case_information_values(case))
    removed_paths = source_values_before.keys() - source_values_after.keys()
    for item in list(case.information_items):
        if item.path in removed_paths:
            db.session.delete(item)
        elif item.path.startswith('effort_tests.') and item.path in source_values_before and item.path in source_values_after:
            before, after = source_values_before[item.path], source_values_after[item.path]
            if before.get('patient_knows') != after.get('patient_knows'):
                item.patient_knows = after.get('patient_knows') is True
            if item.provenance == 'reconstructed_current_policy':
                item.access_mode = 'question' if after.get('actor') == 'patient' else 'examination'
                item.label = after.get('name') or item.label
                item.disclosure_conditions_json = information_canonical({'terms': [item.label]})


@kine_bp.route('/cases', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def cases_collection():
    if request.method == 'GET':
        cases = PatientCase.query.filter_by(specialty='kine').order_by(PatientCase.created_at.desc()).all()
        return jsonify({'cases': [_case_payload(case) for case in cases]})
    data = payload()
    if PatientCase.query.filter_by(case_number=str(data.get('case_number') or '').strip()).first():
        return error('Ce numéro de cas existe déjà. Choisissez un autre numéro.', 409)
    case = PatientCase()
    created_paths = []
    try:
        _apply_case(case, data)
        db.session.add(case)
        _apply_record(case, data)
        db.session.flush()
        for item in _repeatable(data, 'incidents'):
            case.incidents.append(Incident(
                trigger_description=item.get('trigger_description'), trigger_condition=item.get('trigger_condition') or '',
                scripted_reaction=item.get('scripted_reaction') or '', severity=item.get('severity') or 'minor',
            ))
        created_paths = _store_case_uploads(case)
        save_draft(case)
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        _remove_transaction_files(created_paths)
        return error(str(exc))
    except IntegrityError:
        db.session.rollback()
        _remove_transaction_files(created_paths)
        return error('Enregistrement impossible : le numéro du cas existe déjà ou une référence est invalide.', 409)
    current_page = case.authoring_progress.get('current_page', 1)
    redirect_url = (
        url_for('kine.case_item', case_id=case.id, page=current_page)
        if current_page > 1 else url_for('kine.case_item', case_id=case.id)
    )
    if wants_json():
        return jsonify(_case_payload(case) | {'redirect_url': redirect_url}), 201
    return redirect(redirect_url)


@kine_bp.route('/cases/new')
@kine_permission_required('cases.manage')
def new_case_form():
    return render_template('case_form_kine.html', clinical_case=None,
                           folders=PathologyFolder.query.filter_by(specialty='kine', is_archived=False).all(),
                           form_action=url_for('kine.cases_collection'),
                           extraction_url=url_for('kine.extract_case_document'),
                           wizard_page=1, wizard_pages=WIZARD_PAGES,
                           publication_issues=[])


@kine_bp.route('/cases/extract', methods=['POST'])
@kine_permission_required('cases.manage')
def extract_case_document():
    document = request.files.get('source_document')
    if not document or not document.filename:
        return error('A source document is required')
    extension = os.path.splitext(document.filename)[1].lower()
    if extension not in ('.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png'):
        return error('Unsupported document type')
    configured_agent = current_app.config.get('DOCUMENT_AGENT')
    if not configured_agent:
        return error("L'extraction automatique des documents n'est pas configurée.", 503)
    # The processor keeps per-file state, so each request needs its own instance.
    agent = (
        DocumentExtractionAgent(llm_client=configured_agent.llm_client)
        if isinstance(configured_agent, DocumentExtractionAgent)
        else configured_agent
    )
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temporary:
            temporary_path = temporary.name
        document.save(temporary_path)
        extracted = agent.process_file(
            temporary_path, extension,
            request.form.get('case_number') or 'kine-preview', 'kine',
        )
        return jsonify({'extracted_data': extracted})
    except Exception as exc:
        return error(f"Échec de l'extraction du document : {exc}", 502)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


@kine_bp.route('/cases/<int:case_id>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@kine_permission_required('cases.manage')
def case_item(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'GET':
        if wants_json():
            return jsonify(_case_payload(case))
        return render_template('case_form_kine.html', clinical_case=case,
                               folders=PathologyFolder.query.filter_by(specialty='kine', is_archived=False).all(),
                               form_action=url_for('kine.case_item', case_id=case.id),
                               extraction_url=url_for('kine.extract_case_document'),
                               initial_case_data=_case_form_payload(case),
                               download_url=url_for('kine.download_case', case_id=case.id),
                               wizard_page=max(1, min(8, request.args.get('page', type=int) or case.authoring_progress.get('current_page', 1))),
                               wizard_pages=WIZARD_PAGES,
                               publication_issues=_publication_issues(case))
    if request.method == 'DELETE':
        if case.simulation_sessions or KineCaseVersion.query.filter_by(case_id=case.id, status='published').first():
            return error('Ce cas possède des simulations et doit être archivé plutôt que supprimé.', 409)
        for exam in list(case.kine_exams):
            exam.cases.remove(case)
        KineCaseVersion.query.filter_by(case_id=case.id, status='draft').delete()
        db.session.delete(case)
        db.session.commit()
        return ('', 204)
    data = payload()
    created_paths = []
    try:
        _apply_case(case, data)
        _apply_record(case, data, replace_children=True)
        case.incidents.clear()
        for item in _repeatable(data, 'incidents'):
            case.incidents.append(Incident(
                trigger_description=item.get('trigger_description'),
                trigger_condition=item.get('trigger_condition') or '',
                scripted_reaction=item.get('scripted_reaction') or '',
                severity=item.get('severity') if item.get('severity') in ('minor', 'major') else 'minor',
            ))
        created_paths = _store_case_uploads(case)
        save_draft(case)
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        _remove_transaction_files(created_paths)
        return error(str(exc))
    except IntegrityError:
        db.session.rollback()
        _remove_transaction_files(created_paths)
        return error('Enregistrement impossible : le numéro du cas existe déjà ou une référence est invalide.', 409)
    current_page = case.authoring_progress.get('current_page', 1)
    redirect_url = (
        url_for('kine.case_item', case_id=case.id, page=current_page)
        if current_page > 1 else url_for('kine.case_item', case_id=case.id)
    )
    if wants_json():
        return jsonify(_case_payload(case) | {'redirect_url': redirect_url})
    return redirect(redirect_url)


@kine_bp.route('/cases/<int:case_id>/documents/<stable_id>')
@kine_permission_required('cases.manage')
def case_document(case_id, stable_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    item = KineCaseDocument.query.filter_by(
        clinical_case_id=case.id, stable_id=stable_id,
    ).first_or_404()
    expected_root = os.path.abspath(os.path.join(_document_storage_root(), str(case.id)))
    from storage_paths import upload_path
    stored_path = upload_path(item.stored_path)
    try:
        contained = os.path.commonpath((expected_root, stored_path)) == expected_root
    except ValueError:
        contained = False
    if not contained:
        return error('Chemin de document invalide.', 404)
    if not os.path.isfile(stored_path):
        return error('Document original introuvable.', 404)
    if os.path.getsize(stored_path) != item.size_bytes:
        return error('Intégrité du document original invalide.', 409)
    with open(stored_path, 'rb') as stream:
        if hashlib.sha256(stream.read()).hexdigest() != item.sha256:
            return error('Intégrité du document original invalide.', 409)
    return send_file(
        stored_path, as_attachment=True, download_name=item.original_filename,
        mimetype=item.mime_type or 'application/octet-stream',
    )


def _policy_values(data, current=None):
    path = str(data.get('path') if data.get('path') is not None else getattr(current, 'path', '')).strip()
    if not path or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,500}', path):
        raise ValueError("Le chemin d'information est invalide.")
    if current is not None and path != current.path:
        raise ValueError("Le chemin stable d'une information existante ne peut pas être modifié.")
    if 'value' in data:
        value = data['value']
    elif current is not None:
        value = json.loads(current.value_json)
    else:
        raise ValueError("La valeur de l'information est requise.")
    detected_type = value_type(value)
    if data.get('value_type') not in (None, detected_type):
        raise ValueError("Le type déclaré ne correspond pas à la valeur.")
    access_mode = str(data.get('access_mode') or getattr(current, 'access_mode', '')).strip()
    if access_mode not in ACCESS_MODES:
        raise ValueError("Mode d'accès invalide.")
    importance = str(data.get('importance') or getattr(current, 'importance', 'complementary')).strip()
    if importance not in IMPORTANCE_LEVELS:
        raise ValueError("Importance invalide.")
    level_rules = data.get('level_rules')
    if level_rules is None:
        level_rules = json.loads(current.level_rules_json) if current else {}
    if not isinstance(level_rules, dict) or set(level_rules) - {'licence', 'master'}:
        raise ValueError('Les différences de niveau doivent viser Licence ou Master.')
    for rule in level_rules.values():
        if not isinstance(rule, dict) or set(rule) - {'access_mode'}:
            raise ValueError('Une règle de niveau ne peut remplacer que le mode d’accès.')
        if rule.get('access_mode') not in ACCESS_MODES:
            raise ValueError("Mode d'accès de niveau invalide.")
    if path.startswith(('evaluation_expectations', 'expected_physiotherapy_diagnosis')) and (access_mode != 'evaluation_reserved' or any(rule['access_mode'] != 'evaluation_reserved' for rule in level_rules.values())):
        raise ValueError('Les réponses attendues restent réservées à l’évaluation.')
    conditions = data.get('disclosure_conditions')
    if conditions is None:
        conditions = json.loads(current.disclosure_conditions_json) if current else {}
    if not isinstance(conditions, dict) or set(conditions) - {'terms', 'requires_information'}:
        raise ValueError('Conditions de divulgation invalides.')
    if 'terms' in conditions and (not isinstance(conditions['terms'], list)
                                  or not all(isinstance(item, str) and item.strip() for item in conditions['terms'])):
        raise ValueError('Les termes de divulgation doivent être une liste de textes non vides.')
    if 'requires_information' in conditions and (
            not isinstance(conditions['requires_information'], list)
            or not all(isinstance(item, str) and item.strip() for item in conditions['requires_information'])):
        raise ValueError('Les prérequis doivent être des identifiants stables.')
    if 'patient_knows' in data:
        patient_knows = data['patient_knows']
        if patient_knows not in (True, False, None):
            raise ValueError('La connaissance du patient doit être vraie, fausse ou indéterminée.')
    else:
        patient_knows = current.patient_knows if current else None
    return {
        'path': path,
        'label': str(data.get('label') or getattr(current, 'label', '') or path.rsplit('.', 1)[-1]).strip(),
        'value_json': information_canonical(value), 'value_type': detected_type,
        'access_mode': access_mode, 'patient_knows': patient_knows,
        'importance': importance, 'level_rules_json': information_canonical(level_rules),
        'disclosure_conditions_json': information_canonical(conditions),
        'provenance': 'authored',
    }


@kine_bp.route('/cases/<int:case_id>/information', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def case_information_collection(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'GET':
        return jsonify({'information': [information_payload(item) for item in case.information_items]})
    data = payload()
    try:
        values = _policy_values(data)
        if CaseInformation.query.filter_by(clinical_case_id=case.id, path=values['path']).first():
            return error('Une information utilise déjà ce chemin stable.', 409)
        item = CaseInformation(clinical_case=case, stable_id=str(uuid4()), **values)
        db.session.add(item)
        save_draft(case)
        db.session.commit()
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        db.session.rollback()
        return error(str(exc))
    return jsonify(information_payload(item)), 201


@kine_bp.route('/cases/<int:case_id>/information/<stable_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
@kine_permission_required('cases.manage')
def case_information_item(case_id, stable_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    item = CaseInformation.query.filter_by(
        clinical_case_id=case.id, stable_id=stable_id,
    ).first_or_404()
    if request.method == 'GET':
        return jsonify(information_payload(item))
    if request.method == 'DELETE':
        if item.provenance == 'reconstructed_current_policy':
            return error("Supprimez la valeur clinique source plutôt que sa seule règle d'accès.", 409)
        db.session.delete(item)
        save_draft(case)
        db.session.commit()
        return ('', 204)
    try:
        for key, value in _policy_values(payload(), item).items():
            setattr(item, key, value)
        save_draft(case)
        db.session.commit()
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        db.session.rollback()
        return error(str(exc))
    return jsonify(information_payload(item))


@kine_bp.route('/cases/<int:case_id>/download')
@kine_permission_required('cases.manage')
def download_case(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    content = json.dumps(_case_form_payload(case), ensure_ascii=False, indent=2, default=str).encode('utf-8')
    return send_file(
        BytesIO(content), mimetype='application/json; charset=utf-8', as_attachment=True,
        download_name=f"cas_kine_{case.case_number}.json",
    )


@kine_bp.route('/cases/<int:case_id>/lifecycle', methods=['POST'])
@kine_permission_required('cases.manage')
def case_lifecycle(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    action = request.form.get('action') or (request.get_json(silent=True) or {}).get('action')
    if action == 'archive':
        case.is_archived = True
    elif action == 'restore':
        case.is_archived = False
    elif action == 'delete':
        if case.simulation_sessions or KineCaseVersion.query.filter_by(case_id=case.id, status='published').first():
            return error("Ce cas possède des simulations et doit être archivé plutôt que supprimé.", 409)
        for exam in list(case.kine_exams):
            exam.cases.remove(case)
        KineCaseVersion.query.filter_by(case_id=case.id, status='draft').delete()
        db.session.delete(case)
        db.session.commit()
        return redirect(url_for('kine.teacher_dashboard')) if not wants_json() else ('', 204)
    else:
        return error("Action de gestion du cas invalide.")
    db.session.commit()
    if wants_json():
        return jsonify(_case_payload(case) | {'is_archived': case.is_archived})
    return redirect(url_for('kine.teacher_dashboard') + '#tous-les-cas')


@kine_bp.route('/cases/<int:case_id>/incidents', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def case_incidents(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    if request.method == 'GET':
        if wants_json():
            return jsonify({'incidents': [_incident_payload(item) for item in case.incidents]})
        edited = None
        if request.args.get('edit'):
            try:
                edited = Incident.query.filter_by(id=int(request.args['edit']), clinical_case_id=case.id).first()
            except ValueError:
                edited = None
        return render_template('incident_manager.html', clinical_case=case, incidents=case.incidents,
                               edited_incident=edited,
                               incident_form_action=url_for('kine.incident_item', incident_id=edited.id) if edited else url_for('kine.case_incidents', case_id=case.id))
    data = payload()
    if not data.get('trigger_condition') or not data.get('scripted_reaction'):
        return error('Trigger condition and scripted reaction are required')
    incident = Incident(clinical_case=case, trigger_description=data.get('trigger_description'),
                        trigger_condition=data.get('trigger_condition'), scripted_reaction=data.get('scripted_reaction'),
                        severity=data.get('severity') if data.get('severity') in ('minor', 'major') else 'minor')
    db.session.add(incident)
    save_draft(case)
    db.session.commit()
    return jsonify(_incident_payload(incident)), 201


def _incident_payload(incident):
    return {'id': incident.id, 'case_id': incident.clinical_case_id,
            'trigger_description': incident.trigger_description, 'trigger_condition': incident.trigger_condition,
            'scripted_reaction': incident.scripted_reaction, 'severity': incident.severity}


@kine_bp.route('/incidents/<int:incident_id>', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
@kine_permission_required('cases.manage')
def incident_item(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    if incident.clinical_case.specialty != 'kine':
        return error('Not a kine incident', 404)
    if request.method == 'DELETE' or (request.method == 'POST' and request.form.get('_action') == 'delete'):
        case = incident.clinical_case
        db.session.delete(incident)
        save_draft(case)
        db.session.commit()
        return ('', 204)
    data = payload()
    for field in ('trigger_description', 'trigger_condition', 'scripted_reaction'):
        if data.get(field) is not None:
            setattr(incident, field, data.get(field))
    if data.get('severity') in ('minor', 'major'):
        incident.severity = data.get('severity')
    save_draft(incident.clinical_case)
    db.session.commit()
    return jsonify(_incident_payload(incident))


def _exam_payload(exam):
    return {'id': exam.id, 'name': exam.name, 'instructions': exam.instructions,
            'start_at': exam.start_at.isoformat() + 'Z', 'end_at': exam.end_at.isoformat() + 'Z',
            'max_duration_minutes': exam.max_duration_minutes,
            'case_ids': [case.id for case in exam.cases],
            'case_versions': [{
                'case_id': selection.case_id,
                'version_id': selection.version_id,
                'version_number': selection.version.number,
                'provenance': selection.provenance,
            } for selection in sorted(exam.case_version_selections, key=lambda item: item.case_id)],
            'student_ids': [student.id for student in exam.students],
            'students': [{
                'id': student.id,
                'name': (student.name or '').strip() or f"Étudiant {student.student_code}",
                'student_code': student.student_code,
                'level': student.level,
                'group_name': student.group_name,
                'class_name': student.class_name,
            } for student in sorted(
                exam.students, key=lambda item: ((item.name or '').lower(), item.student_code)
            )],
            'group_names': exam.group_names or [],
            'locked': _exam_is_locked(exam)}


def _exam_is_locked(exam):
    """An exam becomes immutable at opening or as soon as an attempt exists."""
    return exam.is_locked


@kine_bp.route('/exams', methods=['GET', 'POST'])
@kine_permission_required('exams.manage')
def exams_collection():
    if request.method == 'GET':
        return jsonify({'exams': [_exam_payload(exam) for exam in scoped_exams().order_by(Exam.start_at.desc()).all()]})
    exam = Exam(created_by=teacher_id())
    db.session.add(exam)
    try:
        _apply_exam(exam, payload())
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback(); return error(str(exc))
    return jsonify(_exam_payload(exam)), 201


def _apply_exam(exam, data):
    exam.name = str(data.get('name') or exam.name or '').strip()
    if not exam.name:
        raise ValueError("Le nom de l’examen est obligatoire.")
    exam.instructions = data.get('instructions')
    browser_offset = data.get('timezone_offset_minutes')
    exam.start_at = parse_datetime(data.get('start_at') or exam.start_at, 'start_at', browser_offset)
    exam.end_at = parse_datetime(data.get('end_at') or exam.end_at, 'end_at', browser_offset)
    if exam.end_at <= exam.start_at:
        raise ValueError("La fermeture de l’examen doit être postérieure à son ouverture.")
    exam.max_duration_minutes = int(data.get('max_duration_minutes') or exam.max_duration_minutes or 0)
    if exam.max_duration_minutes <= 0:
        raise ValueError("La durée de l’examen doit être positive.")
    get_list = data.getlist if hasattr(data, 'getlist') else lambda key: data.get(key)
    case_ids = get_list('case_ids')
    case_version_ids = get_list('case_version_ids')
    student_ids = get_list('student_ids')
    group_names = get_list('group_names')
    if case_ids is not None and not isinstance(case_ids, list): case_ids = [case_ids]
    if case_version_ids is not None and not isinstance(case_version_ids, list): case_version_ids = [case_version_ids]
    if student_ids is not None and not isinstance(student_ids, list): student_ids = [student_ids]
    if group_names is not None and not isinstance(group_names, list): group_names = [group_names]
    try:
        case_ids = list(dict.fromkeys(int(value) for value in case_ids or []))
        case_version_ids = list(dict.fromkeys(int(value) for value in case_version_ids or []))
        student_ids = list(dict.fromkeys(int(value) for value in student_ids or []))
    except (TypeError, ValueError):
        raise ValueError('La sélection des cas ou des étudiants est invalide.')
    if case_version_ids:
        versions = KineCaseVersion.query.filter(
            KineCaseVersion.id.in_(case_version_ids), KineCaseVersion.status == 'published'
        ).all()
        if len(versions) != len(case_version_ids) or len({item.case_id for item in versions}) != len(versions):
            raise ValueError("Sélectionnez une seule version publiée par cas d'examen.")
        if case_ids and set(case_ids) != {item.case_id for item in versions}:
            raise ValueError('Les cas et versions sélectionnés ne correspondent pas.')
        case_ids = [item.case_id for item in versions]
    else:
        existing = {item.case_id: item.version for item in exam.case_version_selections}
        versions = []
        for case_id in case_ids:
            version = existing.get(case_id)
            if version is None:
                availability = db.session.get(KineCaseAvailability, case_id)
                version = availability.version if availability else None
            if not version or version.status != 'published' or version.case_id != case_id:
                raise ValueError("Chaque cas d'examen doit avoir une version publiée sélectionnée.")
            versions.append(version)
    selected_cases = PatientCase.query.filter(
        PatientCase.id.in_(case_ids), PatientCase.specialty == 'kine',
        PatientCase.is_archived.is_(False),
    ).all() if case_ids else []
    if len(selected_cases) != len(set(case_ids)):
        raise ValueError("Un cas sélectionné est archivé ou n'est pas un cas Kiné.")
    if not selected_cases or any(version_view(item).mode_availability not in ('exam', 'both') for item in versions):
        raise ValueError("Sélectionnez au moins une version publiée disponible en mode examen.")
    selected_students = scoped_students().filter(Student.id.in_(student_ids)).all() if student_ids else []
    clean_groups = sorted({str(value).strip() for value in group_names or [] if str(value).strip()})
    if len(selected_students) != len(set(student_ids)):
        raise ValueError('Un étudiant sélectionné est introuvable.')
    if not selected_students and not clean_groups:
        raise ValueError('Sélectionnez au moins un étudiant ou un groupe autorisé.')
    group_students = Student.query.filter(Student.group_name.in_(clean_groups), Student.ecos_type == 'kine').all() if clean_groups else []
    allowed_ids = {student.id for student in scoped_students().all()}
    if any(student.id not in allowed_ids for student in group_students):
        raise ValueError('Sélection hors du périmètre de suivi autorisé.')
    existing_groups = {student.group_name for student in group_students}
    missing_groups = [group for group in clean_groups if group not in existing_groups]
    if missing_groups:
        raise ValueError('Groupe introuvable : ' + ', '.join(missing_groups))
    authorized_students = {student.id: student for student in selected_students + group_students}.values()
    incompatible = [
        student.name for student in authorized_students
        if not any(version_view(version).level in ('both', student.level or 'licence') for version in versions)
    ]
    if incompatible:
        raise ValueError(
            "Aucun cas sélectionné ne correspond au niveau de : " + ', '.join(incompatible)
        )
    exam.cases = selected_cases
    exam.students = selected_students
    exam.group_names = clean_groups
    db.session.flush()
    for selection in list(exam.case_version_selections):
        db.session.delete(selection)
    db.session.flush()
    for version in versions:
        db.session.add(ExamCaseVersion(
            exam_id=exam.id, case_id=version.case_id, version_id=version.id,
            provenance='selected',
        ))


@kine_bp.route('/exams/<int:exam_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
@kine_permission_required('exams.manage')
def exam_item(exam_id):
    exam = scoped_exams().filter(Exam.id == exam_id).first_or_404()
    if request.method == 'GET': return jsonify(_exam_payload(exam))
    if _exam_is_locked(exam):
        return error(
            "Cet examen est ouvert ou a déjà commencé : il ne peut plus être modifié ni supprimé.",
            409,
        )
    if request.method == 'DELETE':
        ExamCaseVersion.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)
        db.session.delete(exam); db.session.commit(); return ('', 204)
    try:
        _apply_exam(exam, payload()); db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback(); return error(str(exc))
    return jsonify(_exam_payload(exam))
