from flask import jsonify, request

from models import PathologyFolder, Student, db

from . import kine_bp
from .common import LEVELS, error, kine_staff_required, payload, teacher_id


@kine_bp.route('/folders', methods=['GET', 'POST'])
@kine_staff_required
def folders_collection():
    if request.method == 'GET':
        include_archived = request.args.get('include_archived') == '1'
        query = PathologyFolder.query.filter_by(specialty='kine')
        if not include_archived:
            query = query.filter_by(is_archived=False)
        return jsonify({'folders': [
            {'id': folder.id, 'name': folder.name, 'specialty': folder.specialty,
             'is_archived': folder.is_archived, 'created_by': folder.created_by}
            for folder in query.order_by(PathologyFolder.name).all()
        ]})
    data = payload()
    name = str(data.get('name') or '').strip()
    if not name:
        return error('Folder name is required')
    if PathologyFolder.query.filter_by(name=name, specialty='kine').first():
        return error('A kine folder with this name already exists', 409)
    folder = PathologyFolder(name=name, specialty='kine', created_by=teacher_id())
    db.session.add(folder)
    db.session.commit()
    return jsonify({'id': folder.id, 'name': folder.name}), 201


@kine_bp.route('/folders/<int:folder_id>', methods=['GET', 'PUT', 'PATCH', 'DELETE'])
@kine_staff_required
def folder_item(folder_id):
    folder = PathologyFolder.query.filter_by(id=folder_id, specialty='kine').first_or_404()
    if request.method == 'GET':
        return jsonify({'id': folder.id, 'name': folder.name, 'is_archived': folder.is_archived})
    if request.method == 'DELETE':
        # Archive folders that still own cases; hard-delete only empty folders.
        if folder.cases:
            folder.is_archived = True
        else:
            db.session.delete(folder)
        db.session.commit()
        return ('', 204)
    data = payload()
    if data.get('name') is not None:
        name = str(data.get('name')).strip()
        if not name:
            return error('Folder name cannot be empty')
        duplicate = PathologyFolder.query.filter(
            PathologyFolder.specialty == 'kine', PathologyFolder.name == name,
            PathologyFolder.id != folder.id,
        ).first()
        if duplicate:
            return error('A kine folder with this name already exists', 409)
        folder.name = name
    if data.get('is_archived') is not None:
        folder.is_archived = str(data.get('is_archived')).lower() in {'1', 'true', 'yes', 'on'}
    db.session.commit()
    return jsonify({'id': folder.id, 'name': folder.name, 'is_archived': folder.is_archived})


@kine_bp.route('/students/<int:student_id>/level', methods=['PUT', 'PATCH'])
@kine_staff_required
def update_student_level(student_id):
    student = Student.query.filter_by(id=student_id, ecos_type='kine').first_or_404()
    level = str(payload().get('level') or '').lower()
    if level not in LEVELS:
        return error("Level must be 'licence' or 'master'")
    student.level = level
    if payload().get('group_name') is not None:
        student.group_name = str(payload().get('group_name') or '').strip() or None
    if payload().get('class_name') is not None:
        student.class_name = str(payload().get('class_name') or '').strip() or None
    db.session.commit()
    return jsonify({'student_id': student.id, 'level': student.level,
                    'group_name': student.group_name, 'class_name': student.class_name})
