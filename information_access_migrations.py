"""004 additive per-information access policy and disclosure journal."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from information_access import (
    capture_version_information, ensure_case_information,
    install_information_guards, reconstructed_version_information,
)
from models import (
    CaseInformation, KineCaseVersion, KineVersionInformation, PatientCase,
    SimulationDisclosure,
)


VERSION = '004_information_access_policy'


def upgrade_information_access_policy(engine):
    """Create T04 storage and reconstruct only the current legacy policy.

    No historical disclosure is invented. Existing published clinical content,
    conversations and results are not modified.
    """
    tables = set(inspect(engine).get_table_names())
    required = {'patient_case1', 'kine_case_versions', 'simulation_sessions', 'schema_migrations'}
    if not required <= tables:
        raise RuntimeError('T03 schema required before information access policy')
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.begin() as connection:
        if not connection.execute(text(
            "SELECT 1 FROM schema_migrations WHERE version='003_case_version_storage'"
        )).scalar():
            raise RuntimeError('Applied T03 migration required before information access policy')
        applied = connection.execute(
            text('SELECT checksum FROM schema_migrations WHERE version=:v'), {'v': VERSION}
        ).scalar()
        if applied and applied != checksum:
            raise RuntimeError('Applied information access migration checksum mismatch')

    models = (CaseInformation, KineVersionInformation, SimulationDisclosure)
    if applied:
        expected_tables = {model.__tablename__ for model in models}
        if not expected_tables <= set(inspect(engine).get_table_names()):
            raise RuntimeError('Applied information access migration is missing tables')
        for model in models:
            expected = {column.name for column in model.__table__.columns}
            actual = {column['name'] for column in inspect(engine).get_columns(model.__tablename__)}
            if not expected <= actual:
                raise RuntimeError('Incompatible information table: ' + model.__tablename__)
        with engine.begin() as connection:
            install_information_guards(connection)
        return

    for model in models:
        model.__table__.create(engine, checkfirst=True)

    with Session(engine) as session, session.begin():
        cases = list(session.scalars(select(PatientCase).where(PatientCase.specialty == 'kine')))
        for case in cases:
            ensure_case_information(case, session=session)
        versions = list(session.scalars(select(KineCaseVersion).where(
            KineCaseVersion.status == 'published'
        )))
        for version in versions:
            if version.information_items:
                continue
            try:
                snapshot = json.loads(version.content_json)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f'Invalid published case snapshot {version.id}') from exc
            embedded = snapshot.get('information_access')
            if isinstance(embedded, list) and embedded:
                capture_version_information(version, embedded, session=session)
            else:
                reconstructed_version_information(version, snapshot, session=session)

    with engine.begin() as connection:
        install_information_guards(connection)
        connection.execute(text(
            'INSERT OR IGNORE INTO schema_migrations(version,checksum,applied_at) '
            'VALUES (:v,:c,:d)'
        ), {'v': VERSION, 'c': checksum, 'd': datetime.utcnow().isoformat()})
