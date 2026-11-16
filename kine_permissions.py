"""D02: explicit Kiné permissions and current student-following scope.

Legacy standard ECOS decorators remain separate. No historical activity grants
authority. All object queries use the same live scope, including file exports.
"""
from functools import wraps
from flask import jsonify, session
from flask_login import current_user
from account_security import admin_profile
from models import (db, Exam, PatientCase, SimulationSession, Student,
                    TeacherStudentScope, TeacherGroupScope)


PERMISSIONS = {
    'technical': frozenset({'accounts.manage', 'scopes.manage', 'folders.manage', 'students.level'}),
    'pedagogical': frozenset({'accounts.manage', 'scopes.manage', 'folders.manage', 'students.level', 'cases.manage', 'exams.manage', 'results.read', 'results.review', 'thresholds.manage'}),
    'teacher': frozenset({'folders.manage', 'students.level', 'cases.manage', 'exams.manage', 'results.read', 'results.review'}),
}


def is_pedagogical_admin():
    return admin_profile() == 'pedagogical'


def actor():
    profile = admin_profile()
    if profile:
        return profile
    if (session.get('user_type') == 'teacher' and session.get('teacher_authenticated')
            and current_user.is_authenticated and current_user.is_active
            and current_user.ecos_type == 'kine' and session.get('teacher_id') == current_user.id):
        return 'teacher'
    return None


def kine_permission_required(permission):
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            role = actor()
            if role is None and session.get('user_type') == 'teacher':
                from auth import teacher_required
                return teacher_required(function)(*args, **kwargs)
            if permission not in PERMISSIONS.get(role, ()):
                return jsonify(error='Accès non autorisé.'), 403 if role else 401
            return function(*args, **kwargs)
        return guarded
    return decorate


def student_scope():
    if actor() in ('technical', 'pedagogical'):
        return Student.ecos_type == 'kine'
    if actor() != 'teacher':
        return db.false()
    tid = current_user.id
    direct = db.select(TeacherStudentScope.student_id).where(TeacherStudentScope.teacher_id == tid)
    groups = db.select(TeacherGroupScope.group_name).where(TeacherGroupScope.teacher_id == tid)
    return db.and_(Student.ecos_type == 'kine', db.or_(Student.id.in_(direct), Student.group_name.in_(groups)))


def scoped_students():
    return Student.query.filter(student_scope())


def require_student(student_id):
    return scoped_students().filter(Student.id == student_id).first_or_404()


def scoped_simulations():
    return SimulationSession.query.join(Student).join(PatientCase).filter(
        student_scope(), PatientCase.specialty == 'kine')


def require_simulation(session_id):
    return scoped_simulations().filter(SimulationSession.id == session_id).first_or_404()


def scoped_exams():
    query = Exam.query
    if is_pedagogical_admin():
        return query
    # A changed assignment must also revoke access to an old exam's roster.
    allowed = {s.id for s in scoped_students().all()}
    groups = {s.group_name for s in Student.query.filter_by(ecos_type='kine').all() if s.id not in allowed}
    ids = [e.id for e in query.all() if all(s.id in allowed for s in e.students)
           and not (set(e.group_names or []) & groups)]
    return Exam.query.filter(Exam.id.in_(ids))
