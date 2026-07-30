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
    guidance: str


PHASES: Tuple[Phase, ...] = (
    Phase(1, 'welcome', 'Accueil et présentation',
          'Accueillir le patient, se présenter et établir une relation thérapeutique.'),
    Phase(2, 'history_taking', 'Anamnèse',
          'Explorer le motif, l’histoire, les traitements, les symptômes, les habitudes, les limitations et les objectifs du patient.'),
    Phase(3, 'history_risk_analysis', 'Analyse des antécédents et facteurs de risque',
          'Analyser les antécédents, les comorbidités et les facteurs de risque sans demander le diagnostic au patient.'),
    Phase(4, 'physiotherapy_assessment', 'Bilan kinésithérapique',
          'Choisir et annoncer les tests pertinents : EVA, Borg, TUG, 6MWT, Sit To Stand, FC, SpO₂, PA, auscultation…'),
    Phase(5, 'clinical_reasoning', 'Analyse et raisonnement clinique',
          'Présenter votre analyse et votre raisonnement clinique sans attendre que le patient donne le diagnostic.'),
    Phase(6, 'therapeutic_objectives', 'Objectifs thérapeutiques',
          'Définir des objectifs thérapeutiques adaptés et formulés selon la méthode SMART.'),
    Phase(7, 'rehabilitation_program', 'Programme de rééducation',
          'Construire le programme FITT : exercices, intensité, fréquence, progression, surveillance et séance type.'),
    Phase(8, 'incident_management', 'Incidents cliniques',
          'Identifier et gérer uniquement les incidents prévus dans le dossier clinique.'),
    Phase(9, 'therapeutic_education', 'Éducation thérapeutique',
          'Informer, conseiller et vérifier la compréhension du patient.'),
)

# Read-only compatibility for SQLite sessions created before these technical
# steps were removed from the student tracker.
LEGACY_TECHNICAL_PHASES: Tuple[Phase, ...] = (
    Phase(10, 'end_of_care', 'Fin de la prise en charge',
          'Ancienne étape technique de clôture.'),
    Phase(11, 'evaluation_feedback', 'Évaluation et feedback',
          'Ancienne étape technique d’évaluation.'),
)
PHASE_BY_NUMBER = {
    phase.number: phase for phase in PHASES + LEGACY_TECHNICAL_PHASES
}
PHASE_BY_KEY = {
    phase.key: phase for phase in PHASES + LEGACY_TECHNICAL_PHASES
}
LICENCE_PHASES = tuple(
    phase for phase in PHASES if phase.key != 'incident_management'
)
PHASE_KEY_ALIASES = {
    'clinical_analysis': 'history_risk_analysis',
    'reasoning': 'clinical_reasoning',
    'objectives': 'therapeutic_objectives',
}
VALID_MODES = {'training', 'exam'}
PHASE_MINIMUM_ACTIONS = {
    'welcome': (
        ('student_message',),
        'Envoyer au moins un message d’accueil ou de présentation.',
    ),
    'history_taking': (
        ('student_message',),
        'Poser au moins une question d’anamnèse au patient.',
    ),
    'history_risk_analysis': (
        ('student_message',),
        'Explorer au moins un antécédent ou facteur de risque.',
    ),
    'physiotherapy_assessment': (
        ('test_requested',),
        'Annoncer et demander au moins un test ou une mesure.',
    ),
    'clinical_reasoning': (
        ('student_message',),
        'Formuler votre analyse ou votre raisonnement clinique.',
    ),
    'therapeutic_objectives': (
        ('student_message',),
        'Présenter au moins un objectif thérapeutique.',
    ),
    'rehabilitation_program': (
        ('student_message',),
        'Présenter au moins un élément du programme de rééducation.',
    ),
    'incident_management': (
        ('student_message', 'incident_triggered'),
        'Réaliser au moins une action de gestion de l’incident.',
    ),
    'therapeutic_education': (
        ('student_message',),
        'Réaliser au moins une action d’éducation thérapeutique.',
    ),
}


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
        raise InvalidPhaseError('La phase demandée est invalide.')
    return phase


class ProgressionTracker:
    """Control and serialize the level-specific Kine consultation workflow."""

    def __init__(self, session_state: Any, student=None, now_factory=None):
        if session_state is None:
            raise ProgressionError('Une session de simulation est obligatoire.')
        self.session = session_state
        recorded_student = student or _read(session_state, 'student')
        recorded_level = getattr(recorded_student, 'level', None)
        normalized_level = str(recorded_level or 'master').strip().lower()
        self.student_level = normalized_level if normalized_level in ('licence', 'master') else 'licence'
        self.phases = LICENCE_PHASES if self.student_level == 'licence' else PHASES
        self._now = now_factory or (lambda: datetime.now(timezone.utc))
        self._validate_state()

    @property
    def mode(self) -> str:
        return str(_read(self.session, 'mode', 'training') or 'training').lower()

    @property
    def simulation_completed(self) -> bool:
        return (
            str(_read(self.session, 'status', '') or '').lower() == 'completed'
            or bool(_read(self.session, 'evaluation_results'))
        )

    @property
    def current(self) -> Phase:
        phase = _normalize_phase(_read(self.session, 'current_phase', 1))
        # A legacy Licence session may have stopped on the former incident
        # phase. Present it at the next authorized phase without rewriting the
        # historical row.
        if phase not in self.phases:
            return PHASE_BY_KEY['therapeutic_education']
        return phase

    def _position(self, phase: Phase) -> int:
        return self.phases.index(phase) + 1

    def _target_phase(self, value: Any) -> Phase:
        if isinstance(value, Phase) or (isinstance(value, str) and not value.strip().isdigit()):
            phase = _normalize_phase(value)
            if phase not in self.phases:
                raise InvalidPhaseError("Cette phase n'est pas disponible pour ce niveau.")
            return phase
        try:
            return self.phases[int(value) - 1]
        except (TypeError, ValueError, IndexError):
            raise InvalidPhaseError(
                f'La phase doit être comprise entre 1 et {len(self.phases)}.'
            ) from None

    @property
    def progress_percentage(self) -> int:
        """Percentage of the furthest server-verified workflow phase reached."""
        return round(self.highest_reached_position / len(self.phases) * 100)

    def _validate_state(self) -> None:
        if self.mode not in VALID_MODES:
            raise ProgressionError("Le mode doit être « entraînement » ou « examen ».")
        _normalize_phase(_read(self.session, 'current_phase', 1))

    def can_navigate_to(self, target: Any) -> bool:
        phase = self._target_phase(target)
        target_position = self._position(phase)
        current_position = self._position(self.current)
        if target_position == current_position:
            return True
        if self.mode == 'exam':
            return (
                target_position == current_position + 1
                and self.current_requirements_met
            )
        if target_position <= self.highest_reached_position:
            return True
        return (
            current_position == self.highest_reached_position
            and target_position == current_position + 1
            and self.current_requirements_met
        )

    def navigate_to(self, target: Any, timestamp=None) -> Dict[str, Any]:
        phase = self._target_phase(target)
        previous = self.current
        if not self.can_navigate_to(phase):
            target_position = self._position(phase)
            current_position = self._position(previous)
            if self.mode == 'exam' and target_position < current_position:
                reason = "Les phases d’examen terminées sont verrouillées."
            elif target_position > current_position + 1:
                reason = "Le saut vers une phase future est interdit. Suivez les phases dans l’ordre."
            elif target_position > self.highest_reached_position and not self.current_requirements_met:
                reason = (
                    "La phase suivante reste verrouillée. Éléments encore nécessaires : "
                    + ' '.join(self.current_unmet_requirements)
                )
            else:
                reason = "Revenez à la dernière phase débloquée avant de poursuivre."
            raise NavigationLockedError(reason)

        if phase.number != previous.number:
            changed_at = timestamp or self._now()
            if not isinstance(changed_at, datetime):
                raise ProgressionError('La date de transition est invalide.')
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            self._record_phase_timing(previous, changed_at)
            _write(self.session, 'current_phase', phase.number)
            self._append_timeline(previous, phase, changed_at)
        return self.to_frontend()

    def next_phase(self, timestamp=None) -> Dict[str, Any]:
        position = self._position(self.current)
        if position == len(self.phases):
            return self.to_frontend()
        return self.navigate_to(position + 1, timestamp=timestamp)

    def previous_phase(self, timestamp=None) -> Dict[str, Any]:
        if self.mode == 'exam':
            raise NavigationLockedError("Le retour en arrière est désactivé en mode examen.")
        position = self._position(self.current)
        if position == 1:
            return self.to_frontend()
        return self.navigate_to(position - 1, timestamp=timestamp)

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

    def finalize_current_phase(self, timestamp=None) -> None:
        """Close timing for the last pedagogical phase without creating a phase."""
        changed_at = timestamp or self._now()
        if not isinstance(changed_at, datetime):
            raise ProgressionError('La date de clôture est invalide.')
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        self._record_phase_timing(self.current, changed_at)

    def _append_timeline(self, previous: Phase, phase: Phase, changed_at: datetime) -> None:
        timeline = list(_read(self.session, 'timeline', []) or [])
        timeline.append({
            'timestamp': self._iso(changed_at),
            'action': 'phase_change',
            'actor': 'student',
            'from_phase': self._position(previous),
            'to_phase': self._position(phase),
            'phase': phase.key,
            'details': {'from': previous.label, 'to': phase.label},
        })
        _write(self.session, 'timeline', timeline)

    def _event_phase_position(self, event: Dict[str, Any]):
        value = event.get('phase')
        if isinstance(value, str) and not value.strip().isdigit():
            try:
                phase = _normalize_phase(value)
            except InvalidPhaseError:
                return None
            return self._position(phase) if phase in self.phases else None
        try:
            position = int(value)
        except (TypeError, ValueError):
            return None
        return position if 1 <= position <= len(self.phases) else None

    @property
    def highest_reached_position(self) -> int:
        reached = self._position(self.current)
        for event in _read(self.session, 'timeline', []) or []:
            if event.get('action') != 'phase_change':
                continue
            try:
                target = int(event.get('to_phase'))
            except (TypeError, ValueError):
                target = self._event_phase_position(event)
            if target is not None:
                reached = max(reached, min(target, len(self.phases)))
        timings = _read(self.session, 'phase_timings', {}) or {}
        for key in timings:
            phase = PHASE_BY_KEY.get(key)
            if phase in self.phases:
                reached = max(reached, self._position(phase))
        return reached

    def _phase_actions(self, phase: Phase):
        position = self._position(phase)
        return {
            event.get('action')
            for event in (_read(self.session, 'timeline', []) or [])
            if self._event_phase_position(event) == position
            and not (
                event.get('action') == 'student_message'
                and event.get('outcome') == 'safety_guardrail'
            )
        }

    def unmet_requirements_for(self, phase: Phase):
        requirement = PHASE_MINIMUM_ACTIONS.get(phase.key)
        if not requirement:
            return []
        accepted_actions, message = requirement
        actions = self._phase_actions(phase)
        return [] if any(action in actions for action in accepted_actions) else [message]

    @property
    def current_unmet_requirements(self):
        return self.unmet_requirements_for(self.current)

    @property
    def current_requirements_met(self):
        return not self.current_unmet_requirements

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
        current_position = self._position(current)
        highest_reached = self.highest_reached_position
        completed = [
            number for number in range(1, highest_reached + 1)
            if number != current_position
        ]
        remaining = list(range(highest_reached + 1, len(self.phases) + 1))
        phases = []
        for number, phase in enumerate(self.phases, start=1):
            if number <= highest_reached and number != current_position:
                status = 'completed'
            elif number == current_position:
                status = 'current'
            else:
                status = 'remaining'
            can_navigate = self.can_navigate_to(phase)
            if self.mode == 'exam' and number != current_position:
                can_navigate = False
            if self.simulation_completed:
                can_navigate = False
            phases.append({
                'number': number,
                'canonical_number': phase.number,
                'key': phase.key,
                'label': phase.label,
                'guidance': phase.guidance,
                'status': status,
                'can_navigate': can_navigate,
                'locked': not can_navigate,
                'lock_reason': (
                    None if can_navigate
                    else 'Simulation terminée.'
                    if self.simulation_completed
                    else (
                        'Phase terminée verrouillée en mode examen.'
                        if self.mode == 'exam' and number < current_position
                        else 'Phase future non débloquée.'
                    )
                ),
            })
        return {
            'mode': self.mode,
            'student_level': self.student_level,
            'current_phase': current_position,
            'canonical_phase': current.number,
            'current_phase_key': current.key,
            'current_phase_label': current.label,
            'progress_percentage': self.progress_percentage,
            'completed_phases': completed,
            'remaining_phases': remaining,
            'can_go_back': self.mode == 'training' and current_position > 1,
            'highest_reached_phase': highest_reached,
            'current_phase_ready': self.current_requirements_met,
            'unmet_requirements': self.current_unmet_requirements,
            'requirements_message': (
                'Simulation terminée : l’évaluation et le feedback sont disponibles ci-dessous.'
                if self.simulation_completed
                else 'Phase prête : vous pouvez poursuivre.'
                if self.current_requirements_met
                else 'Éléments encore nécessaires : '
                     + ' '.join(self.current_unmet_requirements)
            ),
            'is_last_phase': current_position == len(self.phases),
            'is_complete': self.simulation_completed,
            'phases': phases,
        }


def get_progression_state(session_state: Any, student=None) -> Dict[str, Any]:
    """Convenience API used by GET progress endpoints."""
    return ProgressionTracker(session_state, student=student).to_frontend()
