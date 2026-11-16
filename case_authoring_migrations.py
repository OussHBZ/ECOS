"""005 additive T05 authoring fields and original-document storage."""

from datetime import datetime
import hashlib
from pathlib import Path

from sqlalchemy import inspect, text

from models import KineCaseDocument


VERSION = '005_case_authoring_wizard'


CASE_COLUMNS = (
    ('difficulty', 'VARCHAR(20)'),
    ('subpathology', 'VARCHAR(250)'),
    ('rehabilitation_phase', 'VARCHAR(50)'),
    ('planned_sessions', 'INTEGER'),
    ('pedagogical_summary', 'TEXT'),
    ('structured_content_json', 'TEXT'),
    ("authoring_status", "VARCHAR(20) NOT NULL DEFAULT 'legacy'"),
    ('authoring_progress_json', 'TEXT'),
)

MEDICATION_COLUMNS = (
    ('dosage', 'TEXT'),
    ('frequency', 'TEXT'),
)


def ensure_case_authoring_columns(engine):
    """Stage current ORM columns before older backfills load mapped rows.

    This operation is additive and repeatable. It deliberately does not
    stamp migration 005.
    """
    tables = set(inspect(engine).get_table_names())
    for table, additions in (
        ('patient_case1', CASE_COLUMNS), ('medications', MEDICATION_COLUMNS),
    ):
        if table not in tables:
            continue
        existing = {column['name'] for column in inspect(engine).get_columns(table)}
        for name, definition in additions:
            if name not in existing:
                with engine.begin() as connection:
                    connection.exec_driver_sql(
                        f'ALTER TABLE {table} ADD COLUMN {name} {definition}'
                    )


def upgrade_case_authoring(engine):
    tables = set(inspect(engine).get_table_names())
    required = {
        'patient_case1', 'patient_records', 'medications', 'schema_migrations',
        'kine_case_versions', 'case_information',
    }
    if not required <= tables:
        raise RuntimeError('T03/T04 schema required before T05 authoring storage')
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.begin() as connection:
        if not connection.execute(text(
            "SELECT 1 FROM schema_migrations WHERE version='004_information_access_policy'"
        )).scalar():
            raise RuntimeError('Applied T04 migration required before T05 authoring storage')
        applied = connection.execute(text(
            'SELECT checksum FROM schema_migrations WHERE version=:version'
        ), {'version': VERSION}).scalar()
        if applied and applied != checksum:
            raise RuntimeError('Applied T05 migration checksum mismatch')
    if applied:
        _validate(engine)
        return

    ensure_case_authoring_columns(engine)
    KineCaseDocument.__table__.create(engine, checkfirst=True)
    _validate(engine)
    with engine.begin() as connection:
        connection.execute(text(
            'INSERT OR IGNORE INTO schema_migrations(version,checksum,applied_at) '
            'VALUES (:version,:checksum,:applied_at)'
        ), {
            'version': VERSION, 'checksum': checksum,
            'applied_at': datetime.utcnow().isoformat(),
        })


def _validate(engine):
    tables = set(inspect(engine).get_table_names())
    if KineCaseDocument.__tablename__ not in tables:
        raise RuntimeError('Applied T05 migration is missing original documents')
    case_columns = {column['name'] for column in inspect(engine).get_columns('patient_case1')}
    medication_columns = {column['name'] for column in inspect(engine).get_columns('medications')}
    if not {name for name, _ in CASE_COLUMNS} <= case_columns:
        raise RuntimeError('Applied T05 migration is missing case authoring columns')
    if not {name for name, _ in MEDICATION_COLUMNS} <= medication_columns:
        raise RuntimeError('Applied T05 migration is missing medication columns')
