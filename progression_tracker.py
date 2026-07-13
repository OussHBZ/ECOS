"""Progression state machine for physiotherapy simulations.

The tracker contains no Flask or database dependency. It can update a
``SimulationSession`` model instance or a dictionary and leaves transaction
management to the calling route/service.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class Phase:
    number: int
    key: str
    label: str


PHASES: Tuple[Phase, ...] = (
    Phase(1, 'welcome', 'Accueil et présentation'),
    Phase(2, 'history_taking', 'Anamnèse'),
    Phase(3, 'history_risk_analysis', 'Analyse des antécédents et facteurs de risque'),
    Phase(4, 'physiotherapy_assessment', 'Bilan kinésithérapique'),
    Phase(5, 'clinical_reasoning', 'Analyse et raisonnement clinique'),
    Phase(6, 'therapeutic_objectives', 'Objectifs thérapeutiques'),
    Phase(7, 'rehabilitation_program', 'Programme de rééducation'),
    Phase(8, 'incident_management', 'Gestion des incidents cliniques'),
    Phase(9, 'therapeutic_education', 'Éducation thérapeutique'),
    Phase(10, 'end_of_care', 'Fin de la prise en charge'),
    Phase(11, 'evaluation_feedback', 'Évaluation et feedback'),
)

PHASE_BY_NUMBER = {phase.number: phase for phase in PHASES}
PHASE_BY_KEY = {phase.key: phase for phase in PHASES}
PHASE_KEY_ALIASES = {
    'clinical_analysis': 'history_risk_analysis',
    'reasoning': 'clinical_reasoning',
    'objectives': 'therapeutic_objectives',
}
VALID_MODES = {'training', 'exam'}


class ProgressionError(ValueError):
    """Base error for invalid tracker state or transitions."""


class InvalidPhaseError(ProgressionError):
    pass


class NavigationLockedError(ProgressionError):
    pass


def _read(state: Any, name: str, default=None):
    return state.get(name, default) if isinstance(state, dict) else getattr(state, name, default)


def _write(state: Any, name: str, value) -> None:
    if isinstance(state, dict):
        state[name] = value
    else:
        setattr(state, name, value)


def _normalize_phase(value: Any) -> Phase:
    if isinstance(value, Phase):
        return value
    if isinstance(value, str) and not value.strip().isdigit():
        key = value.strip().lower()
        phase = PHASE_BY_KEY.get(PHASE_KEY_ALIASES.get(key, key))
    else:
        try:
            phase = PHASE_BY_NUMBER.get(int(value))
        except (TypeError, ValueError):
            phase = None
    if phase is None:
        raise InvalidPhaseError('Phase must be a number from 1 to 11 or a valid phase key')
    return phase


class ProgressionTracker:
    """Control and serialize the eleven-phase kine consultation workflow."""

    def __init__(self, session_state: Any, now_factory=None):
        if session_state is None:
            raise ProgressionError('A simulation session state is required')
        self.session = session_state
        self._now = now_factory or (lambda: datetime.now(timezone.utc))
        self._validate_state()

    @property
    def mode(self) -> str:
        return str(_read(self.session, 'mode', 'training') or 'training').lower()

    @property
    def current(self) -> Phase:
        return _normalize_phase(_read(self.session, 'current_phase', 1))

    @property
    def progress_percentage(self) -> int:
        """Percentage of the eleven-step workflow reached."""
        return round(self.current.number / len(PHASES) * 100)

    def _validate_state(self) -> None:
        if self.mode not in VALID_MODES:
            raise ProgressionError("Simulation mode must be 'training' or 'exam'")
        _normalize_phase(_read(self.session, 'current_phase', 1))

    def can_navigate_to(self, target: Any) -> bool:
        phase = _normalize_phase(target)
        if self.mode == 'training':
            return True
        # Exam navigation is idempotent or advances exactly one step. This
        # prevents both backward navigation and skipping mandatory phases.
        return phase.number in (self.current.number, self.current.number + 1)

    def navigate_to(self, target: Any, timestamp=None) -> Dict[str, Any]:
        phase = _normalize_phase(target)
        previous = self.current
        if not self.can_navigate_to(phase):
            if phase.number < previous.number:
                reason = 'Completed exam phases are locked'
            else:
                reason = 'Exam phases must be completed sequentially'
            raise NavigationLockedError(reason)

        if phase.number != previous.number:
            changed_at = timestamp or self._now()
            if not isinstance(changed_at, datetime):
                raise ProgressionError('Transition timestamp must be a datetime')
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            self._record_phase_timing(previous, changed_at)
            _write(self.session, 'current_phase', phase.number)
            self._append_timeline(previous, phase, changed_at)
        return self.to_frontend()

    def next_phase(self, timestamp=None) -> Dict[str, Any]:
        if self.current.number == len(PHASES):
            return self.to_frontend()
        return self.navigate_to(self.current.number + 1, timestamp=timestamp)

    def previous_phase(self, timestamp=None) -> Dict[str, Any]:
        if self.mode == 'exam':
            raise NavigationLockedError('Backward navigation is disabled in exam mode')
        if self.current.number == 1:
            return self.to_frontend()
        return self.navigate_to(self.current.number - 1, timestamp=timestamp)

    def _record_phase_timing(self, phase: Phase, changed_at: datetime) -> None:
        timings = dict(_read(self.session, 'phase_timings', {}) or {})
        entry = dict(timings.get(phase.key, {}) or {})
        entry.setdefault('entered_at', self._iso(_read(self.session, 'started_at', changed_at)))
        entry['left_at'] = self._iso(changed_at)
        entered = self._parse_datetime(entry.get('entered_at'))
        if entered is not None:
            entry['duration_seconds'] = max(0, round((changed_at - entered).total_seconds()))
        timings[phase.key] = entry
        _write(self.session, 'phase_timings', timings)

    def _append_timeline(self, previous: Phase, phase: Phase, changed_at: datetime) -> None:
        timeline = list(_read(self.session, 'timeline', []) or [])
        timeline.append({
            'timestamp': self._iso(changed_at),
            'action': 'phase_change',
            'actor': 'student',
            'from_phase': previous.number,
            'to_phase': phase.number,
            'phase': phase.key,
            'details': {'from': previous.label, 'to': phase.label},
        })
        _write(self.session, 'timeline', timeline)

    @staticmethod
    def _iso(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return str(value)

    @staticmethod
    def _parse_datetime(value: Any):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
        else:
            return None
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)

    def to_frontend(self) -> Dict[str, Any]:
        current = self.current
        completed = [phase.number for phase in PHASES if phase.number < current.number]
        remaining = [phase.number for phase in PHASES if phase.number > current.number]
        phases = []
        for phase in PHASES:
            if phase.number < current.number:
                status = 'completed'
            elif phase.number == current.number:
                status = 'current'
            else:
                status = 'remaining'
            phases.append({
                'number': phase.number,
                'key': phase.key,
                'label': phase.label,
                'status': status,
                'can_navigate': self.can_navigate_to(phase),
                'locked': not self.can_navigate_to(phase),
            })
        return {
            'mode': self.mode,
            'current_phase': current.number,
            'current_phase_key': current.key,
            'current_phase_label': current.label,
            'progress_percentage': self.progress_percentage,
            'completed_phases': completed,
            'remaining_phases': remaining,
            'can_go_back': self.mode == 'training' and current.number > 1,
            'is_complete': current.number == len(PHASES),
            'phases': phases,
        }


def get_progression_state(session_state: Any) -> Dict[str, Any]:
    """Convenience API used by GET progress endpoints."""
    return ProgressionTracker(session_state).to_frontend()
