"""T04 migration tests use only synthetic temporary SQLite databases."""

import json
import shutil

import pytest
from sqlalchemy import text

from test_migration_baseline import legacy_file, healthy, history
from account_migrations import upgrade_account_lifecycle
from case_version_migrations import upgrade_case_version_storage
from information_access_migrations import VERSION, upgrade_information_access_policy
from models import (
    db, CaseInformation, KineVersionInformation, SimulationDisclosure,
)


def _prepare_t03():
    with db.engine.begin() as connection:
        additions = {
            'interventions': {'intervention_date_text': 'TEXT'},
            'student': {'group_name': 'VARCHAR(100)', 'class_name': 'VARCHAR(100)'},
        }
        for table, columns in additions.items():
            existing = {item['name'] for item in db.inspect(db.engine).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    upgrade_account_lifecycle(db.engine)
    upgrade_case_version_storage(db.engine)


def _remove_t04_storage(app):
    with app.app_context():
        with db.engine.begin() as connection:
            for trigger in ('kine_version_information_no_update', 'kine_version_information_no_delete'):
                connection.exec_driver_sql('DROP TRIGGER IF EXISTS ' + trigger)
            for table in ('simulation_disclosures', 'kine_version_information', 'case_information'):
                connection.exec_driver_sql('DROP TABLE IF EXISTS ' + table)
        db.session.remove()


def test_information_policy_migration_is_repeatable_and_preserves_history(legacy_file, tmp_path):
    app, legacy_path = legacy_file
    _remove_t04_storage(app)
    before = history(legacy_path)
    backup = tmp_path / 't04-before.sqlite'
    shutil.copy2(legacy_path, backup)
    with app.app_context():
        _prepare_t03()
        upgrade_information_access_policy(db.engine)
        upgrade_information_access_policy(db.engine)
        healthy(legacy_path)
        assert CaseInformation.query.count() > 0
        assert KineVersionInformation.query.count() > 0
        assert SimulationDisclosure.query.count() == 0
        reconstructed = KineVersionInformation.query.first()
        assert reconstructed.provenance == 'reconstructed_current_policy'
        # The synthetic legacy case has no saved diagnosis. Migration must not
        # invent an expected physiotherapy diagnosis.
        assert KineVersionInformation.query.filter_by(
            path='expected_physiotherapy_diagnosis',
        ).first() is None
        assert db.session.execute(text(
            'SELECT count(*) FROM schema_migrations WHERE version=:v'
        ), {'v': VERSION}).scalar() == 1
        assert history(legacy_path) == before
    restored = tmp_path / 't04-restored.sqlite'
    shutil.copy2(backup, restored)
    assert history(restored) == before


def test_information_policy_migration_resumes_after_backfill_failure(legacy_file, monkeypatch):
    import information_access_migrations as migration
    app, legacy_path = legacy_file
    _remove_t04_storage(app)
    with app.app_context():
        _prepare_t03()
        original = migration.reconstructed_version_information
        calls = {'count': 0}

        def interrupted(*args, **kwargs):
            calls['count'] += 1
            if calls['count'] == 1:
                raise RuntimeError('injected T04 backfill interruption')
            return original(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(migration, 'reconstructed_version_information', interrupted)
            with pytest.raises(RuntimeError, match='injected T04'):
                upgrade_information_access_policy(db.engine)
        assert db.session.execute(text(
            'SELECT count(*) FROM schema_migrations WHERE version=:v'
        ), {'v': VERSION}).scalar() == 0
        upgrade_information_access_policy(db.engine)
        assert db.session.execute(text(
            'SELECT count(*) FROM schema_migrations WHERE version=:v'
        ), {'v': VERSION}).scalar() == 1
        assert KineVersionInformation.query.count() > 0
