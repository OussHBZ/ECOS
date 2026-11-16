"""002: additive account lifecycle migration, shared by the two existing paths.

No application factory, seed or CLI call. Use only an explicit SQLAlchemy engine.
The operation is repeatable, including after a partially applied SQLite DDL.
"""
from datetime import datetime
import hashlib
from pathlib import Path
from sqlalchemy import inspect, text
from models import TeacherStudentScope, TeacherGroupScope

VERSION = '002_account_lifecycle'


def upgrade_account_lifecycle(engine):
    tables = set(inspect(engine).get_table_names())
    if not {'student', 'teacher', 'admin_access'} <= tables:
        raise RuntimeError('Account migration requires student, teacher and admin_access tables')
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.begin() as connection:
        connection.exec_driver_sql('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) PRIMARY KEY, checksum VARCHAR(64) NOT NULL,
            applied_at VARCHAR(40) NOT NULL)''')
        applied = connection.execute(text('SELECT checksum FROM schema_migrations WHERE version=:v'),
                                     {'v': VERSION}).scalar()
        if applied and applied != checksum:
            raise RuntimeError('Applied account migration checksum mismatch')
    for table in ('student', 'teacher'):
        for column, definition in (
            ('account_status', "VARCHAR(20) NOT NULL DEFAULT 'active'"),
            ('auth_version', 'INTEGER NOT NULL DEFAULT 0'),
        ):
            columns = {c['name'] for c in inspect(engine).get_columns(table)}
            if column not in columns:
                with engine.begin() as connection:
                    connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
        details = {c['name']: c for c in inspect(engine).get_columns(table)}
        for column, default in (('account_status', 'active'), ('auth_version', '0')):
            existing = details[column]
            actual_default = str(existing.get('default') or '').strip().strip('()').strip("'\"")
            if existing['nullable'] or actual_default != default:
                raise RuntimeError(f'Incompatible account schema: {table}.{column}')
    if 'admin_profile' not in {c['name'] for c in inspect(engine).get_columns('admin_access')}:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE admin_access ADD COLUMN admin_profile VARCHAR(20) NOT NULL DEFAULT 'technical'")
    admin_column = next(c for c in inspect(engine).get_columns('admin_access') if c['name'] == 'admin_profile')
    if admin_column['nullable'] or str(admin_column.get('default') or '').strip("()'\"") != 'technical':
        raise RuntimeError('Incompatible account schema: admin_access.admin_profile')
    # No attribution inferred from past activity, case creators or demo accounts.
    TeacherStudentScope.__table__.create(engine, checkfirst=True)
    TeacherGroupScope.__table__.create(engine, checkfirst=True)
    for model in (TeacherStudentScope, TeacherGroupScope):
        inspector = inspect(engine)
        table = model.__tablename__
        expected = {c.name for c in model.__table__.columns}
        if not expected <= {c['name'] for c in inspector.get_columns(table)} or set(inspector.get_pk_constraint(table)['constrained_columns']) != {c.name for c in model.__table__.primary_key}:
            raise RuntimeError(f'Incompatible scope schema: {table}')
    with engine.begin() as connection:
        connection.execute(text('INSERT OR IGNORE INTO schema_migrations (version,checksum,applied_at) '
                                'VALUES (:v,:c,:d)'),
                           {'v': VERSION, 'c': checksum, 'd': datetime.utcnow().isoformat()})
