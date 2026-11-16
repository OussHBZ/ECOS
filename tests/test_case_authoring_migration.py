"""T05 migration tests use only synthetic temporary SQLite databases."""

from contextlib import closing
import shutil
import sqlite3

import pytest
from sqlalchemy import text

from test_migration_baseline import healthy, history, legacy_file
from account_migrations import upgrade_account_lifecycle
from case_version_migrations import upgrade_case_version_storage
from information_access_migrations import upgrade_information_access_policy
from case_authoring_migrations import (
    CASE_COLUMNS, MEDICATION_COLUMNS, VERSION, upgrade_case_authoring,
)
from models import db, KineCaseDocument


def _prepare_t04(app):
    with app.app_context():
        with db.engine.begin() as connection:
            additions = {
                'interventions': {'intervention_date_text': 'TEXT'},
                'student': {'group_name': 'VARCHAR(100)', 'class_name': 'VARCHAR(100)'},
            }
            for table, columns in additions.items():
                existing = {item['name'] for item in db.inspect(db.engine).get_columns(table)}
                for name, definition in columns.items():
                    if name not in existing:
                        connection.exec_driver_sql(
                            f'ALTER TABLE {table} ADD COLUMN {name} {definition}'
                        )
        upgrade_account_lifecycle(db.engine)
        upgrade_case_version_storage(db.engine)
        upgrade_information_access_policy(db.engine)
        with db.engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS kine_case_documents')
            connection.execute(text('DELETE FROM schema_migrations WHERE version=:v'), {'v': VERSION})
            for table, columns in (('patient_case1', CASE_COLUMNS), ('medications', MEDICATION_COLUMNS)):
                existing = {item['name'] for item in db.inspect(db.engine).get_columns(table)}
                for name, _ in columns:
                    if name in existing:
                        connection.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN {name}')
        db.session.remove()


def test_t05_migration_repeat_backup_restore_and_preserve_history(legacy_file, tmp_path):
    app, path = legacy_file
    _prepare_t04(app)
    before = history(path)
    backup = tmp_path / 'before-t05.sqlite'
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)

    with app.app_context():
        upgrade_case_authoring(db.engine)
        upgrade_case_authoring(db.engine)
        assert KineCaseDocument.__tablename__ in db.inspect(db.engine).get_table_names()
        assert {name for name, _ in CASE_COLUMNS} <= {
            item['name'] for item in db.inspect(db.engine).get_columns('patient_case1')
        }
        assert {name for name, _ in MEDICATION_COLUMNS} <= {
            item['name'] for item in db.inspect(db.engine).get_columns('medications')
        }
        assert db.session.execute(text(
            'SELECT count(*) FROM schema_migrations WHERE version=:v'
        ), {'v': VERSION}).scalar() == 1
    assert history(path) == before
    healthy(path)

    restored = tmp_path / 'restored-before-t05.sqlite'
    shutil.copy2(backup, restored)
    assert history(restored) == before
    healthy(restored)
    with closing(sqlite3.connect(restored)) as connection:
        assert 'difficulty' not in {
            item[1] for item in connection.execute('PRAGMA table_info(patient_case1)')
        }


def test_t05_migration_resumes_after_table_creation_failure(legacy_file, monkeypatch):
    app, _ = legacy_file
    _prepare_t04(app)
    original = KineCaseDocument.__table__.create
    calls = {'count': 0}

    def interrupted(*args, **kwargs):
        calls['count'] += 1
        if calls['count'] == 1:
            raise RuntimeError('injected T05 table failure')
        return original(*args, **kwargs)

    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr(KineCaseDocument.__table__, 'create', interrupted)
            with pytest.raises(RuntimeError, match='injected T05'):
                upgrade_case_authoring(db.engine)
        assert db.session.execute(text(
            'SELECT count(*) FROM schema_migrations WHERE version=:v'
        ), {'v': VERSION}).scalar() == 0
        upgrade_case_authoring(db.engine)
        assert KineCaseDocument.__tablename__ in db.inspect(db.engine).get_table_names()

