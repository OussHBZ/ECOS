from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, Student, TeacherAccess, AdminAccess
from datetime import datetime
import re, os
from functools import wraps
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# Access codes - you can change these or load from environment
TEACHER_ACCESS_CODE = os.getenv('TEACHER_CODE', 'TEACHER123')
ADMIN_ACCESS_CODE = os.getenv('ADMIN_CODE', 'ADMIN123')

def is_ajax_request():
    """Check if the request is an AJAX request"""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Content-Type') == 'application/json' or
        request.accept_mimetypes.best == 'application/json' or
        request.path.startswith(('/admin/', '/teacher/', '/student/'))
    )

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Unified login page for students, teachers, and administrators"""
    if request.method == 'POST':
        login_type = request.form.get('login_type')
        
        if login_type == 'student':
            student_code = request.form.get('student_code', '').strip()
            student_name = request.form.get('student_name', '').strip()
            
            # Updated validation for Numéro d'Apogée (6-7 digits)
            if not re.match(r'^\d{6,7}$', student_code):
                flash('Le numéro d\'Apogée doit contenir entre 6 et 7 chiffres.', 'error')
                return redirect(url_for('auth.login'))
            
            if not student_name:
                flash('Le nom est obligatoire.', 'error')
                return redirect(url_for('auth.login'))
            
            # Validate using the new validation method
            is_valid, result = Student.validate_apogee_number(student_code)
            if not is_valid:
                flash(result, 'error')  # result contains the error message
                return redirect(url_for('auth.login'))
            
            validated_code = result  # result contains the validated code
            
            # Check if student exists
            student = Student.query.filter_by(student_code=validated_code).first()
            
            if student:
                # Existing student - verify name
                if student.name.lower() == student_name.lower():
                    student.last_login = datetime.utcnow()
                    db.session.commit()
                    login_user(student)
                    session['user_type'] = 'student'
                    flash(f'Connexion réussie avec le numéro d\'Apogée {validated_code}', 'success')
                    return redirect(url_for('student.student_interface'))
                else:
                    flash('Numéro d\'Apogée ou nom incorrect.', 'error')
                    return redirect(url_for('auth.login'))
            else:
                # New student - create account
                try:
                    student = Student(
                        student_code=validated_code,
                        name=student_name
                    )
                    db.session.add(student)
                    db.session.commit()
                    login_user(student)
                    session['user_type'] = 'student'
                    flash(f'Compte créé avec succès avec le numéro d\'Apogée {validated_code}!', 'success')
                    return redirect(url_for('student.student_interface'))
                except Exception as e:
                    logger.error(f"Error creating student account: {str(e)}")
                    flash('Erreur lors de la création du compte. Le numéro d\'Apogée pourrait déjà être utilisé.', 'error')
                    return redirect(url_for('auth.login'))
                
        elif login_type == 'teacher':
            access_code = request.form.get('access_code', '').strip()
            
            if access_code == TEACHER_ACCESS_CODE:
                session['user_type'] = 'teacher'
                session['teacher_authenticated'] = True
                
                # Log teacher access
                teacher_access = TeacherAccess.query.filter_by(access_code=access_code).first()
                if not teacher_access:
                    teacher_access = TeacherAccess(access_code=access_code)
                    db.session.add(teacher_access)
                teacher_access.last_used = datetime.utcnow()
                db.session.commit()
                
                return redirect(url_for('teacher.teacher_interface'))
            else:
                flash('Code d\'accès incorrect.', 'error')
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