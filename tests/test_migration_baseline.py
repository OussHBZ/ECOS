"""T01: synthetic file databases only; no historical result is recomputed.

Exercise the existing additive helper, not init_database/reset/create_app.
These tests do not certify app.py's different startup migration path.
"""
from contextlib import closing
from datetime import date, datetime
import shutil
import sqlite3

import pytest
from flask import Flask
from sqlalchemy.engine import Connection

from init_db import apply_additive_schema_updates
from models import db, Intervention, PatientCase, PatientRecord, SimulationSession, Student, StudentPerformance


def history(path):
    with closing(sqlite3.connect(path)) as connection:
        return {
            'standard': connection.execute(
                'SELECT id,student_id,case_number,evaluation_results_json,conversation_transcript_json '
                'FROM student_performance ORDER BY id').fetchall(),
            'kine': connection.execute(
                'SELECT id,student_id,clinical_case_id,status,conversation,evaluation_results,completed_at '
                'FROM simulation_sessions ORDER BY id').fetchall(),
            'accounts': connection.execute(
                'SELECT id,student_code,name,ecos_type FROM student ORDER BY id').fetchall(),
            'cases': connection.execute(
                'SELECT id,case_number,specialty,diagnosis FROM patient_case1 ORDER BY id').fetchall(),
            'dates': connection.execute('SELECT id,intervention_date FROM interventions ORDER BY id').fetchall(),
        }


def healthy(path):
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.fixture()
def legacy_file(tmp_path):
    path = tmp_path / 'synthetic-legacy.sqlite'
    app = Flask('migration-fixture', instance_path=str(tmp_path))
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///' + path.as_posix(),
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        standard = Student(student_code='810001', name='Fictif Standard', ecos_type='standard', level='both')
        kine = Student(student_code='810002', name='Fictif Kine', ecos_type='kine', level='both')
        standard_case = PatientCase(case_number='FIX-STANDARD', specialty='standard-fixture')
        kine_case = PatientCase(case_number='FIX-KINE', specialty='kine')
        db.session.add_all([standard, kine, standard_case, kine_case])
        db.session.flush()
        record = PatientRecord(clinical_case=kine_case)
        record.interventions.append(Intervention(intervention_type='fixture', intervention_date=date(2020, 1, 2)))
        db.session.add(record)
        old_result = {'schema_version': 1, 'points_earned': 9, 'passed': False,
                      'legacy_marker': 'keep-exactly'}
        db.session.add(StudentPerformance(student_id=standard.id, case_number=standard_case.case_number,
            evaluation_results_json='{"legacy_marker": "standard-preserve", "score": 7}',
            conversation_transcript_json='[{"role":"human","content":"Fictif standard"}]'))
        db.session.add(SimulationSession(student_id=kine.id, clinical_case_id=kine_case.id,
            status='completed', conversation=[{'role': 'human', 'content': 'Fictif kine'}],
            evaluation_results=old_result, completed_at=datetime(2020, 1, 3)))
        db.session.commit()
        # Current model minus selected old columns: representative legacy fixture,
        # not a reconstruction of the user's actual historical database.
        with db.engine.begin() as connection:
            for table, column in [('interventions', 'intervention_date_text'),
                                  ('student', 'group_name'), ('student', 'class_name')]:
                connection.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN {column}')
        db.session.remove()
        db.engine.dispose()
    yield app, path
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_existing_migration_repeat_backup_restore_preserves_both_histories(legacy_file, tmp_path):
    app, path = legacy_file
    original = history(path)
    healthy(path)
    backup = tmp_path / 'before-migration.sqlite'
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    assert history(backup) == original
    healthy(backup)
    with app.app_context():
        apply_additive_schema_updates()
        apply_additive_schema_updates()
        assert db.session.get(Student, 1).level == 'both'  # Standard historical field intact.
        assert db.session.get(Student, 2).level == 'licence'  # Existing helper's documented repair.
        assert Intervention.query.one().timing == '2020-01-02'
        assert {'group_name', 'class_name'} <= {c['name'] for c in db.inspect(db.engine).get_columns('student')}
        db.session.remove()
        db.engine.dispose()
    assert history(path) == original  # Raw stored results/conversations, no re-evaluation.
    healthy(path)
    restored = tmp_path / 'restored-pre-migration.sqlite'
    shutil.copyfile(backup, restored)  # Never overwrite a real or currently open database.
    assert history(restored) == original
    healthy(restored)
    with closing(sqlite3.connect(restored)) as connection:
        assert 'intervention_date_text' not in {c[1] for c in connection.execute('PRAGMA table_info(interventions)')}


def test_existing_migration_can_resume_after_injected_ddl_failure(legacy_file, monkeypatch):
    app, path = legacy_file
    original = history(path)
    execute = Connection.exec_driver_sql
    failed = [False]

    def fail_once(connection, statement, *args, **kwargs):
        if 'ADD COLUMN group_name' in statement and not failed[0]:
            failed[0] = True
            raise RuntimeError('injected migration interruption')
        return execute(connection, statement, *args, **kwargs)

    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setattr(Connection, 'exec_driver_sql', fail_once)
            with pytest.raises(RuntimeError, match='injected migration interruption'):
                apply_additive_schema_updates()
        assert failed[0]
        assert history(path) == original
        apply_additive_schema_updates()
        apply_additive_schema_updates()
        assert {'group_name', 'class_name'} <= {c['name'] for c in db.inspect(db.engine).get_columns('student')}
        db.session.remove()
        db.engine.dispose()
    assert history(path) == original
    healthy(path)
