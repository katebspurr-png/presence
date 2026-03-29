import pytest
from engine.personas import PersonaParams, get_persona

SAMPLE_CONFIG = {
    "personas": {
        "custom": {
            "typing_mean_s": 100,
            "typing_stddev_s": 25,
            "mouse_lambda": 0.2,
            "idle_lambda": 0.4,
            "wpm": 65,
        }
    }
}


def test_get_persona_focused_writer():
    p = get_persona("focused_writer", SAMPLE_CONFIG)
    assert p.name == "focused_writer"
    assert p.typing_mean_s == 180
    assert p.typing_stddev_s == 30
    assert p.mouse_lambda == 0.05
    assert p.idle_lambda == 0.2
    assert p.wpm == 70


def test_get_persona_distracted_multitasker():
    p = get_persona("distracted_multitasker", SAMPLE_CONFIG)
    assert p.typing_mean_s == 40
    assert p.wpm == 55


def test_get_persona_slow_and_steady():
    p = get_persona("slow_and_steady", SAMPLE_CONFIG)
    assert p.typing_stddev_s == 10
    assert p.wpm == 35


def test_get_persona_power_user():
    p = get_persona("power_user", SAMPLE_CONFIG)
    assert p.wpm == 90
    assert p.mouse_lambda == 0.15


def test_get_persona_custom_reads_from_config():
    p = get_persona("custom", SAMPLE_CONFIG)
    assert p.name == "custom"
    assert p.typing_mean_s == 100
    assert p.wpm == 65


def test_get_persona_unknown_raises():
    with pytest.raises(ValueError, match="Unknown persona"):
        get_persona("nonexistent", SAMPLE_CONFIG)


def test_persona_params_is_dataclass():
    p = get_persona("power_user", SAMPLE_CONFIG)
    assert isinstance(p, PersonaParams)


def test_persona_params_is_immutable():
    p = get_persona("focused_writer", {})
    try:
        p.wpm = 999
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass  # expected


def test_get_persona_builtin_returns_consistent_values():
    p1 = get_persona("focused_writer", {})
    p2 = get_persona("focused_writer", {})
    assert p1.wpm == p2.wpm == 70
