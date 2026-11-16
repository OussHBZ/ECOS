"""003 additive storage/backfill; no inferred historical clinical version.

Only storage/backfill is wired to startup; D08/release activation stays separate.
Call only on an explicit temporary/authorized engine after T01/02's helper.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from models import (Exam, PatientCase, Student, SimulationSession, KineCaseVersion,
                    KineCaseAvailability, ExamCaseVersion)
from case_versions import (canonical, digest, case_snapshot, freeze_simulation,
                           install_version_guards, install_simulation_guards)

VERSION = '003_case_version_storage'


def upgrade_case_version_storage(engine):
    """Create storage and label every reconstructed reference explicitly.

    Current level/mode access and existing exam selections are preserved as
    reconstructed configuration. Existing result JSON and conversations are
    never changed and no missing historical clinical content is invented.
    """
    # The current mapper contains later additive authoring fields. Stage them
    # without marking T05 as applied before loading legacy rows.
    from case_authoring_migrations import ensure_case_authoring_columns
    ensure_case_authoring_columns(engine)
    tables = set(inspect(engine).get_table_names())
    if not {'student', 'teacher', 'patient_case1', 'simulation_sessions', 'schema_migrations'} <= tables:
        raise RuntimeError('T01/T02 schema required before case version storage')
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.begin() as connection:
        if not connection.execute(text("SELECT 1 FROM schema_migrations WHERE version='002_account_lifecycle'")).scalar():
            raise RuntimeError('Applied T02 migration required before case version storage')
        applied = connection.execute(text('SELECT checksum FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar()
        if applied and applied != checksum:
            raise RuntimeError('Applied case version migration checksum mismatch')
    if applied:
        required_tables = {'kine_case_versions', 'kine_case_availability', 'exam_case_versions'}
        if not required_tables <= set(inspect(engine).get_table_names()):
            raise RuntimeError('Applied case version migration is missing tables')
        required_columns = {'case_version_id', 'frozen_student_level', 'evaluation_reference_json',
                            'student_reference_json', 'reference_origin'}
        if not required_columns <= {c['name'] for c in inspect(engine).get_columns('simulation_sessions')}:
            raise RuntimeError('Applied case version migration is missing simulation references')
        with engine.begin() as connection:
            install_version_guards(connection)
            install_simulation_guards(connection)
        return
    for model in (KineCaseVersion, KineCaseAvailability, ExamCaseVersion):
        model.__table__.create(engine, checkfirst=True)
    columns = {c['name'] for c in inspect(engine).get_columns('simulation_sessions')}
    for name, definition in [
        ('case_version_id', 'INTEGER REFERENCES kine_case_versions(id)'),
        ('frozen_student_level', 'VARCHAR(20)'), ('evaluation_reference_json', 'TEXT'),
        ('student_reference_json', 'TEXT'), ('reference_origin', 'VARCHAR(50)'),
    ]:
        if name not in columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(f'ALTER TABLE simulation_sessions ADD COLUMN {name} {definition}')
    for model in (KineCaseVersion, KineCaseAvailability, ExamCaseVersion):
        details = {c['name'] for c in inspect(engine).get_columns(model.__tablename__)}
        if not {c.name for c in model.__table__.columns} <= details:
            raise RuntimeError('Incompatible case version table: ' + model.__tablename__)
    with Session(engine) as session, session.begin():
        versions_by_case = {}
        for case in session.scalars(select(PatientCase).where(PatientCase.specialty == 'kine')):
            version = session.scalars(select(KineCaseVersion).where(
                KineCaseVersion.case_id == case.id, KineCaseVersion.provenance == 'reconstructed_current')).first()
            if version is None and not session.scalars(select(KineCaseVersion.id).where(KineCaseVersion.case_id == case.id)).first():
                content = canonical(case_snapshot(case))
                version = KineCaseVersion(case_id=case.id, number=1, status='published',
                    content_json=content, content_sha256=digest(content),
                    provenance='reconstructed_current', published_at=datetime.utcnow(),
                    published_actor='migration:003:current-reference-only')
                session.add(version)
                session.flush()
            if version is None:
                # Already authored/versioned cases are never resnapshotted.
                version = session.scalars(select(KineCaseVersion).where(
                    KineCaseVersion.case_id == case.id,
                    KineCaseVersion.status == 'published',
                ).order_by(KineCaseVersion.number.desc())).first()
            if version is None:
                continue
            versions_by_case[case.id] = version
            if not case.is_archived and session.get(KineCaseAvailability, case.id) is None:
                levels = ['licence', 'master'] if case.level == 'both' else [case.level]
                audience = {
                    'schema_version': 1,
                    'student_ids': [],
                    'group_names': [],
                    'legacy_levels': [value for value in levels if value in ('licence', 'master')],
                    'provenance': 'reconstructed_current_access',
                }
                session.add(KineCaseAvailability(
                    case_id=case.id, version_id=version.id,
                    audience_json=canonical(audience),
                    updated_actor='migration:003:current-access-only',
                ))
            for simulation in session.scalars(select(SimulationSession).where(
                    SimulationSession.clinical_case_id == case.id, SimulationSession.case_version_id.is_(None))):
                student = session.get(Student, simulation.student_id)
                freeze_simulation(simulation, version, student, provenance='reconstructed_current_not_historical')
                result = simulation.evaluation_results or {}
                # The saved result is the only evidence of a historical level.
                if result.get('level') in ('licence', 'master'):
                    simulation.frozen_student_level = result['level']
                    from case_versions import evaluation_reference
                    simulation.evaluation_reference_json = canonical(evaluation_reference(result['level']))
                # Explicitly distinguish copied current configuration from facts
                # proven by the historical result; never recompute the latter.
                reference = json.loads(simulation.evaluation_reference_json or '{}')
                reference['provenance'] = 'reconstructed_current_not_historical'
                reference['historical_result_metadata'] = {key: result[key] for key in
                    ('level', 'grid_name', 'validation_threshold', 'elimination_cap', 'schema_version') if key in result}
                simulation.evaluation_reference_json = canonical(reference)
                session.flush()
        for exam in session.scalars(select(Exam)):
            for case in exam.cases:
                if session.get(ExamCaseVersion, (exam.id, case.id)) is not None:
                    continue
                version = versions_by_case.get(case.id)
                if version:
                    session.add(ExamCaseVersion(
                        exam_id=exam.id, case_id=case.id, version_id=version.id,
                        provenance='reconstructed_current_selection',
                    ))
    with engine.begin() as connection:
        install_version_guards(connection)
        install_simulation_guards(connection)
        connection.execute(text('INSERT OR IGNORE INTO schema_migrations(version,checksum,applied_at) VALUES (:v,:c,:d)'),
            {'v': VERSION, 'c': checksum, 'd': datetime.utcnow().isoformat()})
