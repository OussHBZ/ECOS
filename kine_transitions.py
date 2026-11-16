"""Atomic state claims. No deletion or inferred reconnection deadline (D01)."""
from datetime import datetime
from models import db, SimulationSession


class TransitionConflict(ValueError):
    pass


def claim(simulation, states, target, refresh=True, expected=None):
    """Reject stale writers before they can overwrite a completed attempt or its log."""
    now = datetime.utcnow()
    with db.session.no_autoflush:
        changed = SimulationSession.query.filter(
            SimulationSession.id == simulation.id,
            SimulationSession.status.in_(states),
            SimulationSession.updated_at == (expected if expected is not None else simulation.updated_at),
        ).update({'status': target, 'updated_at': now}, synchronize_session=False)
    if refresh or not changed:
        db.session.refresh(simulation)
    else:
        from sqlalchemy.orm.attributes import set_committed_value
        set_committed_value(simulation, 'status', target)
        set_committed_value(simulation, 'updated_at', now)
    if not changed:
        raise TransitionConflict('La tentative a changé ; rechargez son état avant de continuer.')
