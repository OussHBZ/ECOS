"""Physiotherapy extension blueprint."""

from flask import Blueprint, redirect, session, url_for
from flask_login import current_user

kine_bp = Blueprint('kine', __name__, url_prefix='/kine')


@kine_bp.route('/')
def kine_home():
    """Send authenticated users to their kine workspace."""
    if session.get('user_type') == 'student' and current_user.is_authenticated and current_user.ecos_type == 'kine':
        return redirect(url_for('kine.student_kine_home'))
    if session.get('user_type') == 'teacher' and current_user.is_authenticated and current_user.ecos_type == 'kine':
        return redirect(url_for('kine.teacher_kine_home'))
    if session.get('user_type') == 'admin':
        return redirect(url_for('admin.admin_interface'))
    return redirect(url_for('auth.login'))

# Route modules register handlers on the shared blueprint.
from . import routes_admin, routes_dashboard, routes_student, routes_teacher, routes_import  # noqa: E402,F401
