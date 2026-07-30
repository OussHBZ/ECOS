"""Persistent, review-first bulk import workflow for ECOS Kiné DOCX cases."""

import hashlib
import os
import tempfile
import uuid
import zipfile
from datetime import datetime
from io import BytesIO

from flask import (
    current_app, jsonify, redirect, render_template, request, send_file, url_for,
)
from sqlalchemy import func
from werkzeug.utils import secure_filename

from auth import teacher_required
from document_processor import DocumentExtractionAgent
from models import (
    Incident, KineCaseDraft, KineCaseImportBatch, PathologyFolder, PatientCase,
    db,
)

from . import kine_bp
from .common import (
    CASE_LEVELS, MODES, canonicalize_medical_tests, error, payload,
    prune_empty, teacher_id, wants_json,
)
from .routes_teacher import (
    _apply_case, _apply_record, _record_data, _repeatable,
)


IMPORT_EXTENSIONS = {'.docx', '.doc'}
MAX_ARCHIVE_DOCUMENTS = 500
MAX_PROCESS_BATCH = 10
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 250 * 1024 * 1024

STATUS_LABELS = {
    'queued': 'En attente',
    'processing': 'Traitement en cours',
    'completed': 'Traitement terminé',
    'pending': 'À extraire',
    'ready': 'Prêt à valider',
    'incomplete': 'Extraction incomplète',
    'error': 'Erreur',
    'duplicate': 'Doublon détecté',
    'validated': 'Validé',
    'rejected': 'Rejeté',
}


def _owned_batch(batch_id):
    return KineCaseImportBatch.query.filter_by(
        id=batch_id, created_by=teacher_id()
    ).first_or_404()


def _owned_draft(draft_id):
    return KineCaseDraft.query.filter_by(
        id=draft_id, created_by=teacher_id()
    ).first_or_404()


def _storage_root():
    base = (
        current_app.config.get('KINE_IMPORT_FOLDER')
        or current_app.config.get('UPLOAD_FOLDER')
        or tempfile.gettempdir()
    )
    path = os.path.abspath(os.path.join(base, 'kine_case_imports'))
    os.makedirs(path, exist_ok=True)
    return path


def _safe_stored_path(batch_id, filename):
    directory = os.path.join(_storage_root(), str(batch_id))
    os.makedirs(directory, exist_ok=True)
    safe_name = secure_filename(filename) or 'cas.docx'
    return os.path.join(directory, f'{uuid.uuid4().hex}_{safe_name}')


def _write_source(batch_id, filename, content):
    path = _safe_stored_path(batch_id, filename)
    with open(path, 'wb') as output:
        output.write(content)
    return path, hashlib.sha256(content).hexdigest()


def _filename_duplicate(filename, digest, current_id=None):
    query = KineCaseDraft.query.filter(
        KineCaseDraft.status != 'rejected',
        db.or_(
            func.lower(KineCaseDraft.source_filename) == filename.lower(),
            KineCaseDraft.source_sha256 == digest,
        ),
    )
    if current_id:
        query = query.filter(KineCaseDraft.id != current_id)
    found = query.first()
    if not found:
        return None
    if found.source_sha256 == digest:
        return f'Document source identique au brouillon #{found.id}.'
    return f'Nom de fichier déjà importé dans le brouillon #{found.id}.'


def _case_duplicate(data, current_draft_id=None):
    number = str(data.get('case_number') or '').strip()
    title = str(data.get('title') or '').strip()
    clauses = []
    if number:
        clauses.append(func.lower(PatientCase.case_number) == number.lower())
    if title:
        clauses.append(func.lower(PatientCase.title) == title.lower())
    if clauses:
        existing_case = PatientCase.query.filter(
            PatientCase.specialty == 'kine', db.or_(*clauses)
        ).first()
        if existing_case:
            return f'Correspond au cas existant {existing_case.case_number}.'

    draft_query = KineCaseDraft.query.filter(
        KineCaseDraft.id != current_draft_id,
        KineCaseDraft.status.notin_(['rejected', 'error']),
        KineCaseDraft.extracted_data.isnot(None),
    )
    for other in draft_query.all():
        other_data = other.extracted_data or {}
        same_number = number and str(
            other_data.get('case_number') or ''
        ).strip().lower() == number.lower()
        same_title = title and str(
            other_data.get('title') or ''
        ).strip().lower() == title.lower()
        if same_number or same_title:
            return f'Correspond au brouillon #{other.id}.'
    return None


def _suggest_folder(data):
    suggestion = str(data.get('suggested_pathology_folder') or '').strip()
    diagnosis = str(
        (data.get('medical_context') or {}).get('main_diagnosis')
        or data.get('diagnosis') or ''
    ).strip()
    needle = (suggestion or diagnosis).lower()
    if not needle:
        return None
    folders = PathologyFolder.query.filter_by(
        specialty='kine', is_archived=False
    ).all()
    for folder in folders:
        folder_name = folder.name.lower()
        if folder_name == needle or folder_name in needle or needle in folder_name:
            return folder.id
    return None


def _normalise_extraction(raw, draft):
    data = prune_empty(raw if isinstance(raw, dict) else {}) or {}
    source_stem = os.path.splitext(draft.source_filename)[0]
    data['case_number'] = str(data.get('case_number') or source_stem).strip()
    data['title'] = str(data.get('title') or '').strip()
    level = str(data.get('level') or 'both').lower()
    data['level'] = level if level in CASE_LEVELS else 'both'
    mode = str(data.get('mode_availability') or 'both').lower()
    data['mode_availability'] = mode if mode in MODES else 'both'
    data['emotional_state'] = data.get('emotional_state') or 'coopératif'
    data['folder_id'] = data.get('folder_id') or _suggest_folder(data)
    data['source_document'] = {
        'filename': draft.source_filename,
        'draft_id': draft.id,
    }
    return data


def _validation_issues(data):
    issues = []
    checks = (
        ('case_number', 'Numéro du cas absent.'),
        ('title', 'Titre du cas absent.'),
        ('diagnosis', 'Diagnostic principal absent.'),
        ('patient_info', 'Identité du patient absente.'),
        ('evaluation_checklist', "Critères nécessaires à l’évaluation absents."),
    )
    for key, message in checks:
        value = data.get(key)
        if key == 'diagnosis':
            value = value or (data.get('medical_context') or {}).get(
                'main_diagnosis'
            )
        if not value:
            issues.append(message)
    if not data.get('folder_id'):
        issues.append('Dossier pathologique à confirmer.')
    return issues


def _refresh_batch(batch):
    drafts = list(batch.drafts)
    batch.total_files = len(drafts)
    batch.processed_files = sum(
        item.status not in ('pending', 'processing') for item in drafts
    )
    batch.successful_files = sum(
        item.status in ('ready', 'validated') for item in drafts
    )
    batch.incomplete_files = sum(item.status == 'incomplete' for item in drafts)
    batch.error_files = sum(item.status == 'error' for item in drafts)
    batch.duplicate_files = sum(item.status == 'duplicate' for item in drafts)
    if any(item.status == 'processing' for item in drafts):
        batch.status = 'processing'
    elif any(item.status == 'pending' for item in drafts):
        batch.status = 'queued'
    else:
        batch.status = 'completed'
        batch.completed_at = batch.completed_at or datetime.utcnow()
    batch.updated_at = datetime.utcnow()


def _draft_payload(draft):
    return {
        'id': draft.id,
        'batch_id': draft.batch_id,
        'source_filename': draft.source_filename,
        'status': draft.status,
        'status_label': STATUS_LABELS.get(draft.status, draft.status),
        'extracted_data': draft.extracted_data,
        'validation_issues': draft.validation_issues or [],
        'duplicate_reason': draft.duplicate_reason,
        'error_message': draft.error_message,
        'extraction_method': draft.extraction_method,
        'extracted_at': (
            draft.extracted_at.isoformat() + 'Z' if draft.extracted_at else None
        ),
        'validated_case_id': draft.validated_case_id,
        'detail_url': url_for('kine.case_import_draft', draft_id=draft.id),
        'source_url': url_for(
            'kine.case_import_draft_source', draft_id=draft.id
        ),
    }


def _batch_payload(batch, include_drafts=True):
    total = batch.total_files or 0
    result = {
        'id': batch.id,
        'status': batch.status,
        'status_label': STATUS_LABELS.get(batch.status, batch.status),
        'total_files': total,
        'processed_files': batch.processed_files,
        'successful_files': batch.successful_files,
        'incomplete_files': batch.incomplete_files,
        'error_files': batch.error_files,
        'duplicate_files': batch.duplicate_files,
        'progress_percentage': round(
            batch.processed_files / total * 100
        ) if total else 0,
        'process_url': url_for(
            'kine.process_case_import_batch', batch_id=batch.id
        ),
        'retry_url': url_for(
            'kine.retry_case_import_batch', batch_id=batch.id
        ),
        'detail_url': url_for('kine.case_import_batch', batch_id=batch.id),
    }
    if include_drafts:
        result['drafts'] = [_draft_payload(item) for item in batch.drafts]
    return result


def _agent_for_file():
    configured = current_app.config.get('DOCUMENT_AGENT')
    if not configured:
        raise RuntimeError(
            "L’extraction automatique des documents n’est pas configurée."
        )
    if isinstance(configured, DocumentExtractionAgent):
        return DocumentExtractionAgent(llm_client=configured.llm_client)
    return configured


def _process_one_draft(draft_id):
    claimed = KineCaseDraft.query.filter_by(
        id=draft_id, status='pending'
    ).update({
        KineCaseDraft.status: 'processing',
        KineCaseDraft.error_message: None,
    }, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    draft = db.session.get(KineCaseDraft, draft_id)
    try:
        extension = os.path.splitext(draft.source_filename)[1].lower()
        extracted = _agent_for_file().process_file(
            draft.source_path, extension,
            os.path.splitext(draft.source_filename)[0], 'kine',
        )
        draft = db.session.get(KineCaseDraft, draft_id)
        data = _normalise_extraction(extracted, draft)
        draft.extracted_data = data
        draft.extraction_method = str(
            data.get('extraction_method') or 'llm_schema_kine'
        )
        draft.extracted_at = datetime.utcnow()
        draft.validation_issues = _validation_issues(data)
        duplicate = _case_duplicate(data, draft.id)
        draft.duplicate_reason = duplicate
        draft.status = (
            'duplicate' if duplicate
            else ('incomplete' if draft.validation_issues else 'ready')
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        draft = db.session.get(KineCaseDraft, draft_id)
        draft.status = 'error'
        draft.error_message = str(exc)
        draft.extracted_at = datetime.utcnow()
        draft.extraction_method = 'llm_schema_kine'
        db.session.commit()
    return True


def _draft_data_from_form(draft):
    original = dict(draft.extracted_data or {})
    record = _record_data(request.form)
    tests = canonicalize_medical_tests(record.get('tests') or {})
    assessment = tests.pop('physiotherapy_assessment', {})
    vitals = tests.pop('vital_parameters', [])
    original.update({
        'case_number': str(request.form.get('case_number') or '').strip(),
        'title': str(request.form.get('title') or '').strip(),
        'folder_id': int(request.form['folder_id']) if request.form.get('folder_id') else None,
        'level': request.form.get('level') or 'both',
        'mode_availability': request.form.get('mode_availability') or 'both',
        'emotional_state': request.form.get('emotional_state') or 'coopératif',
        'pedagogical_objectives': request.form.get('pedagogical_objectives'),
        'diagnosis': request.form.get('diagnosis'),
        'directives': request.form.get('directives'),
        'patient_info': record.get('identity') or {},
        'medical_context': record.get('medical_context') or {},
        'history': record.get('medical_history') or {},
        'comorbidities': record.get('comorbidities') or [],
        'tests': tests,
        'reference_vitals': record.get('reference_vitals') or {},
        'prescriptions': {
            'medical': record.get('medical_prescription'),
            'physiotherapy': record.get('physiotherapy_prescription'),
        },
        'available_documents': record.get('available_documents') or [],
        'physiotherapy_assessment': assessment,
        'vital_parameters': vitals,
        'procedures': _repeatable(request.form, 'procedures'),
        'medications': _repeatable(request.form, 'medications'),
        'incidents': _repeatable(request.form, 'incidents'),
        'evaluation_checklist': _repeatable(
            request.form, 'evaluation_checklist'
        ),
    })
    return prune_empty(original) or {}


def _create_case_from_draft(draft):
    data = draft.extracted_data or {}
    if _case_duplicate(data, draft.id):
        raise ValueError(
            'Un cas ou un autre brouillon possède déjà ce numéro ou ce titre.'
        )
    tests = dict(data.get('tests') or {})
    tests['physiotherapy_assessment'] = (
        data.get('physiotherapy_assessment') or {}
    )
    tests['vital_parameters'] = data.get('vital_parameters') or []
    prescriptions = data.get('prescriptions') or {}
    case_data = {
        'case_number': data.get('case_number'),
        'title': data.get('title'),
        'folder_id': data.get('folder_id'),
        'level': data.get('level'),
        'mode_availability': data.get('mode_availability'),
        'pedagogical_objectives': data.get('pedagogical_objectives'),
        'emotional_state': data.get('emotional_state'),
        'diagnosis': data.get('diagnosis') or (
            data.get('medical_context') or {}
        ).get('main_diagnosis'),
        'directives': data.get('directives'),
        'patient_record': {
            'identity': data.get('patient_info') or {},
            'medical_context': data.get('medical_context') or {},
            'medical_history': data.get('history') or {},
            'comorbidities': data.get('comorbidities') or [],
            'tests': tests,
            'reference_vitals': data.get('reference_vitals') or {},
            'medical_prescription': prescriptions.get('medical'),
            'physiotherapy_prescription': prescriptions.get('physiotherapy'),
            'available_documents': data.get('available_documents') or [],
        },
        'procedures': data.get('procedures') or [],
        'medications': data.get('medications') or [],
        'incidents': data.get('incidents') or [],
    }
    case = PatientCase()
    _apply_case(case, case_data)
    db.session.add(case)
    _apply_record(case, case_data)
    case.evaluation_checklist = data.get('evaluation_checklist') or []
    case.symptoms = data.get('symptoms') or []
    case.custom_sections = data.get('custom_sections') or []
    db.session.flush()
    for item in data.get('incidents') or []:
        case.incidents.append(Incident(
            trigger_description=item.get('trigger_description'),
            trigger_condition=item.get('trigger_condition') or '',
            scripted_reaction=item.get('scripted_reaction') or '',
            severity=(
                item.get('severity')
                if item.get('severity') in ('minor', 'major') else 'minor'
            ),
        ))
    return case


@kine_bp.route('/case-imports', methods=['GET', 'POST'])
@teacher_required
def case_imports():
    if request.method == 'GET':
        batches = KineCaseImportBatch.query.filter_by(
            created_by=teacher_id()
        ).order_by(KineCaseImportBatch.created_at.desc()).all()
        if wants_json():
            return jsonify({
                'batches': [
                    _batch_payload(item, include_drafts=False)
                    for item in batches
                ]
            })
        return render_template('case_imports_kine.html', batches=batches)

    uploads = [
        item for item in request.files.getlist('documents')
        if item and item.filename
    ]
    if not uploads:
        single = request.files.get('source_document')
        uploads = [single] if single and single.filename else []
    if not uploads:
        return error('Sélectionnez au moins un document Word ou une archive ZIP.')

    batch = KineCaseImportBatch(created_by=teacher_id(), status='queued')
    db.session.add(batch)
    db.session.flush()
    candidates = []
    try:
        for upload in uploads:
            filename = os.path.basename(upload.filename)
            extension = os.path.splitext(filename)[1].lower()
            content = upload.read()
            if len(content) > MAX_DOCUMENT_BYTES and extension != '.zip':
                raise ValueError(
                    f'Le document « {filename} » dépasse la limite de 25 Mo.'
                )
            if extension == '.zip':
                archive_path, _ = _write_source(batch.id, filename, content)
                del archive_path  # Archive conservée avec les sources du lot.
                with zipfile.ZipFile(BytesIO(content)) as archive:
                    entries = [
                        entry for entry in archive.infolist()
                        if not entry.is_dir()
                        and os.path.splitext(entry.filename)[1].lower() == '.docx'
                    ]
                    if len(entries) > MAX_ARCHIVE_DOCUMENTS:
                        raise ValueError(
                            f'Une archive ne peut pas contenir plus de '
                            f'{MAX_ARCHIVE_DOCUMENTS} documents.'
                        )
                    if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                        raise ValueError(
                            "Le contenu décompressé de l’archive dépasse 250 Mo."
                        )
                    for entry in entries:
                        if entry.file_size > MAX_DOCUMENT_BYTES:
                            raise ValueError(
                                f'Le document « {os.path.basename(entry.filename)} » '
                                'dépasse la limite de 25 Mo.'
                            )
                        candidates.append((
                            os.path.basename(entry.filename),
                            archive.read(entry),
                        ))
            elif extension in IMPORT_EXTENSIONS:
                candidates.append((filename, content))
            else:
                raise ValueError(
                    f'Format non pris en charge pour « {filename} ». '
                    'Utilisez DOCX, DOC ou ZIP.'
                )
        if not candidates:
            raise ValueError("Aucun document DOCX n’a été trouvé.")
        if len(candidates) > MAX_ARCHIVE_DOCUMENTS:
            raise ValueError(
                f'Un lot ne peut pas dépasser {MAX_ARCHIVE_DOCUMENTS} documents.'
            )
        for filename, content in candidates:
            path, digest = _write_source(batch.id, filename, content)
            duplicate = _filename_duplicate(filename, digest)
            db.session.add(KineCaseDraft(
                batch=batch, created_by=teacher_id(),
                source_filename=filename, source_path=path,
                source_sha256=digest,
                status='duplicate' if duplicate else 'pending',
                duplicate_reason=duplicate,
                validation_issues=[duplicate] if duplicate else [],
            ))
        db.session.flush()
        _refresh_batch(batch)
        db.session.commit()
    except (ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        db.session.rollback()
        return error(str(exc))

    result = _batch_payload(batch)
    if wants_json():
        return jsonify(result), 201
    return redirect(url_for('kine.case_import_batch', batch_id=batch.id))


@kine_bp.route('/case-imports/<int:batch_id>')
@teacher_required
def case_import_batch(batch_id):
    batch = _owned_batch(batch_id)
    if wants_json():
        return jsonify(_batch_payload(batch))
    return render_template(
        'case_import_batch_kine.html', batch=batch,
        batch_data=_batch_payload(batch),
    )


@kine_bp.route('/case-imports/<int:batch_id>/process', methods=['POST'])
@teacher_required
def process_case_import_batch(batch_id):
    batch = _owned_batch(batch_id)
    requested = (request.get_json(silent=True) or request.form).get('limit', 3)
    try:
        limit = max(1, min(int(requested), MAX_PROCESS_BATCH))
    except (TypeError, ValueError):
        return error('Taille du lot de traitement invalide.')
    pending_ids = [
        item.id for item in KineCaseDraft.query.filter_by(
            batch_id=batch.id, status='pending'
        ).order_by(KineCaseDraft.id).limit(limit).all()
    ]
    for draft_id in pending_ids:
        _process_one_draft(draft_id)
    batch = db.session.get(KineCaseImportBatch, batch.id)
    _refresh_batch(batch)
    db.session.commit()
    return jsonify(_batch_payload(batch))


@kine_bp.route('/case-imports/<int:batch_id>/retry', methods=['POST'])
@teacher_required
def retry_case_import_batch(batch_id):
    batch = _owned_batch(batch_id)
    failures = KineCaseDraft.query.filter_by(
        batch_id=batch.id, status='error'
    ).all()
    for draft in failures:
        draft.status = 'pending'
        draft.error_message = None
    batch.completed_at = None
    _refresh_batch(batch)
    db.session.commit()
    return jsonify(_batch_payload(batch))


@kine_bp.route('/case-import-drafts/<int:draft_id>', methods=['GET', 'POST', 'PATCH'])
@teacher_required
def case_import_draft(draft_id):
    draft = _owned_draft(draft_id)
    if request.method == 'GET':
        if wants_json():
            return jsonify(_draft_payload(draft))
        return render_template(
            'case_form_kine.html', clinical_case=None, draft=draft,
            folders=PathologyFolder.query.filter_by(
                specialty='kine', is_archived=False
            ).all(),
            form_action=url_for('kine.case_import_draft', draft_id=draft.id),
            initial_case_data=draft.extracted_data or {},
            source_url=url_for(
                'kine.case_import_draft_source', draft_id=draft.id
            ),
            cancel_url=url_for(
                'kine.case_import_batch', batch_id=draft.batch_id
            ),
        )

    if request.is_json:
        data = payload().get('extracted_data')
        if not isinstance(data, dict):
            return error('Les données corrigées du brouillon sont invalides.')
        draft.extracted_data = _normalise_extraction(data, draft)
        action = payload().get('action') or 'save'
    else:
        draft.extracted_data = _normalise_extraction(
            _draft_data_from_form(draft), draft
        )
        action = request.form.get('draft_action') or 'save'

    draft.validation_issues = _validation_issues(draft.extracted_data)
    duplicate = _case_duplicate(draft.extracted_data, draft.id)
    draft.duplicate_reason = duplicate
    draft.status = (
        'duplicate' if duplicate
        else ('incomplete' if draft.validation_issues else 'ready')
    )
    draft.reviewed_at = datetime.utcnow()
    if action == 'validate':
        if draft.validation_issues:
            db.session.commit()
            if wants_json():
                return error(
                    'Corrigez les éléments incomplets avant validation.', 409
                )
            return redirect(url_for('kine.case_import_draft', draft_id=draft.id))
        try:
            case = _create_case_from_draft(draft)
            draft.status = 'validated'
            draft.validated_case = case
            _refresh_batch(draft.batch)
            db.session.commit()
        except (TypeError, ValueError) as exc:
            db.session.rollback()
            return error(str(exc), 409)
        if wants_json():
            return jsonify({
                **_draft_payload(draft), 'case_id': case.id,
                'case_url': url_for('kine.case_item', case_id=case.id),
            })
        return redirect(url_for('kine.case_item', case_id=case.id))

    _refresh_batch(draft.batch)
    db.session.commit()
    if wants_json():
        return jsonify(_draft_payload(draft))
    return redirect(url_for('kine.case_import_draft', draft_id=draft.id))


@kine_bp.route('/case-import-drafts/<int:draft_id>/reject', methods=['POST'])
@teacher_required
def reject_case_import_draft(draft_id):
    draft = _owned_draft(draft_id)
    if draft.status == 'validated':
        return error('Un brouillon déjà validé ne peut pas être rejeté.', 409)
    draft.status = 'rejected'
    draft.reviewed_at = datetime.utcnow()
    _refresh_batch(draft.batch)
    db.session.commit()
    if wants_json():
        return jsonify(_draft_payload(draft))
    return redirect(url_for('kine.case_import_batch', batch_id=draft.batch_id))


@kine_bp.route('/case-import-drafts/<int:draft_id>/source')
@teacher_required
def case_import_draft_source(draft_id):
    draft = _owned_draft(draft_id)
    if not os.path.isfile(draft.source_path):
        return error('Document source introuvable.', 404)
    return send_file(
        draft.source_path, as_attachment=True,
        download_name=draft.source_filename,
    )
