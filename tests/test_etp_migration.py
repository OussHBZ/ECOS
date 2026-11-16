"""Additive migration is verified only on the temporary legacy fixture."""
from contextlib import closing
import shutil
import sqlite3
import pytest
from sqlalchemy import text
from test_migration_baseline import legacy_file, history, healthy
from test_case_authoring_migration import _prepare_t04
from case_authoring_migrations import upgrade_case_authoring
from etp_migrations import upgrade_etp_library, VERSION
from models import db, KineETPVersion


def test_etp_migration_repeat_resume_backup_restore_and_checksum(legacy_file, tmp_path, monkeypatch):
    app, path = legacy_file
    _prepare_t04(app)
    with app.app_context():
        upgrade_case_authoring(db.engine)
        with db.engine.begin() as conn:
            conn.exec_driver_sql('DROP TABLE IF EXISTS kine_etp_versions')
        before = history(path)
        backup = tmp_path / 'before-etp.sqlite'
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        import etp_migrations
        install = etp_migrations.etp_triggers
        def interrupted(*args, **kwargs):
            raise RuntimeError('injected interruption')
        monkeypatch.setattr(etp_migrations, 'etp_triggers', interrupted)
        with pytest.raises(RuntimeError, match='injected'):
            upgrade_etp_library(db.engine)
        assert db.session.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar() == 0
        monkeypatch.setattr(etp_migrations, 'etp_triggers', install)
        upgrade_etp_library(db.engine)
        upgrade_etp_library(db.engine)
        assert KineETPVersion.__tablename__ in db.inspect(db.engine).get_table_names()
        assert db.session.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar() == 1
        assert history(path) == before
        with db.engine.begin() as conn:
            conn.execute(text('UPDATE schema_migrations SET checksum=:c WHERE version=:v'), {'c': 'tampered', 'v': VERSION})
        with pytest.raises(RuntimeError, match='checksum'):
            upgrade_etp_library(db.engine)
    healthy(path)
    restored = tmp_path / 'restored-etp.sqlite'
    shutil.copy2(backup, restored)
    assert history(restored) == before
    healthy(restored)
    with closing(sqlite3.connect(restored)) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='kine_etp_versions'").fetchone()
