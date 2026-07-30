import json
import os
import tempfile
from datetime import datetime
from io import BytesIO

from flask import current_app, jsonify, redirect, render_template, request, send_file, url_for

from auth import teacher_required
from document_processor import DocumentExtractionAgent
from models import (
    Exam, Incident, Intervention, Medication, PathologyFolder, PatientCase,
    PatientRecord, Student, db,
)

from . import kine_bp
from .common import (
    CASE_LEVELS, MODES, canonicalize_medical_tests, error,
    normalize_vital_parameters, parse_datetime, parse_indexed_form, payload,
    teacher_id, validate_vital_parameter_rows, wants_json,
)


@kine_bp.route('/teacher')
@teacher_required
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
    }


def _case_form_payload(case):
    """Return every persisted case field in the extraction/form schema."""
    record = case.patient_record
    stored_tests = canonicalize_medical_tests(record.tests or {}) if record else {}
    categorized_tests = {
        key: list(stored_tests.get(key) or [])
        for key in ('cardiac', 'vascular', 'biological', 'imaging', 'other')
    }
    assessment = stored_tests.get('physiotherapy_assessment') or {}
    return {
        **_case_payload(case),
        'patient_info': record.identity or {} if record else {},
        'medical_context': record.medical_context or {} if record else {'main_diagnosis': case.diagnosis},
        'history': record.medical_history or {} if record else {},
        'comorbidities': record.comorbidities or [] if record else [],
        'procedures': [{
            'type': item.intervention_type,
            'date': item.intervention_date.isoformat() if item.intervention_date else None,
            'complications': item.complications,
        } for item in (record.interventions if record else [])],
        'medications': [{
            'therapeutic_class': item.therapeutic_class, 'inn': item.inn,
            'effect': item.effect, 'physiotherapy_precautions': item.physiotherapy_precautions,
        } for item in (record.medications if record else [])],
        'tests': categorized_tests,
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
    }


def _repeatable(data, name):
    value = data.get(name) if hasattr(data, 'get') else None
    if isinstance(value, list):
        return value
    rows = parse_indexed_form(name)
    if rows:
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
    tests = _repeatable(data, 'tests')
    parameters = _repeatable(data, 'parameters')
    # Unlike legacy extracted repeaters, an empty structured list is meaningful:
    # it means the teacher deleted every vital-parameter row.
    vital_parameters = parse_indexed_form('vital_parameters')
    validate_vital_parameter_rows(vital_parameters)
    form_record = {
        'identity': {
            'name': data.get('identity_name'), 'age': data.get('identity_age'),
            'gender': data.get('identity_gender'), 'family_situation': data.get('family_situation'),
            'occupation': data.get('occupation'), 'height_cm': data.get('height_cm'),
            'weight_kg': data.get('weight_kg'), 'bmi': data.get('bmi'),
            'social_context': data.get('social_context'),
        },
        'medical_context': {
            'main_diagnosis': data.get('diagnosis'), 'illness_history': data.get('illness_history'),
        },
        'medical_history': {
            'cardiovascular': data.get('history_cardiovascular'), 'medical': data.get('history_medical'),
            'surgical': data.get('history_surgical'), 'allergies': data.get('history_allergies'),
            'risk_factors': data.get('risk_factors'),
        },
        'tests': {
            'items': tests,
            'physiotherapy_assessment': assessment,
            'vital_parameters': vital_parameters,
        },
        'reference_vitals': {item.get('name'): {'value': item.get('value'), 'unit': item.get('unit')} for item in parameters if item.get('name')},
        'medical_prescription': data.get('medical_prescription'),
        'physiotherapy_prescription': data.get('physiotherapy_prescription'),
        'available_documents': [file.filename for file in request.files.getlist('documents') if file and file.filename],
    }
    for section in ('identity', 'medical_context', 'medical_history', 'reference_vitals'):
        base.setdefault(section, {}).update({key: value for key, value in form_record[section].items() if value not in (None, '')})
    form_tests = form_record['tests']
    if tests:
        categorized = {key: [] for key in ('cardiac', 'vascular', 'biological', 'imaging', 'other')}
        for item in tests:
            if not isinstance(item, dict):
                categorized['other'].append(item)
                continue
            category = item.get('category') if item.get('category') in categorized else 'other'
            categorized[category].append({key: value for key, value in item.items() if key != 'category'})
        base['tests'] = categorized
    if any(assessment.values()):
        base.setdefault('tests', {})['physiotherapy_assessment'] = assessment
    if form_tests.get('vital_parameters'):
        base.setdefault('tests', {})['vital_parameters'] = form_tests['vital_parameters']
    base['tests'] = canonicalize_medical_tests(base.get('tests') or {})
    for field in ('medical_prescription', 'physiotherapy_prescription'):
        if form_record.get(field):
            base[field] = form_record[field]
    if form_record['available_documents']:
        base['available_documents'] = list(dict.fromkeys((base.get('available_documents') or []) + form_record['available_documents']))
    return base


def _apply_case(case, data):
    case.case_number = str(data.get('case_number') or case.case_number or '').strip()
    if not case.case_number:
        raise ValueError('Case number is required')
    case.specialty = 'kine'
    case.title = str(data.get('title') or case.title or '').strip() or None
    case.folder_id = int(data.get('folder_id')) if data.get('folder_id') else None
    case.level = str(data.get('level') or case.level or 'both').lower()
    case.mode_availability = str(data.get('mode_availability') or case.mode_availability or 'both').lower()
    if case.level not in CASE_LEVELS:
        raise ValueError('Invalid case level')
    if case.mode_availability not in MODES:
        raise ValueError('Invalid mode availability')
    case.pedagogical_objectives = data.get('pedagogical_objectives')
    case.emotional_state = data.get('emotional_state') or 'cooperative'
    nested_record = data.get('patient_record') or {} if request.is_json else {}
    extracted = _extracted_form_data()
    case.diagnosis = data.get('diagnosis') or nested_record.get('medical_context', {}).get('main_diagnosis') or case.diagnosis
    case.diagnosis = case.diagnosis or (extracted.get('medical_context') or {}).get('main_diagnosis') or extracted.get('diagnosis')
    case.directives = data.get('directives')
    checklist = _repeatable(data, 'evaluation_checklist')
    if checklist:
        case.evaluation_checklist = checklist


def _apply_record(case, data, replace_children=True):
    record_data = _record_data(data)
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
    if replace_children:
        record.interventions.clear()
        for item in _repeatable(data, 'procedures'):
            date_value = item.get('date')
            record.interventions.append(Intervention(
                intervention_type=item.get('type') or item.get('intervention_type') or 'Procedure',
                intervention_date=parse_datetime(date_value, 'procedure date').date() if date_value else None,
                complications=item.get('complications'),
            ))
        record.medications.clear()
        for item in _repeatable(data, 'medications'):
            record.medications.append(Medication(
                therapeutic_class=item.get('therapeutic_class') or 'Unspecified', inn=item.get('inn'),
                effect=item.get('effect'), physiotherapy_precautions=item.get('precautions') or item.get('physiotherapy_precautions'),
            ))
    db.session.add(record)


@kine_bp.route('/cases', methods=['GET', 'POST'])
@teacher_required
def cases_collection():
    if request.method == 'GET':
        cases = PatientCase.query.filter_by(specialty='kine').order_by(PatientCase.created_at.desc()).all()
        return jsonify({'cases': [_case_payload(case) for case in cases]})
    data = payload()
    if PatientCase.query.filter_by(case_number=str(data.get('case_number') or '').strip()).first():
        return error('Case number already exists', 409)
    case = PatientCase()
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
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return error(str(exc))
    if wants_json():
        return jsonify(_case_payload(case)), 201
    return redirect(url_for('kine.case_item', case_id=case.id))


@kine_bp.route('/cases/new')
@teacher_required
def new_case_form():
    return render_template('case_form_kine.html', clinical_case=None,
                           folders=PathologyFolder.query.filter_by(specialty='kine', is_archived=False).all(),
                           form_action=url_for('kine.cases_collection'),
                           extraction_url=url_for('kine.extract_case_document'))


@kine_bp.route('/cases/extract', methods=['POST'])
@teacher_required
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
@teacher_required
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
                               download_url=url_for('kine.download_case', case_id=case.id))
    if request.method == 'DELETE':
        db.session.delete(case)
        db.session.commit()
        return ('', 204)
    data = payload()
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
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return error(str(exc))
    if wants_json():
        return jsonify(_case_payload(case))
    return redirect(url_for('kine.case_item', case_id=case.id))


@kine_bp.route('/cases/<int:case_id>/download')
@teacher_required
def download_case(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    content = json.dumps(_case_form_payload(case), ensure_ascii=False, indent=2, default=str).encode('utf-8')
    return send_file(
        BytesIO(content), mimetype='application/json; charset=utf-8', as_attachment=True,
        download_name=f"cas_kine_{case.case_number}.json",
    )


@kine_bp.route('/cases/<int:case_id>/lifecycle', methods=['POST'])
@teacher_required
def case_lifecycle(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    action = request.form.get('action') or (request.get_json(silent=True) or {}).get('action')
    if action == 'archive':
        case.is_archived = True
    elif action == 'restore':
        case.is_archived = False
    elif action == 'delete':
        if case.simulation_sessions:
            return error("Ce cas possède des simulations et doit être archivé plutôt que supprimé.", 409)
        for exam in list(case.kine_exams):
            exam.cases.remove(case)
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
@teacher_required
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
    db.session.commit()
    return jsonify(_incident_payload(incident)), 201


def _incident_payload(incident):
    return {'id': incident.id, 'case_id': incident.clinical_case_id,
            'trigger_description': incident.trigger_description, 'trigger_condition': incident.trigger_condition,
            'scripted_reaction': incident.scripted_reaction, 'severity': incident.severity}


@kine_bp.route('/incidents/<int:incident_id>', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
@teacher_required
def incident_item(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    if incident.clinical_case.specialty != 'kine':
        return error('Not a kine incident', 404)
    if request.method == 'DELETE' or (request.method == 'POST' and request.form.get('_action') == 'delete'):
        db.session.delete(incident); db.session.commit(); return ('', 204)
    data = payload()
    for field in ('trigger_description', 'trigger_condition', 'scripted_reaction'):
        if data.get(field) is not None:
            setattr(incident, field, data.get(field))
    if data.get('severity') in ('minor', 'major'):
        incident.severity = data.get('severity')
    db.session.commit()
    return jsonify(_incident_payload(incident))


def _exam_payload(exam):
    return {'id': exam.id, 'name': exam.name, 'instructions': exam.instructions,
            'start_at': exam.start_at.isoformat() + 'Z', 'end_at': exam.end_at.isoformat() + 'Z',
            'max_duration_minutes': exam.max_duration_minutes,
            'case_ids': [case.id for case in exam.cases], 'student_ids': [student.id for student in exam.students],
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
@teacher_required
def exams_collection():
    if request.method == 'GET':
        return jsonify({'exams': [_exam_payload(exam) for exam in Exam.query.order_by(Exam.start_at.desc()).all()]})
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
    student_ids = get_list('student_ids')
    group_names = get_list('group_names')
    if case_ids is not None and not isinstance(case_ids, list): case_ids = [case_ids]
    if student_ids is not None and not isinstance(student_ids, list): student_ids = [student_ids]
    if group_names is not None and not isinstance(group_names, list): group_names = [group_names]
    try:
        case_ids = list(dict.fromkeys(int(value) for value in case_ids or []))
        student_ids = list(dict.fromkeys(int(value) for value in student_ids or []))
    except (TypeError, ValueError):
        raise ValueError('La sélection des cas ou des étudiants est invalide.')
    selected_cases = PatientCase.query.filter(
        PatientCase.id.in_(case_ids), PatientCase.specialty == 'kine',
        PatientCase.is_archived.is_(False),
        PatientCase.mode_availability.in_(['exam', 'both']),
    ).all() if case_ids else []
    if len(selected_cases) != len(set(case_ids)):
        raise ValueError("Un cas sélectionné est archivé ou n'est pas disponible en mode examen.")
    if not selected_cases:
        raise ValueError("Sélectionnez au moins un cas disponible en mode examen.")
    selected_students = Student.query.filter(Student.id.in_(student_ids), Student.ecos_type == 'kine').all() if student_ids else []
    clean_groups = sorted({str(value).strip() for value in group_names or [] if str(value).strip()})
    if len(selected_students) != len(set(student_ids)):
        raise ValueError('Un étudiant sélectionné est introuvable.')
    if not selected_students and not clean_groups:
        raise ValueError('Sélectionnez au moins un étudiant ou un groupe autorisé.')
    group_students = Student.query.filter(Student.group_name.in_(clean_groups), Student.ecos_type == 'kine').all() if clean_groups else []
    existing_groups = {student.group_name for student in group_students}
    missing_groups = [group for group in clean_groups if group not in existing_groups]
    if missing_groups:
        raise ValueError('Groupe introuvable : ' + ', '.join(missing_groups))
    authorized_students = {student.id: student for student in selected_students + group_students}.values()
    incompatible = [
        student.name for student in authorized_students
        if not any(case.level in ('both', student.level or 'licence') for case in selected_cases)
    ]
    if incompatible:
        raise ValueError(
            "Aucun cas sélectionné ne correspond au niveau de : " + ', '.join(incompatible)
        )
    exam.cases = selected_cases
    exam.students = selected_students
    exam.group_names = clean_groups


@kine_bp.route('/exams/<int:exam_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
@teacher_required
def exam_item(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if request.method == 'GET': return jsonify(_exam_payload(exam))
    if _exam_is_locked(exam):
        return error(
            "Cet examen est ouvert ou a déjà commencé : il ne peut plus être modifié ni supprimé.",
            409,
        )
    if request.method == 'DELETE': db.session.delete(exam); db.session.commit(); return ('', 204)
    try:
        _apply_exam(exam, payload()); db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback(); return error(str(exc))
    return jsonify(_exam_payload(exam))
