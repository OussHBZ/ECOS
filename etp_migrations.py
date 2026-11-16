"""006 additive ETP library, no backfill or historical case rewrite."""
from datetime import datetime
import hashlib
from pathlib import Path
from sqlalchemy import inspect, text
from models import KineETPVersion
from etp_library import etp_triggers

VERSION = '006_etp_library'


def upgrade_etp_library(engine):
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.begin() as connection:
        if not connection.execute(text("SELECT 1 FROM schema_migrations WHERE version='005_case_authoring_wizard'")).scalar():
            raise RuntimeError('Applied T05 required before ETP library')
        applied = connection.execute(text('SELECT checksum FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar()
        if applied and applied != checksum:
            raise RuntimeError('Applied ETP migration checksum mismatch')
    if applied and KineETPVersion.__tablename__ not in inspect(engine).get_table_names():
        raise RuntimeError('ETP library table missing')
    KineETPVersion.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        etp_triggers(KineETPVersion.__table__, connection)
        connection.execute(text('INSERT OR IGNORE INTO schema_migrations(version,checksum,applied_at) VALUES (:v,:c,:a)'),
                           {'v': VERSION, 'c': checksum, 'a': datetime.utcnow().isoformat()})
