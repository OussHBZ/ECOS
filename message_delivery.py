"""Durable delivery keys; reservations are technical, never an exam grace period."""
from datetime import datetime, timedelta
from uuid import uuid4

from models import db
from kine_transitions import claim, TransitionConflict

# Recover a crashed worker without duplicating its saved human message. The
# original revision fences out any old worker that returns after recovery.
RESERVATION_SECONDS = 300


def prepare(simulation, message, key):
    if key is None:
        key = str(uuid4())  # Backwards-compatible clients do not promise retries.
    if not isinstance(key, str) or not 1 <= len(key) <= 128:
        raise ValueError('Identifiant de requête invalide.')
    rows = simulation.conversation or []
    human = next((r for r in rows if r.get('request_id') == key and r.get('role') == 'human'), None)
    if human and human.get('delivery_identity', human['content']) != message:
        raise ValueError('Cet identifiant appartient à un autre message.')
    if human and 'delivery_response' in human:
        return key, human, human['delivery_response']
    reply = next((r for r in rows if r.get('request_id') == key and r.get('role') == 'assistant'), None)
    if reply:
        return key, human, reply.get('delivery_response') or {'type': reply['type'], 'content': reply['content']}
    pending = (simulation.runtime_state or {}).get('message_delivery') or {}
    if pending.get('state') == 'pending' and datetime.fromisoformat(pending['started_at']) + timedelta(seconds=RESERVATION_SECONDS) > datetime.utcnow():
        raise TransitionConflict('Une réponse est en cours. Réessayez le même envoi dans quelques instants.')
    return key, human, None


def reserve(simulation, key):
    state = dict(simulation.runtime_state or {})
    state['message_delivery'] = {'request_id': key, 'state': 'pending', 'started_at': datetime.utcnow().isoformat()}
    simulation.runtime_state = state


def failed(simulation, key, revision):
    db.session.rollback()
    # Do not overwrite a close, teacher action, or newer worker's reservation.
    try:
        claim(simulation, ('in_progress',), 'in_progress', expected=revision)
        state = dict(simulation.runtime_state or {})
        state['message_delivery'] = {'request_id': key, 'state': 'retryable'}
        simulation.runtime_state = state
        db.session.commit()
    except TransitionConflict:
        db.session.rollback()
