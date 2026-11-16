"""Kiné case publications. Snapshots contain stored data, never inferred facts."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event, inspect, select
from models import (db, PatientCase, KineCaseVersion, KineCaseAvailability,
                    ExamCaseVersion, SimulationSession)


def canonical(value):
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError(type(item).__name__)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=encode)


def digest(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _columns(model):
    return {column.name: deepcopy(getattr(model, column.name)) for column in model.__table__.columns}


def case_snapshot(case):
    from criterion_evaluation import normalize_criteria
    from teaching_aids import normalize_aids
    normalize_aids(case.structured_content.get('teaching_aids', []), case)
    from information_access import snapshot_current_information
    from rehabilitation import evaluation_inputs
    record = case.patient_record
    return {
        'schema_version': 2,
        'case': _columns(case),
        'folder': _columns(case.pathology_folder) if case.pathology_folder else None,
        'patient_record': ({**_columns(record),
            'interventions': [{**_columns(i), 'timing': i.timing} for i in record.interventions],
            'medications': [_columns(m) for m in record.medications]} if record else None),
        'incidents': [_columns(i) for i in case.incidents if not inspect(i).deleted],
        'case_documents': [_columns(item) for item in case.documents if not inspect(item).deleted],
        'information_access': snapshot_current_information(case),
        'evaluation_inputs': evaluation_inputs(case),
        'evaluation_criteria': normalize_criteria(case.structured_content.get('evaluation_criteria', [])),
        'modules_not_yet_implemented': [],
    }


def save_draft(case):
    if case.specialty != 'kine':
        raise ValueError('Cas Kiné requis.')
    db.session.flush()
    content = canonical(case_snapshot(case))
    draft = KineCaseVersion.query.filter_by(case_id=case.id, status='draft').first()
    if draft is None:
        number = (db.session.query(db.func.max(KineCaseVersion.number)).filter_by(case_id=case.id).scalar() or 0) + 1
        draft = KineCaseVersion(case_id=case.id, number=number, status='draft')
        db.session.add(draft)
    draft.content_json = content
    draft.content_sha256 = digest(draft.content_json)
    return draft


def publish(case, actor, expected_sha256=None):
    from information_access import capture_version_information
    from rehabilitation import normalize_rehabilitation
    program = case.structured_content.get('rehabilitation_program')
    if program is not None:
        normalize_rehabilitation(program)
    event_ids = {e['id'] for e in (program or {}).get('session', {}).get('events', [])}
    for criterion in case.structured_content.get('evaluation_criteria', []):
        condition = criterion.get('applicability', {})
        if condition.get('kind') == 'event' and condition.get('event_id') not in event_ids:
            raise ValueError('Un critère conditionnel référence un événement absent du scénario.')
    for association in case.structured_content.get('etp_associations', []):
        if association.get('status') != 'validated':
            raise ValueError('Validez ou retirez chaque adaptation ETP avant publication.')
    draft = save_draft(case)
    if expected_sha256 and expected_sha256 != draft.content_sha256:
        raise ValueError('Le brouillon a changé ; relisez-le avant publication.')
    draft.status = 'published'
    draft.published_at = datetime.utcnow()
    draft.published_actor = actor
    db.session.flush()
    capture_version_information(
        draft, [item for item in case.information_items if not inspect(item).deleted]
    )
    return draft


def version_view(version):
    if not version or version.status != 'published':
        raise ValueError('Version publiée requise.')
    if digest(version.content_json) != version.content_sha256:
        raise ValueError('Empreinte de version invalide.')
    data = json.loads(version.content_json)
    case = SimpleNamespace(**data['case'])
    for name in ('patient_info', 'symptoms', 'evaluation_checklist', 'differential_diagnosis', 'custom_sections'):
        setattr(case, name, json.loads(getattr(case, name + '_json', None) or ('{}' if name == 'patient_info' else '[]')))
    case.structured_content = json.loads(getattr(case, 'structured_content_json', None) or '{}')
    folder = SimpleNamespace(**data['folder']) if data.get('folder') else None
    case.pathology_folder = folder
    case.incidents = [SimpleNamespace(**i) for i in data['incidents']]
    raw_record = data.get('patient_record')
    record = SimpleNamespace(**raw_record) if raw_record else None
    if record:
        record.interventions = [SimpleNamespace(**i) for i in raw_record['interventions']]
        record.medications = [SimpleNamespace(**m) for m in raw_record['medications']]
    case.patient_record = record
    case.case_documents = [SimpleNamespace(**item) for item in data.get('case_documents') or []]
    case.information_access = deepcopy(data.get('information_access') or [])
    case.version_id, case.version_number = version.id, version.number
    case.version_provenance = version.provenance
    case.get_summary = lambda: case.title or case.diagnosis or case.case_number
    return case


def evaluation_reference(level):
    from evaluation_config import get_kine_evaluation_grid
    grid = get_kine_evaluation_grid(level)
    return {'schema_version': 1, 'engine': 'legacy_kine_v2',
            'engine_sha256': hashlib.sha256(Path(__file__).with_name('kine_evaluation.py').read_bytes()).hexdigest(),
            'referential': f'legacy_kine_v2:{grid["level"]}',
            'referential_sha256': digest(canonical(grid)),
            'validation_threshold': grid['validation_threshold'],
            'grid': grid}


def audience_payload(student_ids=None, group_names=None, *, provenance='selected'):
    """Canonical explicit audience; legacy levels are migration-only."""
    return {
        'schema_version': 1,
        'student_ids': sorted({int(value) for value in student_ids or []}),
        'group_names': sorted({str(value).strip() for value in group_names or [] if str(value).strip()}),
        'provenance': provenance,
    }


def availability_audience(availability):
    try:
        value = json.loads(availability.audience_json or '{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def audience_allows(availability, student):
    audience = availability_audience(availability)
    if student.id in audience.get('student_ids', []):
        return True
    if student.group_name and student.group_name in audience.get('group_names', []):
        return True
    # This field only preserves the former level-based availability during
    # migration. New teacher choices always use explicit students/groups.
    return student.level in audience.get('legacy_levels', [])


def version_supports(version, student, mode):
    if not version or version.status != 'published':
        return False
    case = version_view(version)
    return (case.level in ('both', student.level or 'licence')
            and case.mode_availability in ('both', mode))


def training_version(case_id, student):
    availability = db.session.get(KineCaseAvailability, case_id)
    if not availability or not availability.version_id or not audience_allows(availability, student):
        return None
    stable_case = db.session.get(PatientCase, case_id)
    version = availability.version
    if (not stable_case or stable_case.specialty != 'kine' or stable_case.is_archived
            or not version or version.case_id != case_id
            or not version_supports(version, student, 'training')):
        return None
    return version


def selected_exam_version(exam_id, case_id, student=None):
    selection = db.session.get(ExamCaseVersion, (exam_id, case_id))
    if not selection or not selection.version or selection.version.case_id != case_id:
        return None
    if student is not None and not version_supports(selection.version, student, 'exam'):
        return None
    return selection.version


def freeze_simulation(simulation, version, student, provenance='captured_at_start'):
    if version.case_id != simulation.clinical_case_id or version.status != 'published':
        raise ValueError('Version et identité du cas incompatibles.')
    simulation.case_version = version
    simulation.frozen_student_level = student.level if student.level in ('licence', 'master') else None
    from evaluation_lifecycle import frozen_reference
    simulation.evaluation_reference_json = canonical(frozen_reference(version, student, simulation)) if simulation.frozen_student_level else None
    simulation.student_reference_json = canonical({name: getattr(student, name, None) for name in
        ('id', 'name', 'student_code', 'level', 'group_name', 'class_name')})
    simulation.reference_origin = provenance


def simulation_case(simulation):
    # Legacy unmigrated rows remain identifiable. The migration attaches all
    # existing Kiné rows; new public starts always require a frozen version.
    return version_view(simulation.case_version) if simulation.case_version else simulation.clinical_case


def simulation_student(simulation):
    if simulation.student_reference_json:
        values = json.loads(simulation.student_reference_json)
        values['level'] = simulation.frozen_student_level
        return SimpleNamespace(**values)
    return simulation.student


def version_metadata(simulation):
    version = simulation.case_version
    return {'case_version_id': version.id if version else None,
            'case_version_number': version.number if version else None,
            'case_reference_provenance': version.provenance if version else 'unversioned_legacy',
            'reference_origin': simulation.reference_origin or 'unversioned_legacy',
            'frozen_student_level': simulation.frozen_student_level}


@event.listens_for(KineCaseVersion, 'before_update')
def prevent_publication_change(mapper, connection, target):
    status = connection.execute(select(KineCaseVersion.status).where(KineCaseVersion.id == target.id)).scalar()
    if status == 'published' and any(inspect(target).attrs[c.name].history.has_changes() for c in target.__table__.columns):
        raise ValueError('Une version publiée est immuable.')


@event.listens_for(KineCaseVersion, 'before_delete')
def prevent_publication_delete(mapper, connection, target):
    if connection.execute(select(KineCaseVersion.status).where(KineCaseVersion.id == target.id)).scalar() == 'published':
        raise ValueError('Une version publiée est conservée.')


def install_version_guards(connection):
    for operation in ('UPDATE', 'DELETE'):
        connection.exec_driver_sql(f'''CREATE TRIGGER IF NOT EXISTS kine_version_no_{operation.lower()}
            BEFORE {operation} ON kine_case_versions WHEN OLD.status = 'published'
            BEGIN SELECT RAISE(ABORT, 'published version is immutable'); END''')


def install_simulation_guards(connection):
    fields = ('case_version_id', 'frozen_student_level', 'evaluation_reference_json',
              'student_reference_json', 'reference_origin', 'clinical_case_id')
    changed = ' OR '.join(f'OLD.{name} IS NOT NEW.{name}' for name in fields)
    connection.exec_driver_sql(f'''CREATE TRIGGER IF NOT EXISTS kine_simulation_reference_immutable
        BEFORE UPDATE ON simulation_sessions WHEN OLD.case_version_id IS NOT NULL AND ({changed})
        BEGIN SELECT RAISE(ABORT, 'simulation reference is immutable'); END''')
    for operation in ('INSERT', 'UPDATE'):
        connection.exec_driver_sql(f'''CREATE TRIGGER IF NOT EXISTS kine_simulation_version_{operation.lower()}
            BEFORE {operation} ON simulation_sessions WHEN NEW.case_version_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM kine_case_versions v WHERE v.id = NEW.case_version_id
                AND v.case_id = NEW.clinical_case_id AND v.status = 'published')
            BEGIN SELECT RAISE(ABORT, 'invalid simulation publication'); END''')


@event.listens_for(KineCaseVersion.__table__, 'after_create')
def create_version_guards(table, connection, **kwargs):
    if connection.dialect.name == 'sqlite':
        install_version_guards(connection)


@event.listens_for(SimulationSession.__table__, 'after_create')
def create_simulation_guards(table, connection, **kwargs):
    if connection.dialect.name == 'sqlite':
        install_simulation_guards(connection)
