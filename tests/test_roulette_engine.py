from roulette_engine import RouletteEngine, RouletteSession, normalize_message


class FixedRandom:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value
        self.last_choice: list[str] | None = None

    def choice(self, sequence: list[str]) -> str:
        self.last_choice = list(sequence)
        return sequence[0]

    def random(self) -> float:
        return self.value


def test_repeated_messages_keep_duplicate_chambers() -> None:
    rng = FixedRandom()
    engine = RouletteEngine(
        min_repeat_count=2,
        base_bullet_chance=30,
        chance_per_repeat=20,
        rng=rng,
    )
    session = RouletteSession()

    engine.advance(session, message="复读", sender_id="original", now=0)
    engine.advance(session, message="复读", sender_id="alice", now=1)
    engine.advance(session, message="复读", sender_id="alice", now=2)
    outcome = engine.advance(session, message="打断", sender_id="bob", now=3)

    assert outcome is not None
    assert rng.last_choice == ["alice", "alice"]
    assert outcome.target_user_id == "alice"
    assert outcome.repeat_count == 2
    assert outcome.bullet_chance == 30
    assert outcome.fired is True


def test_more_repeats_raise_and_cap_bullet_chance() -> None:
    engine = RouletteEngine(
        min_repeat_count=2,
        base_bullet_chance=20,
        chance_per_repeat=25,
        max_bullet_chance=60,
        rng=FixedRandom(0.99),
    )
    session = RouletteSession()

    engine.advance(session, message="same", sender_id="original", now=0)
    for now in range(1, 6):
        engine.advance(session, message="same", sender_id=str(now), now=now)
    outcome = engine.advance(session, message="different", sender_id="breaker", now=6)

    assert outcome is not None
    assert outcome.repeat_count == 5
    assert outcome.bullet_chance == 60
    assert outcome.fired is False


def test_timeout_quietly_discards_a_round() -> None:
    engine = RouletteEngine(round_timeout_seconds=30, rng=FixedRandom())
    session = RouletteSession()

    engine.advance(session, message="same", sender_id="original", now=0)
    engine.advance(session, message="same", sender_id="alice", now=1)
    outcome = engine.advance(session, message="different", sender_id="bob", now=32)

    assert outcome is None
    assert session.last_message == "different"
    assert session.repeat_users == []


def test_whitespace_is_not_a_round_breaker() -> None:
    engine = RouletteEngine(rng=FixedRandom())
    session = RouletteSession()

    engine.advance(session, message="  hello   world ", sender_id="original", now=0)
    engine.advance(session, message="hello world", sender_id="alice", now=1)

    assert normalize_message("  hello   world ") == "hello world"
    assert session.repeat_users == ["alice"]
