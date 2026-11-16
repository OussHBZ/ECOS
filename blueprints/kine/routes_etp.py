"""Protected ETP library, source retention and independent case adaptations."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from uuid import uuid4
from flask import jsonify, request, render_template, send_file, redirect, url_for
from sqlalchemy.exc import IntegrityError
from case_versions import save_draft, digest
from etp_library import CATEGORIES, new_revision, adaptation
from kine_permissions import kine_permission_required
from models import db, KineETPVersion, PatientCase
from . import kine_bp
from .common import error, payload, teacher_id, wants_json


def descriptor(item):
    return {'id': item.id, 'sheet_id': item.sheet_id, 'number': item.number,
            'title': item.title, 'pathology': item.pathology, 'level': item.level,
            'status': item.status, 'sha256': item.content_sha256,
            'source_filename': item.source_filename, 'source_sha256': item.source_sha256,
            'content': json.loads(item.content_json)}


def edit_data():
    data = payload()
    if not request.is_json:
        data = dict(data)
        if any(key in request.form for key in CATEGORIES):
            data['categories'] = {key: request.form.get(key, '') for key in CATEGORIES}
        if 'prompt_trigger' in request.form:
            data['patient_prompts'] = [
                {'id': ident or str(uuid4()), 'category': category, 'trigger': trigger,
                 'text': text, 'master_only': level == 'master'}
                for ident, category, trigger, text, level in zip(
                    request.form.getlist('prompt_id'), request.form.getlist('prompt_category'),
                    request.form.getlist('prompt_trigger'), request.form.getlist('prompt_text'),
                    request.form.getlist('prompt_level')) if trigger.strip() or text.strip()
            ]
        data['validate'] = request.form.get('validate') == 'yes'
        data['confirm_review'] = request.form.get('confirm_review') == 'yes'
    return data


def uploaded_source():
    uploaded = request.files.get('source')
    if not uploaded or not uploaded.filename:
        return None
    return uploaded.read(25 * 1024 * 1024 + 1), uploaded.filename.replace('\\', '/').rsplit('/', 1)[-1]


@kine_bp.route('/etp', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def etp_library():
    if request.method == 'POST':
        try:
            item = new_revision(edit_data(), teacher_id(), source=uploaded_source())
            db.session.commit()
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return error(str(exc))
        if wants_json():
            return jsonify(descriptor(item)), 201
        return redirect(url_for('kine.etp_revision', version_id=item.id))
    items = KineETPVersion.query.order_by(KineETPVersion.created_at.desc(), KineETPVersion.id.desc()).all()
    latest = {}
    for item in items:
        latest.setdefault(item.sheet_id, item)
    filtered = []
    for item in latest.values():
        if request.args.get('pathology') and request.args['pathology'].casefold() not in item.pathology.casefold():
            continue
        if request.args.get('level') and item.level not in (request.args['level'], 'both'):
            continue
        if request.args.get('q') and request.args['q'].casefold() not in (item.title + ' ' + item.pathology).casefold():
            continue
        if request.args.get('category') and not json.loads(item.content_json)['categories'].get(request.args['category']):
            continue
        filtered.append(descriptor(item))
    if wants_json():
        return jsonify(sheets=filtered)
    return render_template('etp_library_kine.html', sheets=filtered, categories=CATEGORIES, item=None)


@kine_bp.route('/etp/versions/<int:version_id>', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def etp_revision(version_id):
    item = KineETPVersion.query.get_or_404(version_id)
    if request.method == 'POST':
        try:
            item = new_revision(edit_data(), teacher_id(), previous=item, source=uploaded_source())
            db.session.commit()
        except (ValueError, TypeError, IntegrityError) as exc:
            db.session.rollback()
            return error(str(exc), 409 if isinstance(exc, IntegrityError) else 400)
        if not wants_json():
            return redirect(url_for('kine.etp_revision', version_id=item.id))
        return jsonify(descriptor(item)), 201
    if wants_json():
        return jsonify(descriptor(item))
    history = KineETPVersion.query.filter_by(sheet_id=item.sheet_id).order_by(KineETPVersion.number.desc()).all()
    return render_template('etp_library_kine.html', sheets=[descriptor(v) for v in history], categories=CATEGORIES, item=descriptor(item))


@kine_bp.route('/etp/versions/<int:version_id>/source')
@kine_permission_required('cases.manage')
def etp_source(version_id):
    item = KineETPVersion.query.get_or_404(version_id)
    if item.source_bytes is None or hashlib.sha256(item.source_bytes).hexdigest() != item.source_sha256:
        return error('Source absente ou empreinte invalide.', 404)
    return send_file(BytesIO(item.source_bytes), as_attachment=True, download_name=item.source_filename,
                     mimetype='application/octet-stream')


@kine_bp.route('/cases/<int:case_id>/etp', methods=['GET', 'POST'])
@kine_permission_required('cases.manage')
def case_etp(case_id):
    case = PatientCase.query.filter_by(id=case_id, specialty='kine').first_or_404()
    associations = deepcopy(case.structured_content.get('etp_associations', []))
    if request.method == 'GET':
        if wants_json():
            return jsonify(associations=associations)
        refs = KineETPVersion.query.filter_by(status='validated').order_by(KineETPVersion.title, KineETPVersion.number.desc()).all()
        terms = [str(t).casefold() for t in (case.subpathology, case.pathology_folder.name if case.pathology_folder else '',
                 (case.patient_record.medical_context or {}).get('main_diagnosis') if case.patient_record else '') if t]
        suggested = {r.id for r in refs if r.pathology and any(t in r.pathology.casefold() or r.pathology.casefold() in t for t in terms)}
        refs.sort(key=lambda r: r.id not in suggested)
        selected = next((a for a in associations if a['id'] == request.args.get('adaptation')), None)
        return render_template('etp_case_kine.html', clinical_case=case, associations=associations,
                               references=refs, categories=CATEGORIES, selected=selected, suggested=suggested)
    data = edit_data()
    try:
        existing = next((a for a in associations if a['id'] == data.get('id')), None)
        if data.get('remove') is True or data.get('remove') == 'yes':
            if not existing:
                return error('Adaptation absente.', 404)
            associations.remove(existing)
        else:
            reference_id = int(data.get('reference_id') or (existing or {}).get('reference_id'))
            reference = db.session.get(KineETPVersion, reference_id)
            if not reference:
                return error('Référence ETP absente.', 404)
            # Every edit requires a new explicit validation for this association.
            merged = {**((existing or {}).get('content', {})), **data}
            if existing:
                merged['id'] = existing['id']
                associations.remove(existing)
            elif data.get('id'):
                raise ValueError('Identifiant d’adaptation inconnu.')
            associations.append(adaptation(reference, merged, teacher_id()))
        content = deepcopy(case.structured_content)
        content['etp_associations'] = associations
        case.structured_content = content
        save_draft(case)
        db.session.commit()
    except (ValueError, TypeError) as exc:
        db.session.rollback()
        return error(str(exc))
    if wants_json():
        return jsonify(associations=associations)
    return redirect(url_for('kine.case_etp', case_id=case.id))
