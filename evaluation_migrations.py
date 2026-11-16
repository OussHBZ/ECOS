"""007: additive review journal and thresholds; no rewriting of existing attempts."""
from datetime import datetime
import hashlib
from pathlib import Path
from sqlalchemy import text, inspect
from models import KineEvaluationChange, KineEvaluationSettings
from evaluation_lifecycle import evaluation_guards

VERSION = '007_criteria_evaluation'


def upgrade_evaluation(engine):
    checksum = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with engine.begin() as connection:
        if not connection.execute(text("SELECT 1 FROM schema_migrations WHERE version='006_etp_library'")).scalar():
            raise RuntimeError('Applied T12 required')
        applied = connection.execute(text('SELECT checksum FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar()
        if applied and applied != checksum:
            raise RuntimeError('Evaluation migration checksum mismatch')
    tables = (KineEvaluationChange, KineEvaluationSettings)
    if applied and any(model.__tablename__ not in inspect(engine).get_table_names() for model in tables):
        raise RuntimeError('Applied evaluation migration has a missing table; restore the backup')
    for model in tables:
        model.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        evaluation_guards(KineEvaluationChange.__table__, connection)
        connection.execute(text('INSERT OR IGNORE INTO schema_migrations(version,checksum,applied_at) VALUES (:v,:c,:a)'),
                           {'v': VERSION, 'c': checksum, 'a': datetime.utcnow().isoformat()})
