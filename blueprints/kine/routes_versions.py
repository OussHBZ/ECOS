"""Private publication and explicit version assignment management."""
import json
from flask import jsonify, redirect, request, send_file, session, url_for
from io import BytesIO
from sqlalchemy.exc import IntegrityError
from models import db, PatientCase, Student, KineCaseVersion, KineCaseAvailability
from kine_permissions import kine_permission_required, scoped_students
from case_versions import audience_payload, availability_audience, canonical, publish
from .routes_teacher import _publication_issues
from . import kine_bp
from .common import error, payload, wants_json


def _metadata(version):
    return dict(id=version.id, case_id=version.case_id, number=version.number,
                status=version.status, sha256=version.content_sha256,
                provenance=version.provenance,
                published_at=version.published_at.isoformat() if version.published_at else None)


def _availability_metadata(availability):
    return {
        'case_id': availability.case_id,
        'version_id': availability.version_id,
        'audience': availability_audience(availability),
        'updated_actor': availability.updated_actor,
    }


def _actor():
    return (f"teacher:{session['teacher_id']}" if session.get('user_type') == 'teacher'
            else f"pedagogical-admin:{session.get('admin_access_id')}")


@kine_bp.route('/cases/<int:case_id>/versions', methods=['GET'])
@kine_permission_required('cases.manage')
def case_versions_collection(case_id):
    PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    return jsonify(versions=[_metadata(v) for v in KineCaseVersion.query.filter_by(case_id=case_id).order_by(KineCaseVersion.number)])


@kine_bp.route('/cases/<int:case_id>/versions/publish', methods=['POST'])
@kine_permission_required('cases.manage')
def publish_case_version(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    data = payload()
    if set(data) - {'expected_sha256'}:
        return error('Champs de publication invalides.')
    # Only cases authored through the T05 wizard carry progress metadata.
    # Publishing a legacy/API case must not retroactively make it subject to
    # fields that did not exist in its original authoring workflow.
    uses_t05_wizard = bool(case.authoring_progress_json)
    issues = _publication_issues(case) if uses_t05_wizard else []
    if issues:
        return jsonify({
            'error': 'Publication refusée : informations obligatoires manquantes.',
            'validation_issues': issues,
        }), 409
    try:
        if uses_t05_wizard:
            case.authoring_status = 'published'
        version = publish(case, _actor(), data.get('expected_sha256'))
        db.session.commit()
        return jsonify(_metadata(version)), 201
    except (ValueError, IntegrityError) as exc:
        db.session.rollback()
        return error('Publication refusée : brouillon modifié ou publication concurrente.', 409)


@kine_bp.route('/cases/<int:case_id>/versions/<int:version_id>', methods=['GET'])
@kine_permission_required('cases.manage')
def case_version_item(case_id, version_id):
    PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    version = KineCaseVersion.query.filter_by(id=version_id, case_id=case_id).first_or_404()
    return jsonify(**_metadata(version), content=json.loads(version.content_json))


@kine_bp.route('/cases/<int:case_id>/versions/<int:version_id>/download', methods=['GET'])
@kine_permission_required('cases.manage')
def case_version_download(case_id, version_id):
    PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    version = KineCaseVersion.query.filter_by(id=version_id, case_id=case_id).first_or_404()
    return send_file(BytesIO(version.content_json.encode('utf-8')), as_attachment=True,
        mimetype='application/json', download_name=f'case_{case_id}_version_{version.number}.json')


@kine_bp.route('/cases/<int:case_id>/availability', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@kine_permission_required('cases.manage')
def case_availability(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    availability = db.session.get(KineCaseAvailability, case_id)
    if request.method == 'GET':
        return jsonify(_availability_metadata(availability) if availability else {
            'case_id': case_id, 'version_id': None, 'audience': {}, 'updated_actor': None,
        })
    data = payload()
    if request.method == 'DELETE' or str(data.get('disable') or '').lower() in ('1', 'true', 'yes', 'on'):
        if availability:
            db.session.delete(availability)
            db.session.commit()
        if wants_json():
            return ('', 204)
        return redirect(url_for('kine.teacher_dashboard'))
    try:
        version_id = int(data.get('version_id'))
    except (TypeError, ValueError):
        return error('Sélectionnez une version publiée.')
    version = KineCaseVersion.query.filter_by(id=version_id, case_id=case.id, status='published').first()
    if not version:
        return error('La version attribuée doit être une publication de ce cas.', 400)
    get_list = data.getlist if hasattr(data, 'getlist') else lambda key: data.get(key)
    student_ids, group_names = get_list('student_ids'), get_list('group_names')
    if student_ids is not None and not isinstance(student_ids, list):
        student_ids = [student_ids]
    if group_names is not None and not isinstance(group_names, list):
        group_names = [group_names]
    try:
        student_ids = list(dict.fromkeys(int(value) for value in student_ids or []))
    except (TypeError, ValueError):
        return error('La sélection des étudiants est invalide.')
    group_names = sorted({str(value).strip() for value in group_names or [] if str(value).strip()})
    selected = scoped_students().filter(Student.id.in_(student_ids)).all() if student_ids else []
    if len(selected) != len(student_ids):
        return error('Un étudiant attribué est hors du périmètre de suivi.', 403)
    group_students = Student.query.filter(
        Student.ecos_type == 'kine', Student.group_name.in_(group_names)
    ).all() if group_names else []
    allowed_ids = {student.id for student in scoped_students().all()}
    if any(student.id not in allowed_ids for student in group_students):
        return error('Un groupe attribué dépasse le périmètre de suivi.', 403)
    existing_groups = {student.group_name for student in group_students}
    if set(group_names) - existing_groups:
        return error('Un groupe attribué est introuvable.')
    if not student_ids and not group_names:
        return error('Attribuez la version à au moins un étudiant ou un groupe.')
    audience = audience_payload(student_ids, group_names)
    if availability is None:
        availability = KineCaseAvailability(case_id=case.id)
        db.session.add(availability)
    availability.version = version
    availability.audience_json = canonical(audience)
    availability.updated_actor = _actor()
    db.session.commit()
    if wants_json():
        return jsonify(_availability_metadata(availability))
    return redirect(url_for('kine.teacher_dashboard'))
