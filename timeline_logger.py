"""Consistent timeline event logging and frontend formatting."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ACTION_LABELS = {
    'simulation_started': 'Simulation commencée',
    'student_message': 'Message de l’étudiant',
    'test_requested': 'Test demandé',
    'incident_triggered': 'Incident déclenché',
    'phase_change': 'Changement de phase',
    'phase_navigation_denied': 'Navigation de phase refusée',
    'exam_auto_closed': 'Examen clôturé automatiquement',
    'simulation_completed': 'Simulation terminée',
    'simulation_paused': 'Simulation mise en pause',
    'simulation_resumed': 'Simulation reprise',
}


def append_timeline_event(session, action, *, actor='student', phase=None,
                          details=None, timestamp=None, **metadata):
    """Append an immutable-style event so SQLAlchemy JSON detects the change."""
    occurred_at = timestamp or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    event = {
        'timestamp': occurred_at.isoformat(),
        'action': str(action),
        'actor': actor,
    }
    if phase is not None:
        event['phase'] = phase
    if details is not None:
        event['details'] = details
    event.update({key: value for key, value in metadata.items() if value is not None})
    timeline = list(getattr(session, 'timeline', None) or [])
    timeline.append(event)
    session.timeline = timeline
    return event


def _parse_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def format_timeline(timeline, timezone_name='Africa/Casablanca'):
    """Return chronologically sorted, display-ready timeline dictionaries."""
    try:
        display_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        try:
            import pytz
        except ImportError:
            display_timezone = timezone.utc
            timezone_name = 'UTC'
        else:
            try:
                display_timezone = pytz.timezone(timezone_name)
            except pytz.UnknownTimeZoneError:
                display_timezone = timezone.utc
                timezone_name = 'UTC'
    formatted = []
    for position, original in enumerate(timeline or []):
        event = dict(original or {})
        parsed = _parse_timestamp(event.get('timestamp'))
        event['sequence'] = position + 1
        event['action_label'] = ACTION_LABELS.get(event.get('action'), str(event.get('action') or 'Action').replace('_', ' ').title())
        if str(event.get('phase')) in (
            '10', '11', 'end_of_care', 'evaluation_feedback',
        ):
            event['phase_label'] = 'Clôture technique historique'
        elif event.get('phase') is not None:
            event['phase_label'] = f"Phase {event['phase']}"
        event['timezone'] = timezone_name
        event['display_time'] = parsed.astimezone(display_timezone).strftime('%H:%M:%S') if parsed else '—'
        event['display_datetime'] = parsed.astimezone(display_timezone).strftime('%d/%m/%Y %H:%M:%S') if parsed else '—'
        event['_sort_timestamp'] = parsed.timestamp() if parsed else float('inf')
        formatted.append(event)
    formatted.sort(key=lambda event: (event['_sort_timestamp'], event['sequence']))
    for sequence, event in enumerate(formatted, start=1):
        event['sequence'] = sequence
        event.pop('_sort_timestamp', None)
    return formatted
