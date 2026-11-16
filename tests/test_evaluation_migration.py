"""007 migration: temporary database only, retry, integrity and restoration."""
from contextlib import closing
import shutil
import sqlite3
import pytest
from sqlalchemy import text
from test_migration_baseline import legacy_file, history, healthy
from test_case_authoring_migration import _prepare_t04
from case_authoring_migrations import upgrade_case_authoring
from etp_migrations import upgrade_etp_library
from evaluation_migrations import upgrade_evaluation, VERSION
from models import db


def test_evaluation_migration_resume_repeat_checksum_restore(legacy_file, tmp_path, monkeypatch):
    app, path = legacy_file
    _prepare_t04(app)
    with app.app_context():
        upgrade_case_authoring(db.engine)
        upgrade_etp_library(db.engine)
        before = history(path)
        backup = tmp_path / 'evaluation-backup.sqlite'
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        import evaluation_migrations
        install = evaluation_migrations.evaluation_guards
        monkeypatch.setattr(evaluation_migrations, 'evaluation_guards', lambda *a: (_ for _ in ()).throw(RuntimeError('injected')))
        with pytest.raises(RuntimeError, match='injected'):
            upgrade_evaluation(db.engine)
        assert db.session.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v':VERSION}).scalar()==0
        monkeypatch.setattr(evaluation_migrations, 'evaluation_guards', install)
        upgrade_evaluation(db.engine);upgrade_evaluation(db.engine)
        assert history(path)==before
        assert db.session.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v':VERSION}).scalar()==1
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE schema_migrations SET checksum=:c WHERE version=:v'), {'c':'bad','v':VERSION})
        with pytest.raises(RuntimeError, match='checksum'):
            upgrade_evaluation(db.engine)
    healthy(path)
    restored=tmp_path/'restored-evaluation.sqlite';shutil.copy2(backup,restored)
    assert history(restored)==before
    healthy(restored)
