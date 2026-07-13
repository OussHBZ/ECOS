import json
import re
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import jsonify, redirect, request, session, url_for
from flask_login import current_user


LEVELS = {'licence', 'master'}
CASE_LEVELS = LEVELS | {'both'}
MODES = {'training', 'exam', 'both'}


def prune_empty(value):
    """Recursively remove display-only empty values while preserving 0/False."""
    if isinstance(value, dict):
        cleaned = {}
        for key, nested in value.items():
            nested = prune_empty(nested)
            if nested is not None:
                cleaned[key] = nested
        return cleaned or None
    if isinstance(value, (list, tuple)):
        cleaned = [item for item in (prune_empty(item) for item in value) if item is not None]
        return cleaned or None
    if isinstance(value, str):
        text = value.strip()
        return None if text.lower() in ('', '-', '—', 'null', 'none', 'n/a') else text
    return None if value is None else value


def _deduplication_key(value):
    if isinstance(value, str):
        return ' '.join(value.lower().split())
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).lower()
    except (TypeError, ValueError):
        return repr(value).lower()


def deduplicate_nested(value):
    """Remove repeated structured extraction values while preserving order."""
    if isinstance(value, dict):
        return {key: deduplicate_nested(nested) for key, nested in value.items()}
    if isinstance(value, list):
        result, seen = [], set()
        for item in value:
            cleaned = deduplicate_nested(item)
            key = _deduplication_key(cleaned)
            if key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result
    return value


def canonicalize_medical_tests(value):
    """Return one canonical copy of each medical result.

    Older case forms stored the same extracted result both under its category
    and in a legacy ``items`` list. Categorized values take precedence; legacy
    items are distributed only when no categorized data exists.
    """
    tests = deduplicate_nested(dict(value or {}))
    categories = ('cardiac', 'vascular', 'biological', 'imaging', 'other')
    has_categories = any(tests.get(category) for category in categories)
    result = {key: nested for key, nested in tests.items() if key != 'items'}
    if not has_categories:
        for item in tests.get('items') or []:
            if isinstance(item, dict):
                category = item.get('category') if item.get('category') in categories else 'other'
                cleaned = {key: nested for key, nested in item.items() if key != 'category'}
            else:
                category, cleaned = 'other', item
            result.setdefault(category, []).append(cleaned)
    # Form repeaters turn a plain extracted sentence into
    # {name: sentence, value: '', unit: ''}. Collapse that empty wrapper so it
    # compares equal to the original string instead of rendering a bold copy.
    for category in categories:
        normalized_items = []
        for item in result.get(category) or []:
            if isinstance(item, dict):
                cleaned = {key: nested for key, nested in item.items() if key != 'category'}
                meaningful_extra = any(
                    nested not in (None, '') for key, nested in cleaned.items()
                    if key not in ('name', 'value', 'unit')
                )
                if cleaned.get('name') and cleaned.get('value') in (None, '') and cleaned.get('unit') in (None, '') and not meaningful_extra:
                    item = cleaned['name']
                else:
                    item = cleaned
            normalized_items.append(item)
        if normalized_items:
            result[category] = normalized_items
        else:
            result.pop(category, None)
    return deduplicate_nested(result)


def wants_json():
    return request.is_json or request.accept_mimetypes.best == 'application/json'


def payload():
    return request.get_json(silent=True) or request.form


def error(message, status=400):
    return jsonify({'error': message}), status


def teacher_id():
    return session.get('teacher_id')


def parse_datetime(value, field_name='datetime', local_utc_offset_minutes=None):
    """Normalize an ISO value or browser-local wall time to naive UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            raise ValueError(f'Invalid {field_name}; expected ISO-8601 datetime')
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        offset = int(local_utc_offset_minutes) if local_utc_offset_minutes not in (None, '') else 0
    except (TypeError, ValueError):
        raise ValueError('Invalid browser timezone offset')
    if not -840 <= offset <= 840:
        raise ValueError('Invalid browser timezone offset')
    return parsed + timedelta(minutes=offset)


def parse_indexed_form(prefix):
    """Parse ``prefix[0][field]`` HTML controls into a list of dictionaries."""
    rows = {}
    pattern = re.compile(rf'^{re.escape(prefix)}\[(\d+)\]\[([^]]+)\]$')
    for key in request.form:
        match = pattern.match(key)
        if match:
            index, field = match.groups()
            rows.setdefault(int(index), {})[field] = request.form.get(key)
    return [rows[index] for index in sorted(rows) if any(str(v or '').strip() for v in rows[index].values())]


def model_dict(model, fields):
    return {field: getattr(model, field, None) for field in fields}


def kine_staff_required(function):
    """Allow authenticated administrators or teachers to manage kine data."""
    @wraps(function)
    def decorated(*args, **kwargs):
        user_type = session.get('user_type')
        authorized = (
            user_type == 'admin' and session.get('admin_authenticated')
        ) or (
            user_type == 'teacher' and session.get('teacher_authenticated')
            and current_user.is_authenticated
            and str(getattr(current_user, 'ecos_type', 'standard') or 'standard').lower() == 'kine'
        )
        if not authorized:
            if wants_json():
                return error('Staff authentication required', 401)
            return redirect(url_for('auth.login'))
        return function(*args, **kwargs)
    return decorated
