"""T03 storage migration only: synthetic SQLite, no real historical reconstruction."""
from contextlib import closing
import shutil
import sqlite3
import json
import re
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from models import db, Exam, KineCaseVersion, PatientCase, SimulationSession, KineCaseAvailability, ExamCaseVersion
from init_db import apply_additive_schema_updates
from case_version_migrations import VERSION, upgrade_case_version_storage
from test_migration_baseline import legacy_file, history, healthy


def remove_storage_columns(app):
    with app.app_context():
        apply_additive_schema_updates()
        with db.engine.begin() as connection:
            connection.execute(text("DELETE FROM schema_migrations WHERE version='004_information_access_policy'"))
            for trigger in ['kine_version_information_no_update', 'kine_version_information_no_delete']:
                connection.exec_driver_sql('DROP TRIGGER IF EXISTS ' + trigger)
            for table in ['simulation_disclosures', 'kine_version_information', 'case_information']:
                connection.exec_driver_sql('DROP TABLE IF EXISTS ' + table)
            connection.execute(text('DELETE FROM schema_migrations WHERE version=:v'), {'v': VERSION})
            for trigger in ['kine_simulation_reference_immutable', 'kine_simulation_version_insert', 'kine_simulation_version_update']:
                connection.exec_driver_sql('DROP TRIGGER IF EXISTS ' + trigger)
            # Synthetic fixture only: SQLite cannot DROP a column participating
            # in a table-level FK. Rebuild the old fixture schema faithfully.
            removed = {'case_version_id', 'frozen_student_level', 'evaluation_reference_json', 'student_reference_json', 'reference_origin'}
            ddl = connection.execute(text("SELECT sql FROM sqlite_master WHERE name='simulation_sessions'")).scalar()
            lines = [line for line in ddl.splitlines() if not any(re.match(r'\s*' + name + r'\s', line) for name in removed)
                     and 'FOREIGN KEY(case_version_id)' not in line]
            ddl = re.sub(r',\s*\)', '\n)', '\n'.join(lines))
            ddl = re.sub(r'CREATE TABLE simulation_sessions', 'CREATE TABLE simulation_sessions_fixture_old', ddl, count=1)
            connection.exec_driver_sql(ddl)
            kept = [c['name'] for c in db.inspect(db.engine).get_columns('simulation_sessions') if c['name'] not in removed]
            names = ','.join(kept)
            connection.exec_driver_sql(f'INSERT INTO simulation_sessions_fixture_old ({names}) SELECT {names} FROM simulation_sessions')
            connection.exec_driver_sql('DROP TABLE simulation_sessions')
            connection.exec_driver_sql('ALTER TABLE simulation_sessions_fixture_old RENAME TO simulation_sessions')
            for table in ['exam_case_versions', 'kine_case_availability', 'kine_case_versions']:
                connection.exec_driver_sql('DROP TABLE ' + table)
        db.session.remove()


def test_storage_migration_repeat_backup_restore_and_uncertain_provenance(legacy_file):
    app, path = legacy_file
    remove_storage_columns(app)
    original = history(path)
    backup = path.with_name('before-version-storage.sqlite')
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    with app.app_context():
        upgrade_case_version_storage(db.engine)
        upgrade_case_version_storage(db.engine)
        version = KineCaseVersion.query.one()
        simulation = SimulationSession.query.one()
        assert version.provenance == 'reconstructed_current'
        assert simulation.reference_origin == 'reconstructed_current_not_historical'
        assert json.loads(simulation.evaluation_reference_json)['provenance'] == 'reconstructed_current_not_historical'
        assert simulation.case_version_id == version.id
        availability = KineCaseAvailability.query.one()
        assert availability.version_id == version.id
        audience = json.loads(availability.audience_json)
        assert audience['provenance'] == 'reconstructed_current_access'
        assert audience['legacy_levels'] == ['licence', 'master']
        assert ExamCaseVersion.query.count() == 0
        assert db.session.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar() == 1
    assert history(path) == original
    healthy(path)
    restored = path.with_name('restored-pre-version-storage.sqlite')
    shutil.copyfile(backup, restored)
    assert history(restored) == original
    healthy(restored)
    with closing(sqlite3.connect(restored)) as connection:
        assert 'case_version_id' not in {row[1] for row in connection.execute('PRAGMA table_info(simulation_sessions)')}


def test_storage_migration_recovers_partial_ddl_without_stamp(legacy_file, monkeypatch):
    app, path = legacy_file
    remove_storage_columns(app)
    original = history(path)
    execute = Connection.exec_driver_sql
    def interrupted(connection, statement, *args, **kwargs):
        if 'ADD COLUMN student_reference_json' in statement:
            raise RuntimeError('fixture version DDL interruption')
        return execute(connection, statement, *args, **kwargs)
    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr(Connection, 'exec_driver_sql', interrupted)
            with pytest.raises(RuntimeError, match='fixture version DDL'):
                upgrade_case_version_storage(db.engine)
        assert db.session.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'), {'v': VERSION}).scalar() == 0
        upgrade_case_version_storage(db.engine)
    assert history(path) == original
    healthy(path)


def test_storage_backfill_transaction_rolls_back_and_retries(legacy_file, monkeypatch):
    import case_version_migrations
    app, path = legacy_file
    remove_storage_columns(app)
    original = history(path)
    freeze = case_version_migrations.freeze_simulation
    def interrupted(*args, **kwargs):
        freeze(*args, **kwargs)
        raise RuntimeError('fixture backfill interruption')
    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr(case_version_migrations, 'freeze_simulation', interrupted)
            with pytest.raises(RuntimeError, match='fixture backfill'):
                upgrade_case_version_storage(db.engine)
        assert KineCaseVersion.query.count() == 0
        assert history(path) == original
        upgrade_case_version_storage(db.engine)
        assert KineCaseVersion.query.count() == 1
    assert history(path) == original
    healthy(path)


def test_storage_migration_refuses_changed_checksum(legacy_file):
    app, path = legacy_file
    remove_storage_columns(app)
    with app.app_context():
        upgrade_case_version_storage(db.engine)
        db.session.execute(text('UPDATE schema_migrations SET checksum=:c WHERE version=:v'), {'c': 'invalid-fixture', 'v': VERSION})
        db.session.commit()
        with pytest.raises(RuntimeError, match='checksum mismatch'):
            upgrade_case_version_storage(db.engine)


def test_storage_migration_marks_existing_exam_selection_as_reconstructed(legacy_file):
    app, path = legacy_file
    with app.app_context():
        case = PatientCase.query.filter_by(specialty='kine').one()
        exam = Exam(name='Synthetic legacy exam', start_at=datetime.utcnow() + timedelta(days=1),
                    end_at=datetime.utcnow() + timedelta(days=1, hours=1),
                    max_duration_minutes=20, group_names=[])
        exam.cases.append(case)
        db.session.add(exam)
        db.session.commit()
        exam_id, case_id = exam.id, case.id
    remove_storage_columns(app)
    with app.app_context():
        upgrade_case_version_storage(db.engine)
        selection = db.session.get(ExamCaseVersion, (exam_id, case_id))
        assert selection is not None
        assert selection.provenance == 'reconstructed_current_selection'
        assert selection.version.provenance == 'reconstructed_current'
