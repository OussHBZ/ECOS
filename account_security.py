"""Server identity revocation, workspace boundaries and request forgery defense."""
import hmac
import secrets
from urllib.parse import urlsplit

from flask import flash, jsonify, redirect, request, session, url_for, send_from_directory
from flask_login import current_user, logout_user
from models import Student, Teacher, AdminAccess, PatientCase, StudentPerformance, db


def standard_performance_query():
    """Filter legacy results by both account and case, without rewriting history."""
    return StudentPerformance.query.join(Student).outerjoin(
        PatientCase, StudentPerformance.case_number == PatientCase.case_number
    ).filter(Student.ecos_type == 'standard',
             db.func.lower(db.func.trim(db.func.coalesce(PatientCase.specialty, ''))) != 'kine')


def admin_profile():
    """Persisted server authority; legacy admin cookies have technical rights only."""
    if session.get('user_type') != 'admin' or not session.get('admin_authenticated'):
        return None
    access_id = session.get('admin_access_id')
    if access_id is None:
        return 'technical'
    access = db.session.get(AdminAccess, access_id, populate_existing=True)
    return access.admin_profile if access and access.admin_profile in ('technical', 'pedagogical') else None


def csrf_token():
    if not session.get('_csrf_token'):
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


def revoke_sessions(account):
    account.auth_version = (account.auth_version or 0) + 1


def legacy_pdf_download(filename):
    """Legacy standard download is bound to its authenticated browser session.

    Kiné exports are always regenerated through an authorized simulation ID;
    a known filename must never bypass that check via the old generic route.
    """
    import tempfile
    if (not current_user.is_authenticated or session.get('user_type') != 'student'
            or getattr(current_user, 'ecos_type', None) != 'standard'
            or filename != session.get('last_pdf') or '..' in filename
            or '/' in filename or '\\' in filename):
        return jsonify(error='Rapport indisponible.'), 404
    return send_from_directory(tempfile.gettempdir(), filename, as_attachment=True, mimetype='application/pdf')


def session_account_valid():
    role = session.get('user_type')
    model = {'student': Student, 'teacher': Teacher}.get(role)
    if model is None:
        return role != 'admin' or admin_profile() is not None
    if not current_user.is_authenticated or not isinstance(current_user._get_current_object(), model):
        return False
    account = db.session.get(model, current_user.id, populate_existing=True)
    if account is None or not account.is_active:
        return False
    # Legacy sessions are accepted only until the first explicit revocation.
    if session.get('auth_version', 0) != (account.auth_version or 0):
        return False
    if role == 'teacher' and (not session.get('teacher_authenticated') or session.get('teacher_id') != account.id):
        return False
    return True


def protect_request():
    role = session.get('user_type')
    if role in ('student', 'teacher', 'admin') and not session_account_valid():
        logout_user()
        session.clear()
        if request.is_json or request.accept_mimetypes.best == 'application/json' or request.headers.get('X-Requested-With'):
            return jsonify(error='Compte indisponible ou session révoquée.', auth_required=True), 401
        flash('Compte indisponible ou session révoquée. Reconnectez-vous.', 'error')
        return redirect(url_for('auth.login'))
    # Standard teacher endpoints cannot bypass Kiné permissions using direct IDs
    # or change the workspace of a case through an old editing endpoint.
    if request.blueprint == 'teacher' and session.get('user_type') == 'teacher' and current_user.is_authenticated:
        values = request.view_args or {}
        data = request.get_json(silent=True) or request.form
        nested = data.get('edited_data') if isinstance(data, dict) else None
        nested = nested if isinstance(nested, dict) else {}
        case_number = values.get('case_number') or data.get('case_number') or nested.get('case_number')
        case = PatientCase.query.filter_by(case_number=str(case_number)).first() if case_number else None
        student = db.session.get(Student, values['student_id']) if values.get('student_id') else None
        performance = db.session.get(StudentPerformance, values['performance_id']) if values.get('performance_id') else None
        if performance:
            student = performance.student
            case = PatientCase.query.filter_by(case_number=performance.case_number).first()
        if ((case and str(case.specialty or '').lower() == 'kine')
                or (student and student.ecos_type == 'kine')
                or str(data.get('specialty') or nested.get('specialty') or '').strip().lower() == 'kine'):
            return jsonify(error='Ressource indisponible dans cet espace.'), 404
    protected_mutation = (request.blueprint in ('admin', 'kine', 'teacher') and
                          ((role == 'admin' and session.get('admin_authenticated')) or current_user.is_authenticated))
    login_mutation = request.endpoint in ('auth.login', 'auth.logout')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and (protected_mutation or login_mutation):
        origin = request.headers.get('Origin')
        target = urlsplit(request.host_url)
        supplied = urlsplit(origin) if origin else None
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (
            supplied and (supplied.scheme, supplied.netloc) != (target.scheme, target.netloc)
        ):
            return jsonify(error='Origine de requête refusée.'), 403
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token') or ''
        expected = session.get('_csrf_token') or ''
        if not expected or not hmac.compare_digest(str(token), str(expected)):
            return jsonify(error='Jeton CSRF absent ou invalide.'), 403
