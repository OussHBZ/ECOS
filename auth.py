from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Student, Teacher, AdminAccess
from datetime import datetime
import re, os
from functools import wraps
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Admin access code - loaded from environment
ADMIN_ACCESS_CODE = os.getenv('ADMIN_CODE', 'ADMIN123')
# Function to check if the request is an AJAX request
def is_ajax_request():
    """Check if the request is an AJAX request"""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Content-Type') == 'application/json' or
        request.accept_mimetypes.best == 'application/json'
    )

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Unified login page for students, teachers, and administrators"""
    if request.method == 'POST':
        login_type = request.form.get('login_type')

        if login_type == 'student':
            student_code = request.form.get('student_code', '').strip()
            password = request.form.get('password', '').strip()

            is_valid, result = Student.validate_apogee_number(student_code)
            if not is_valid:
                flash(result, 'error')
                return redirect(url_for('auth.login'))

            if not password:
                flash('Le mot de passe est obligatoire.', 'error')
                return redirect(url_for('auth.login'))

            student = Student.query.filter_by(student_code=result).first()

            if student and student.check_password(password):
                student.last_login = datetime.utcnow()
                db.session.commit()
                login_user(student)
                session['user_type'] = 'student'
                return redirect(url_for('student.student_interface'))
            else:
                flash('Numéro d\'Apogée ou mot de passe incorrect.', 'error')
                return redirect(url_for('auth.login'))

        elif login_type == 'teacher':
            teacher_login = request.form.get('teacher_login', '').strip()
            password = request.form.get('password', '').strip()

            if not teacher_login or not password:
                flash('Identifiant et mot de passe obligatoires.', 'error')
                return redirect(url_for('auth.login'))

            teacher = Teacher.query.filter_by(login=teacher_login).first()

            if teacher and teacher.check_password(password):
                teacher.last_login = datetime.utcnow()
                db.session.commit()
                session['user_type'] = 'teacher'
                session['teacher_authenticated'] = True
                session['teacher_id'] = teacher.id
                session['teacher_name'] = teacher.name
                return redirect(url_for('teacher.teacher_interface'))
            else:
                flash('Identifiant ou mot de passe incorrect.', 'error')
                return redirect(url_for('auth.login'))

        elif login_type == 'admin':
            access_code = request.form.get('access_code', '').strip()

            if access_code == ADMIN_ACCESS_CODE:
                session['user_type'] = 'admin'
                session['admin_authenticated'] = True

                # Log admin access
                admin_access = AdminAccess.query.filter_by(access_code=access_code).first()
                if not admin_access:
                    admin_access = AdminAccess(access_code=access_code)
                    db.session.add(admin_access)
                admin_access.last_used = datetime.utcnow()
                db.session.commit()

                return redirect(url_for('admin.admin_interface'))
            else:
                flash('Code d\'accès administrateur incorrect.', 'error')
                return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('index'))

def student_required(f):
    """Decorator to require student login - returns JSON for AJAX requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in as student
        if not current_user.is_authenticated or session.get('user_type') != 'student':
            if is_ajax_request():
                logger.warning(f"Unauthorized student AJAX request to {request.path}")
                return jsonify({
                    'error': 'Authentication required',
                    'redirect': url_for('auth.login'),
                    'auth_required': True
                }), 401
            else:
                flash('Accès réservé aux étudiants.', 'error')
                return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    """Decorator to require teacher authentication - returns JSON for AJAX requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in as teacher
        if session.get('user_type') != 'teacher' or not session.get('teacher_authenticated'):
            if is_ajax_request():
                logger.warning(f"Unauthorized teacher AJAX request to {request.path}")
                return jsonify({
                    'error': 'Authentication required',
                    'redirect': url_for('auth.login'),
                    'auth_required': True
                }), 401
            else:
                flash('Accès réservé aux enseignants.', 'error')
                return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require administrator authentication - returns JSON for AJAX requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_type') != 'admin' or not session.get('admin_authenticated'):
            if is_ajax_request():
                logger.warning(f"Unauthorized admin AJAX request to {request.path}")
                return jsonify({
                    'error': 'Authentication required',
                    'redirect': url_for('auth.login'),
                    'auth_required': True
                }), 401
            else:
                flash('Accès réservé aux administrateurs.', 'error')
                return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function