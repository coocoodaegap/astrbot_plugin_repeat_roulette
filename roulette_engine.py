"""Pure, testable rules for the repeat roulette round lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Protocol


class RandomSource(Protocol):
    """The tiny portion of a random generator used by the rules engine."""

    def choice(self, sequence: list[str]) -> str: ...

    def random(self) -> float: ...


@dataclass
class RouletteSession:
    """In-memory state for one group and one currently tracked message."""

    last_message: str | None = None
    repeat_users: list[str] = field(default_factory=list)
    last_activity_at: float = 0.0


@dataclass(frozen=True)
class RouletteOutcome:
    """A completed round that the AstrBot layer should announce or enforce."""

    target_user_id: str
    repeat_count: int
    bullet_chance: int
    fired: bool


def normalize_message(message: str) -> str:
    """Normalize text-only messages so harmless whitespace changes do not break a round."""

    return " ".join(message.split())


class RouletteEngine:
    """Advance a round with one message and return an outcome only when it breaks."""

    def __init__(
        self,
        *,
        min_repeat_count: int = 2,
        base_bullet_chance: int = 20,
        chance_per_repeat: int = 15,
        max_bullet_chance: int = 80,
        random_mode: bool = True,
        last_n_th: int = 1,
        round_timeout_seconds: int = 180,
        rng: RandomSource | None = None,
    ) -> None:
        self.min_repeat_count = max(1, int(min_repeat_count))
        self.base_bullet_chance = self._clamp_percent(base_bullet_chance)
        self.chance_per_repeat = max(0, int(chance_per_repeat))
        self.max_bullet_chance = max(
            self.base_bullet_chance, self._clamp_percent(max_bullet_chance)
        )
        self.random_mode = bool(random_mode)
        self.last_n_th = max(1, int(last_n_th))
        self.round_timeout_seconds = max(1, int(round_timeout_seconds))
        self.rng = rng or random.SystemRandom()

    def advance(
        self,
        session: RouletteSession,
        *,
        message: str,
        sender_id: str,
        now: float,
    ) -> RouletteOutcome | None:
        """Record a message and return the previous round's result if it was broken.

        Repeated messages append one chamber entry every time, including when the
        same member sends them repeatedly. A stale round expires quietly.
        """

        normalized_message = normalize_message(message)
        if not normalized_message:
            return None

        if (
            session.last_message is None
            or now - session.last_activity_at > self.round_timeout_seconds
        ):
            self._start_round(session, normalized_message, now)
            return None

        if normalized_message == session.last_message:
            session.repeat_users.append(sender_id)
            session.last_activity_at = now
            return None

        outcome = self._resolve_round(session)
        self._start_round(session, normalized_message, now)
        return outcome

    def _resolve_round(self, session: RouletteSession) -> RouletteOutcome | None:
        repeat_count = len(session.repeat_users)
        if repeat_count < self.min_repeat_count:
            return None

        target_user_id = self._pick_target(session.repeat_users)
        if target_user_id is None:
            return None

        bullet_chance = min(
            self.max_bullet_chance,
            self.base_bullet_chance
            + (repeat_count - self.min_repeat_count) * self.chance_per_repeat,
        )
        return RouletteOutcome(
            target_user_id=target_user_id,
            repeat_count=repeat_count,
            bullet_chance=bullet_chance,
            fired=self.rng.random() < bullet_chance / 100,
        )

    def _pick_target(self, repeat_users: list[str]) -> str | None:
        if self.random_mode:
            # A user who repeats more often has more entries and therefore a
            # proportionally higher chance of being selected.
            return self.rng.choice(repeat_users)
        if self.last_n_th > len(repeat_users):
            return None
        return repeat_users[-self.last_n_th]

    @staticmethod
    def _start_round(session: RouletteSession, message: str, now: float) -> None:
        session.last_message = message
        session.repeat_users.clear()
        session.last_activity_at = now

    @staticmethod
    def _clamp_percent(value: int) -> int:
        return min(100, max(0, int(value)))
