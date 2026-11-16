"""Conservative source extraction and append-only ETP library."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from uuid import uuid4

from sqlalchemy import event
from models import db, KineETPVersion
from case_versions import canonical, digest

CATEGORIES = {
    'identification': 'Identification et ciblage',
    'knowledge': 'Socle de connaissances',
    'messages': 'Vulgarisation et messages clés',
    'daily_action': 'Plan d’action quotidien',
    'self_monitoring': 'Protocole d’autosurveillance',
    'rehabilitation': 'Réadaptation cardiovasculaire',
    'warning_signs': 'Arbre de décision des signes d’alerte',
    'patient_questions': 'Banque de questions et réponses du patient',
    'misconceptions': 'Gestion des idées reçues',
    'teach_back': 'Outils d’évaluation de la compréhension',
}


def categories(value):
    if not isinstance(value, dict) or set(value) - set(CATEGORIES):
        raise ValueError('Les dix catégories ETP sont requises ; catégorie inconnue.')
    result = {key: value.get(key, '') for key in CATEGORIES}
    if any(not isinstance(v, str) or len(v) > 100000 for v in result.values()):
        raise ValueError('Contenu de catégorie ETP invalide.')
    return result


def _text(value):
    value = unicodedata.normalize('NFKD', value)
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c)).lower()).strip()


def extract_source(content, filename):
    """Only explicit headings are classified. Unclassified text stays reviewable."""
    extension = Path(filename).suffix.lower()
    if extension == '.pdf':
        from PyPDF2 import PdfReader
        reader = PdfReader(BytesIO(content))
        if len(reader.pages) > 100:
            raise ValueError('Document ETP limité à 100 pages.')
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    elif extension in ('.docx', '.doc'):
        from docx import Document
        # Word OpenXML is accepted even when mislabeled .doc. Binary DOC needs conversion.
        try:
            doc = Document(BytesIO(content))
        except Exception as exc:
            raise ValueError('Convertissez ce document Word binaire en DOCX avant import.') from exc
        text = '\n'.join([p.text for p in doc.paragraphs] + [
            ' | '.join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows
        ])
    else:
        raise ValueError('Import ETP : Word (.docx) ou PDF requis.')
    result, unclassified, selected = categories({}), [], None
    headings = {_text(label): key for key, label in CATEGORIES.items()}
    headings.update({_text(key): key for key in CATEGORIES})
    for line in text.splitlines():
        candidate = _text(re.sub(r'^\s*\d+[.)\s-]*', '', line))
        if candidate in headings:
            selected = headings[candidate]
        elif line.strip():
            if selected:
                result[selected] += line + '\n'
            else:
                unclassified.append(line)
    return {'categories': result, 'unclassified': '\n'.join(unclassified),
            'extraction_review_required': True, 'raw_text': text,
            'missing_categories': [k for k, v in result.items() if not v.strip()]}


def new_revision(data, actor, previous=None, source=None):
    body = deepcopy(json.loads(previous.content_json) if previous else {})
    body.update({k: deepcopy(data[k]) for k in (
        'references', 'unclassified', 'patient_prompts',
    ) if k in data})
    if 'categories' in data:
        if not isinstance(data['categories'], dict):
            raise ValueError('Catégories ETP invalides.')
        body['categories'] = {**body.get('categories', {}), **data['categories']}
    body['categories'] = categories(body.get('categories', {}))
    if source:
        raw, filename = source
        if len(raw) > 25 * 1024 * 1024:
            raise ValueError('Source ETP limitée à 25 Mo.')
        try:
            body.update(extract_source(raw, filename))
        except Exception as exc:
            raise ValueError(f'Extraction ETP impossible : {exc}') from exc
    prompts = body.get('patient_prompts', [])
    from rehabilitation import rows
    for prompt in rows(prompts, 'Questions ETP du patient'):
        if (prompt.get('category') not in CATEGORIES or not isinstance(prompt.get('trigger'), str)
                or not prompt['trigger'].strip() or not isinstance(prompt.get('text'), str) or not prompt['text'].strip()):
            raise ValueError('Question ETP : catégorie, déclencheur et texte requis.')
    validated = data.get('validate') is True and source is None
    if validated and body.get('extraction_review_required') and data.get('confirm_review') is not True:
        raise ValueError('Contrôlez le document, les catégories absentes et le contenu non classé.')
    if validated:
        body['extraction_review_required'] = False
    title = str(data.get('title', previous.title if previous else '')).strip()
    level = data.get('level', previous.level if previous else 'both')
    if not title or level not in ('licence', 'master', 'both'):
        raise ValueError('Titre et niveau ETP requis.')
    sheet_id = previous.sheet_id if previous else str(uuid4())
    number = (db.session.query(db.func.max(KineETPVersion.number)).filter_by(sheet_id=sheet_id).scalar() or 0) + 1
    raw, filename = source if source else ((previous.source_bytes, previous.source_filename) if previous else (None, None))
    item = KineETPVersion(
        sheet_id=sheet_id, number=number, title=title,
        pathology=str(data.get('pathology', previous.pathology if previous else '')),
        level=level, status='validated' if validated else 'review',
        content_json=canonical(body), content_sha256=digest(canonical(body)),
        source_bytes=raw, source_filename=filename,
        source_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
        created_by=str(actor),
    )
    db.session.add(item)
    db.session.flush()
    return item


def adaptation(reference, data, actor):
    if reference.status != 'validated' or digest(reference.content_json) != reference.content_sha256:
        raise ValueError('Une version de référence validée est requise.')
    body = json.loads(reference.content_json)
    supplied = data.get('categories', {})
    if not isinstance(supplied, dict):
        raise ValueError('Catégories ETP invalides.')
    body['categories'] = categories({**body['categories'], **supplied})
    if 'patient_prompts' in data:
        from rehabilitation import rows
        body['patient_prompts'] = deepcopy(rows(data['patient_prompts'], 'Questions ETP'))
    for p in body.get('patient_prompts', []):
        if p.get('category') not in CATEGORIES or not isinstance(p.get('trigger'), str) or not p['trigger'].strip() or not p.get('text'):
            raise ValueError('Question patient ETP invalide.')
    return {'id': str(data.get('id') or uuid4()), 'reference_id': reference.id,
            'sheet_id': reference.sheet_id, 'reference_number': reference.number,
            'reference_sha256': reference.content_sha256, 'title': reference.title,
            'status': 'validated' if data.get('validate') is True else 'review',
            'validated_by': str(actor) if data.get('validate') is True else None,
            'content': body}


@event.listens_for(KineETPVersion, 'before_update')
@event.listens_for(KineETPVersion, 'before_delete')
def immutable_etp(mapper, connection, target):
    raise ValueError('Une révision ETP est immuable ; créez une nouvelle version.')


@event.listens_for(KineETPVersion.__table__, 'after_create')
def etp_triggers(target, connection, **kwargs):
    if connection.dialect.name == 'sqlite':
        for operation in ('UPDATE', 'DELETE'):
            connection.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS kine_etp_no_{operation.lower()} BEFORE {operation} "
                "ON kine_etp_versions BEGIN SELECT RAISE(ABORT, 'Immutable ETP revision'); END"
            )
