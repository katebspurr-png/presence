# Presence Behavioral Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the behavioral engine core for the Presence daemon — scheduler, activity selector, timing distributions, config, logging, and HTTP command server.

**Architecture:** Sync state machine on the main thread with two daemon background threads (ConfigWatcher, CommandServer). Three thread-safe shared objects (EngineControl, StatusStore, ConfigStore) coordinate state. Each activity type owns its own class with a `run(duration_s, control)` interface.

**Tech Stack:** Python 3.11+, stdlib only (threading, sqlite3, http.server, logging) + `anthropic` SDK for Claude API calls.

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | Python dependencies |
| `config.json` | Default runtime configuration |
| `engine/__init__.py` | Package marker |
| `engine/status.py` | `EngineControl`, `StatusStore`, `ConfigStore` — all shared thread-safe state |
| `engine/distributions.py` | `gaussian_duration`, `exponential_duration` — bounded sampling helpers |
| `engine/personas.py` | `PersonaParams` dataclass + `get_persona()` — 5 persona definitions |
| `engine/activities/__init__.py` | Package marker |
| `engine/activities/base.py` | `ActivityBase` ABC, `ActivityResult` dataclass, `interruptible_sleep()` |
| `engine/activities/idle.py` | `IdleActivity` — sleeps for duration |
| `engine/activities/dead_stop.py` | `DeadStopActivity` — sleeps for duration |
| `engine/activities/mouse.py` | `MouseActivity` — stub HID write + sleep |
| `engine/activities/typing.py` | `TypingActivity` — Claude API + 50-string fallback bank + `used_recently` |
| `engine/activity_selector.py` | `ActivitySelector` — time-of-day weights, dead zone detection, duration sampling |
| `engine/logger.py` | `ActivityEvent`, `ActivityLogger` — SQLite + stdout dual logging |
| `engine/config_watcher.py` | `ConfigWatcher` — polls config.json mtime, fires reload event |
| `engine/command_server.py` | `CommandServer` — 4-endpoint localhost HTTP server |
| `engine/scheduler.py` | `run_engine()` — main while-True state machine |
| `run.py` | Entrypoint — wires all components, handles signals |
| `presence.service` | systemd unit file |
| `docs/README.md` | Project documentation |
| `tests/__init__.py` | Package marker |
| `tests/test_distributions.py` | Unit tests for distribution helpers |
| `tests/test_personas.py` | Unit tests for persona loading |
| `tests/test_status.py` | Unit tests for thread-safe shared state |
| `tests/test_activity_selector.py` | Unit tests for activity selection and dead zones |
| `tests/test_activities.py` | Unit tests for activity run() interfaces |
| `tests/test_typing_fallback.py` | Unit tests for fallback bank and used_recently |
| `tests/test_logger.py` | Unit tests for SQLite + stdout logging |
| `tests/test_config_watcher.py` | Unit tests for config file watching |
| `tests/test_command_server.py` | Unit tests for HTTP command endpoints |
| `tests/test_scheduler.py` | Integration smoke test for full engine loop |

---

## Task 1: Project scaffold, requirements.txt, and config.json

**Files:**
- Create: `requirements.txt`
- Create: `config.json`
- Create: `engine/__init__.py`
- Create: `engine/activities/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
cd ~/projects/presence
mkdir -p engine/activities tests docs
```

- [ ] **Step 2: Create requirements.txt**

```
anthropic>=0.30.0
pytest>=8.0.0
```

- [ ] **Step 3: Create engine/__init__.py and engine/activities/__init__.py and tests/__init__.py**

Each file is empty — just package markers:

```bash
touch engine/__init__.py engine/activities/__init__.py tests/__init__.py
```

- [ ] **Step 4: Create config.json**

```json
{
  "persona": "focused_writer",
  "dead_zones": [
    { "start": "09:00", "end": "09:30", "days": ["mon","tue","wed","thu","fri"] }
  ],
  "time_profiles": {
    "typing":    [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.6, 0.7, 0.7, 0.6,
                  0.5, 0.6, 0.7, 0.6, 0.5, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1],
    "mouse":     [0.05,0.05,0.05,0.05,0.05,0.05,0.1, 0.3, 0.5, 0.5, 0.5, 0.4,
                  0.4, 0.5, 0.5, 0.4, 0.3, 0.2, 0.1, 0.05,0.05,0.05,0.05,0.05],
    "idle":      [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.2, 0.2, 0.2, 0.2, 0.3,
                  0.3, 0.2, 0.2, 0.2, 0.3, 0.3, 0.4, 0.4, 0.4, 0.4, 0.3, 0.3],
    "dead_stop": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.4, 0.1, 0.05,0.05,0.05,0.1,
                  0.1, 0.05,0.05,0.1, 0.1, 0.2, 0.3, 0.5, 0.6, 0.6, 0.6, 0.6]
  },
  "personas": {
    "focused_writer":         { "typing_mean_s": 180, "typing_stddev_s": 30, "mouse_lambda": 0.05, "idle_lambda": 0.2,  "wpm": 70 },
    "distracted_multitasker": { "typing_mean_s": 40,  "typing_stddev_s": 15, "mouse_lambda": 0.3,  "idle_lambda": 0.8,  "wpm": 55 },
    "slow_and_steady":        { "typing_mean_s": 120, "typing_stddev_s": 10, "mouse_lambda": 0.1,  "idle_lambda": 0.3,  "wpm": 35 },
    "power_user":             { "typing_mean_s": 90,  "typing_stddev_s": 20, "mouse_lambda": 0.15, "idle_lambda": 0.1,  "wpm": 90 },
    "custom":                 { "typing_mean_s": 90,  "typing_stddev_s": 20, "mouse_lambda": 0.15, "idle_lambda": 0.25, "wpm": 60 }
  },
  "claude": {
    "model": "claude-sonnet-4-20250514",
    "content_types": ["email", "notes", "code_comments"],
    "max_tokens": 300
  },
  "command_server": {
    "host": "127.0.0.1",
    "port": 7777
  },
  "hid": {
    "keyboard": "/dev/hidg0",
    "mouse": "/dev/hidg1"
  },
  "logging": {
    "db_path": "/var/log/presence/presence.db",
    "stdout": true
  }
}
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: packages install cleanly.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.json engine/__init__.py engine/activities/__init__.py tests/__init__.py
git commit -m "feat: project scaffold, requirements, and default config"
```

---

## Task 2: engine/status.py — shared thread-safe state

**Files:**
- Create: `engine/status.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_status.py`:
```python
import threading
from engine.status import ConfigStore, EngineControl, StatusStore


def test_status_store_update_and_snapshot():
    store = StatusStore()
    assert store.snapshot() is None
    store.update({"activity": "typing", "persona": "focused_writer"})
    snap = store.snapshot()
    assert snap["activity"] == "typing"
    assert snap["persona"] == "focused_writer"


def test_status_store_snapshot_is_copy():
    store = StatusStore()
    store.update({"activity": "idle"})
    snap = store.snapshot()
    snap["activity"] = "mutated"
    assert store.snapshot()["activity"] == "idle"


def test_config_store_get_and_set():
    store = ConfigStore({"persona": "focused_writer"})
    assert store.get()["persona"] == "focused_writer"
    store.set({"persona": "power_user"})
    assert store.get()["persona"] == "power_user"


def test_config_store_get_is_copy():
    store = ConfigStore({"persona": "focused_writer"})
    cfg = store.get()
    cfg["persona"] = "mutated"
    assert store.get()["persona"] == "focused_writer"


def test_engine_control_events_default_unset():
    ctrl = EngineControl()
    assert not ctrl.running.is_set()
    assert not ctrl.paused.is_set()
    assert not ctrl.stopped.is_set()
    assert not ctrl.reload.is_set()


def test_engine_control_set_and_clear():
    ctrl = EngineControl()
    ctrl.running.set()
    assert ctrl.running.is_set()
    ctrl.running.clear()
    assert not ctrl.running.is_set()


def test_status_store_thread_safety():
    store = StatusStore()
    errors = []

    def writer():
        for i in range(100):
            store.update({"activity": f"typing_{i}"})

    def reader():
        for _ in range(100):
            try:
                store.snapshot()
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/projects/presence && python -m pytest tests/test_status.py -v
```

Expected: `ImportError` — `engine.status` does not exist yet.

- [ ] **Step 3: Implement engine/status.py**

```python
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EngineControl:
    running: threading.Event = field(default_factory=threading.Event)
    paused: threading.Event = field(default_factory=threading.Event)
    stopped: threading.Event = field(default_factory=threading.Event)
    reload: threading.Event = field(default_factory=threading.Event)


class StatusStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: Optional[dict] = None

    def update(self, status: dict) -> None:
        with self._lock:
            self._status = status.copy()

    def snapshot(self) -> Optional[dict]:
        with self._lock:
            return self._status.copy() if self._status is not None else None


class ConfigStore:
    def __init__(self, config: dict) -> None:
        self._lock = threading.Lock()
        self._config = config.copy()

    def get(self) -> dict:
        with self._lock:
            return self._config.copy()

    def set(self, config: dict) -> None:
        with self._lock:
            self._config = config.copy()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_status.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/status.py tests/test_status.py
git commit -m "feat: thread-safe EngineControl, StatusStore, ConfigStore"
```

---

## Task 3: engine/distributions.py — timing distribution helpers

**Files:**
- Create: `engine/distributions.py`
- Create: `tests/test_distributions.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_distributions.py`:
```python
from engine.distributions import exponential_duration, gaussian_duration


def test_gaussian_stays_within_bounds():
    for _ in range(1000):
        result = gaussian_duration(mean_s=60.0, stddev_s=10.0)
        assert 1.0 <= result <= 3600.0


def test_gaussian_respects_custom_bounds():
    for _ in range(500):
        result = gaussian_duration(mean_s=10.0, stddev_s=5.0, min_s=5.0, max_s=30.0)
        assert 5.0 <= result <= 30.0


def test_gaussian_floor_at_one_second():
    # Use extreme params to guarantee some draws below 1.0
    for _ in range(500):
        result = gaussian_duration(mean_s=0.5, stddev_s=0.1)
        assert result >= 1.0


def test_exponential_stays_within_bounds():
    for _ in range(1000):
        result = exponential_duration(lambda_=0.1)
        assert 1.0 <= result <= 600.0


def test_exponential_respects_custom_bounds():
    for _ in range(500):
        result = exponential_duration(lambda_=0.5, min_s=2.0, max_s=20.0)
        assert 2.0 <= result <= 20.0


def test_exponential_floor_at_one_second():
    for _ in range(500):
        result = exponential_duration(lambda_=1000.0)
        assert result >= 1.0


def test_gaussian_returns_float():
    assert isinstance(gaussian_duration(60.0, 10.0), float)


def test_exponential_returns_float():
    assert isinstance(exponential_duration(0.1), float)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_distributions.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/distributions.py**

```python
import random


def gaussian_duration(
    mean_s: float,
    stddev_s: float,
    min_s: float = 1.0,
    max_s: float = 3600.0,
) -> float:
    """Sample a duration from a Gaussian distribution, clamped to [min_s, max_s]."""
    return float(max(min_s, min(max_s, random.gauss(mean_s, stddev_s))))


def exponential_duration(
    lambda_: float,
    min_s: float = 1.0,
    max_s: float = 600.0,
) -> float:
    """Sample a duration from an Exponential distribution, clamped to [min_s, max_s].

    lambda_ is the rate parameter (events per second). Higher lambda_ = shorter durations.
    """
    return float(max(min_s, min(max_s, random.expovariate(lambda_))))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_distributions.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/distributions.py tests/test_distributions.py
git commit -m "feat: gaussian and exponential duration samplers with bounds"
```

---

## Task 4: engine/personas.py — persona definitions

**Files:**
- Create: `engine/personas.py`
- Create: `tests/test_personas.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_personas.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_personas.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/personas.py**

```python
from dataclasses import dataclass


@dataclass
class PersonaParams:
    name: str
    typing_mean_s: float
    typing_stddev_s: float
    mouse_lambda: float
    idle_lambda: float
    wpm: int


_BUILTIN_PERSONAS: dict[str, PersonaParams] = {
    "focused_writer": PersonaParams(
        name="focused_writer",
        typing_mean_s=180,
        typing_stddev_s=30,
        mouse_lambda=0.05,
        idle_lambda=0.2,
        wpm=70,
    ),
    "distracted_multitasker": PersonaParams(
        name="distracted_multitasker",
        typing_mean_s=40,
        typing_stddev_s=15,
        mouse_lambda=0.3,
        idle_lambda=0.8,
        wpm=55,
    ),
    "slow_and_steady": PersonaParams(
        name="slow_and_steady",
        typing_mean_s=120,
        typing_stddev_s=10,
        mouse_lambda=0.1,
        idle_lambda=0.3,
        wpm=35,
    ),
    "power_user": PersonaParams(
        name="power_user",
        typing_mean_s=90,
        typing_stddev_s=20,
        mouse_lambda=0.15,
        idle_lambda=0.1,
        wpm=90,
    ),
    # "custom" is not in _BUILTIN_PERSONAS — it is always loaded from config
}


def get_persona(name: str, config: dict) -> PersonaParams:
    """Return PersonaParams for the given persona name.

    For "custom", parameters are read directly from config["personas"]["custom"].
    For all others, built-in values are used.
    """
    if name == "custom":
        p = config["personas"]["custom"]
        return PersonaParams(
            name="custom",
            typing_mean_s=float(p["typing_mean_s"]),
            typing_stddev_s=float(p["typing_stddev_s"]),
            mouse_lambda=float(p["mouse_lambda"]),
            idle_lambda=float(p["idle_lambda"]),
            wpm=int(p["wpm"]),
        )
    if name not in _BUILTIN_PERSONAS:
        raise ValueError(f"Unknown persona: {name!r}")
    return _BUILTIN_PERSONAS[name]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_personas.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/personas.py tests/test_personas.py
git commit -m "feat: PersonaParams dataclass and get_persona() with 5 personas"
```

---

## Task 5: engine/activities/base.py, idle.py, dead_stop.py

**Files:**
- Create: `engine/activities/base.py`
- Create: `engine/activities/idle.py`
- Create: `engine/activities/dead_stop.py`
- Create: `tests/test_activities.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_activities.py`:
```python
import time
from engine.activities.base import ActivityResult, interruptible_sleep
from engine.activities.dead_stop import DeadStopActivity
from engine.activities.idle import IdleActivity
from engine.status import EngineControl


def test_activity_result_defaults():
    result = ActivityResult(activity="idle", duration_s=5.0)
    assert result.metadata == {}


def test_interruptible_sleep_completes_full_duration():
    ctrl = EngineControl()
    start = time.monotonic()
    interruptible_sleep(2.0, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed >= 1.9  # allow small timing slop


def test_interruptible_sleep_breaks_on_stop():
    ctrl = EngineControl()
    ctrl.stopped.set()
    start = time.monotonic()
    interruptible_sleep(60.0, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0  # should exit almost immediately


def test_interruptible_sleep_breaks_on_pause():
    ctrl = EngineControl()
    ctrl.paused.set()
    start = time.monotonic()
    interruptible_sleep(60.0, ctrl)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


def test_idle_activity_returns_correct_result():
    ctrl = EngineControl()
    ctrl.stopped.set()  # exit immediately
    activity = IdleActivity()
    result = activity.run(duration_s=60.0, control=ctrl)
    assert result.activity == "idle"
    assert result.duration_s == 60.0


def test_dead_stop_activity_returns_correct_result():
    ctrl = EngineControl()
    ctrl.stopped.set()
    activity = DeadStopActivity()
    result = activity.run(duration_s=30.0, control=ctrl)
    assert result.activity == "dead_stop"
    assert result.duration_s == 30.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_activities.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/activities/base.py**

```python
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ActivityResult:
    activity: str
    duration_s: float
    metadata: dict = field(default_factory=dict)


class ActivityBase(ABC):
    @abstractmethod
    def run(self, duration_s: float, control) -> ActivityResult:
        """Execute this activity for approximately duration_s seconds.

        Must honor control.stopped and control.paused — check at least every
        1 second and return early if either is set.
        """
        ...


def interruptible_sleep(duration: float, control) -> None:
    """Sleep for up to duration seconds, waking within ~1s if stop or pause is set."""
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if control.stopped.is_set() or control.paused.is_set():
            break
        time.sleep(1)
```

- [ ] **Step 4: Implement engine/activities/idle.py**

```python
from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep


class IdleActivity(ActivityBase):
    """Do nothing for duration_s seconds (micro-pause, no HID output)."""

    def run(self, duration_s: float, control) -> ActivityResult:
        interruptible_sleep(duration_s, control)
        return ActivityResult(activity="idle", duration_s=duration_s)
```

- [ ] **Step 5: Implement engine/activities/dead_stop.py**

```python
from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep


class DeadStopActivity(ActivityBase):
    """Complete silence for duration_s seconds (meeting block, no HID output)."""

    def run(self, duration_s: float, control) -> ActivityResult:
        interruptible_sleep(duration_s, control)
        return ActivityResult(activity="dead_stop", duration_s=duration_s)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_activities.py -v
```

Expected: 6 passed. Note: `test_interruptible_sleep_completes_full_duration` takes ~2 seconds — expected.

- [ ] **Step 7: Commit**

```bash
git add engine/activities/base.py engine/activities/idle.py engine/activities/dead_stop.py tests/test_activities.py
git commit -m "feat: ActivityBase, interruptible_sleep, IdleActivity, DeadStopActivity"
```

---

## Task 6: engine/activities/typing.py — Claude API + fallback bank + used_recently

**Files:**
- Create: `engine/activities/typing.py`
- Create: `tests/test_typing_fallback.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_typing_fallback.py`:
```python
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from engine.activities import typing as typing_module
from engine.activities.typing import FALLBACK_CONTENT, TypingActivity
from engine.status import EngineControl

SAMPLE_CONFIG = {
    "claude": {
        "model": "claude-sonnet-4-20250514",
        "content_types": ["email", "notes", "code_comments"],
        "max_tokens": 300,
    },
    "hid": {"keyboard": "/dev/hidg0"},
}


def _make_activity(claude_client=None):
    return TypingActivity(
        config=SAMPLE_CONFIG,
        wpm=60,
        hid_path="/dev/null",
        claude_client=claude_client,
    )


def _reset_used_recently():
    typing_module._used_recently.clear()


def test_fallback_bank_has_50_plus_strings():
    total = sum(len(v) for v in FALLBACK_CONTENT.values())
    assert total >= 50


def test_fallback_bank_has_all_content_types():
    assert "email" in FALLBACK_CONTENT
    assert "notes" in FALLBACK_CONTENT
    assert "code_comments" in FALLBACK_CONTENT


def test_fallback_bank_each_type_has_at_least_15_strings():
    for content_type, strings in FALLBACK_CONTENT.items():
        assert len(strings) >= 15, f"{content_type} has only {len(strings)} strings"


def test_used_recently_prevents_immediate_repeat():
    _reset_used_recently()
    activity = _make_activity()
    seen = set()
    for _ in range(len(FALLBACK_CONTENT["email"])):
        content = activity._pick_fallback("email")
        if content in seen:
            break
        seen.add(content)
    # After exhausting available strings, repeats are allowed — not before
    assert len(seen) == len(FALLBACK_CONTENT["email"])


def test_used_recently_allows_repeat_after_two_hours():
    _reset_used_recently()
    activity = _make_activity()
    first = activity._pick_fallback("email")
    # Backdate the used_recently entry by 3 hours
    typing_module._used_recently[first] = datetime.utcnow() - timedelta(hours=3)
    # Should be available again
    available_again = False
    for _ in range(50):
        result = activity._pick_fallback("email")
        if result == first:
            available_again = True
            break
    assert available_again


def test_used_recently_blocks_within_two_hours():
    _reset_used_recently()
    activity = _make_activity()
    # Force a specific string into used_recently with a recent timestamp
    target = FALLBACK_CONTENT["notes"][0]
    typing_module._used_recently[target] = datetime.utcnow()
    results = [activity._pick_fallback("notes") for _ in range(100)]
    # Should not appear (unless all notes strings are exhausted)
    if len(FALLBACK_CONTENT["notes"]) > 1:
        assert target not in results[:len(FALLBACK_CONTENT["notes"]) - 1]


def test_fallback_used_when_claude_client_is_none():
    _reset_used_recently()
    activity = _make_activity(claude_client=None)
    content = activity._get_content("email")
    assert isinstance(content, str)
    assert len(content) > 0


def test_claude_client_called_when_provided():
    _reset_used_recently()
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Test claude response")]
    mock_client.messages.create.return_value = mock_response
    activity = _make_activity(claude_client=mock_client)
    content = activity._get_content("email")
    assert content == "Test claude response"
    mock_client.messages.create.assert_called_once()


def test_claude_failure_falls_back_to_bank():
    _reset_used_recently()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")
    activity = _make_activity(claude_client=mock_client)
    content = activity._get_content("email")
    assert content in FALLBACK_CONTENT["email"]


def test_run_returns_correct_activity_result():
    _reset_used_recently()
    ctrl = EngineControl()
    ctrl.stopped.set()
    activity = _make_activity()
    result = activity.run(duration_s=5.0, control=ctrl)
    assert result.activity == "typing"
    assert result.metadata["wpm"] == 60
    assert result.metadata["content_type"] in ("email", "notes", "code_comments")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_typing_fallback.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/activities/typing.py**

```python
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep

logger = logging.getLogger(__name__)

# Fallback content bank — used when Claude API is unavailable.
# 55 strings across 3 content types; used_recently prevents repeats within 2 hours.
FALLBACK_CONTENT: dict[str, list[str]] = {
    "email": [
        "Following up on our discussion from yesterday — wanted to make sure we're aligned before the deadline.",
        "Can we schedule a quick sync this week to go over the project status?",
        "Please find the updated report attached. Let me know if you have any questions.",
        "Thanks for the context. I'll review and get back to you by end of day.",
        "Just wanted to loop in the team on this. See thread below.",
        "Per our conversation, I've updated the timeline. The new dates are reflected in the shared doc.",
        "Quick heads up — the meeting tomorrow has been moved to 3pm. Room B is now available.",
        "Appreciate you flagging this. I'll coordinate with the relevant stakeholders and follow up.",
        "The client confirmed receipt. We're good to proceed with the next phase.",
        "Could you take a look at the attached draft and share your feedback?",
        "I wanted to share a brief status update ahead of our next check-in.",
        "Reaching out to confirm we're still on for Thursday's review session.",
        "Thanks everyone for a productive meeting. Summary and action items are below.",
        "I've gone ahead and updated the shared calendar with the new schedule.",
        "Let me know if the proposed approach works or if you'd like to explore alternatives.",
        "Circling back on the open items from last week — two of the three are resolved.",
        "The vendor responded and confirmed delivery by end of month.",
        "Happy to jump on a call if it's easier to discuss live.",
        "Sending this along for your awareness — no action required from your end.",
        "I'll be OOO from Thursday through Monday. Please reach out to Jamie in the interim.",
    ],
    "notes": [
        "Review Q3 metrics before the leadership meeting. Focus on retention and activation numbers.",
        "Draft proposal for the new feature — needs input from design and engineering before finalizing.",
        "TODO: confirm budget allocation with finance team by Friday.",
        "Key takeaways from today's standup: deployment blocked on infra, UX review complete.",
        "Research competitors' onboarding flows — look for patterns we can adapt.",
        "Meeting notes: discussed scope reduction, agreed to cut phase 2 features for now.",
        "Reminder to update the roadmap doc with decisions made this sprint.",
        "Follow up with legal on data retention policy — they had questions about the 90-day window.",
        "The performance issue seems related to the caching layer — worth investigating before launch.",
        "Ideas for the next team offsite: workshop format, half-day, bring in external facilitator.",
        "Outstanding items: API documentation, staging environment access, load test results.",
        "Need to revisit the error handling approach — current implementation is too noisy in logs.",
        "Interesting article about distributed tracing — could be useful for our observability work.",
        "Draft talking points for the all-hands: product progress, team growth, upcoming priorities.",
        "Check in with the data team about the pipeline delay — it's affecting the weekly report.",
        "Document the deployment process before the handoff next month.",
        "The new hire starts Monday — arrange access provisioning and schedule onboarding sessions.",
        "Weekly review: three tickets shipped, two in review, one blocked pending design sign-off.",
        "Rough outline for the architecture decision record on the new storage backend.",
        "Personal note: block focus time Thursday morning for the quarterly planning doc.",
    ],
    "code_comments": [
        "# TODO: refactor this once the upstream API stabilizes — too many edge cases right now",
        "# This calculation assumes UTC timestamps — ensure input is normalized before calling",
        "# Retry logic here is intentional — the downstream service has transient failures",
        "# NOTE: this value is cached for 5 minutes, changes won't be reflected immediately",
        "# Temporary workaround for the race condition in the connection pool — revisit in v2",
        "# The magic number 8192 is the default chunk size for the streaming response parser",
        "# This branch should never be hit in production, but added guard for safety",
        "# Pagination starts at 1, not 0 — the vendor API is inconsistent with our conventions",
        "# We intentionally swallow this error — the operation is best-effort",
        "# Last updated by the build pipeline — do not edit manually",
        "# This regex was tested against 10k sample records — do not simplify without re-testing",
        "# Dependency injection here makes testing easier — see test_service.py for examples",
        "# Rate limit: 100 requests per minute. Back-off logic is in the client wrapper.",
        "# This field is deprecated but retained for backwards compatibility with v1 clients",
        "# Performance note: this query runs full scan on large tables — add index before scaling",
    ],
}

_TWO_HOURS_S = 7200.0

# Module-level: persists across all TypingActivity instances for the lifetime of the process.
_used_recently: dict[str, datetime] = {}


class TypingActivity(ActivityBase):
    def __init__(
        self,
        config: dict,
        wpm: int = 60,
        hid_path: str = "/dev/hidg0",
        claude_client=None,
    ) -> None:
        self.config = config
        self.wpm = wpm
        self.hid_path = hid_path
        self.claude_client = claude_client

    def _pick_content_type(self) -> str:
        types = self.config.get("claude", {}).get(
            "content_types", ["email", "notes", "code_comments"]
        )
        return random.choice(types)

    def _get_content(self, content_type: str) -> str:
        if self.claude_client is not None:
            try:
                return self._fetch_from_claude(content_type)
            except Exception as e:
                logger.warning(f"claude_error={e!r} falling_back_to_bank=True")
        return self._pick_fallback(content_type)

    def _fetch_from_claude(self, content_type: str) -> str:
        model = self.config.get("claude", {}).get("model", "claude-sonnet-4-20250514")
        max_tokens = self.config.get("claude", {}).get("max_tokens", 300)
        prompts = {
            "email": "Write a short, realistic professional work email body (2-4 sentences). No subject line.",
            "notes": "Write a short realistic work note or task reminder (1-3 sentences). Plain text.",
            "code_comments": "Write 1-3 realistic code comments a developer might add while working. Start each with #.",
        }
        response = self.claude_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompts.get(content_type, prompts["notes"])}],
        )
        return response.content[0].text.strip()

    def _pick_fallback(self, content_type: str) -> str:
        global _used_recently
        bank = FALLBACK_CONTENT.get(content_type, FALLBACK_CONTENT["notes"])
        now = datetime.utcnow()

        # Purge entries older than 2 hours
        _used_recently = {
            k: v
            for k, v in _used_recently.items()
            if (now - v).total_seconds() < _TWO_HOURS_S
        }

        available = [s for s in bank if s not in _used_recently]
        if not available:
            # All strings recently used — allow repeats rather than blocking
            available = list(bank)

        chosen = random.choice(available)
        _used_recently[chosen] = now
        return chosen

    def _write_hid(self, content: str) -> None:
        # Stub: actual HID keystroke encoding (USB HID keycodes, 8-byte reports) is
        # out of scope for this phase. A real implementation would translate each
        # character and write reports to self.hid_path at the persona's WPM rate.
        try:
            with open(self.hid_path, "wb") as f:
                f.write(content.encode("utf-8", errors="replace"))
        except OSError as e:
            logger.warning(f"hid_unavailable path={self.hid_path} error={e!r}")

    def run(self, duration_s: float, control) -> ActivityResult:
        content_type = self._pick_content_type()
        content = self._get_content(content_type)
        self._write_hid(content)
        interruptible_sleep(duration_s, control)
        return ActivityResult(
            activity="typing",
            duration_s=duration_s,
            metadata={"content_type": content_type, "wpm": self.wpm},
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_typing_fallback.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/activities/typing.py tests/test_typing_fallback.py
git commit -m "feat: TypingActivity with Claude API, 55-string fallback bank, 2h recency guard"
```

---

## Task 7: engine/activities/mouse.py — stub HID mouse activity

**Files:**
- Create: `engine/activities/mouse.py`

- [ ] **Step 1: Add mouse tests to tests/test_activities.py**

Append to `tests/test_activities.py`:
```python
from engine.activities.mouse import MouseActivity


def test_mouse_activity_returns_correct_result():
    ctrl = EngineControl()
    ctrl.stopped.set()
    activity = MouseActivity(hid_path="/dev/null")
    result = activity.run(duration_s=10.0, control=ctrl)
    assert result.activity == "mouse"
    assert result.duration_s == 10.0


def test_mouse_activity_handles_missing_hid_device():
    ctrl = EngineControl()
    ctrl.stopped.set()
    # /dev/nonexistent should not raise — just log a warning
    activity = MouseActivity(hid_path="/dev/nonexistent_hidg1")
    result = activity.run(duration_s=5.0, control=ctrl)
    assert result.activity == "mouse"
```

- [ ] **Step 2: Run tests to verify new tests fail**

```bash
python -m pytest tests/test_activities.py::test_mouse_activity_returns_correct_result tests/test_activities.py::test_mouse_activity_handles_missing_hid_device -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/activities/mouse.py**

```python
import logging

from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep

logger = logging.getLogger(__name__)


class MouseActivity(ActivityBase):
    """Stub mouse activity.

    Mouse movement algorithm (bezier curves, HID report encoding) is out of scope
    for this phase. A real implementation would write 6-byte mouse HID reports to
    self.hid_path at intervals over duration_s.
    """

    def __init__(self, hid_path: str = "/dev/hidg1") -> None:
        self.hid_path = hid_path

    def run(self, duration_s: float, control) -> ActivityResult:
        # Stub: no HID writes until mouse movement algorithm is implemented.
        interruptible_sleep(duration_s, control)
        return ActivityResult(activity="mouse", duration_s=duration_s)
```

- [ ] **Step 4: Run all activity tests**

```bash
python -m pytest tests/test_activities.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/activities/mouse.py tests/test_activities.py
git commit -m "feat: MouseActivity stub (HID encoding out of scope)"
```

---

## Task 8: engine/activity_selector.py — time-of-day weighting and dead zones

**Files:**
- Create: `engine/activity_selector.py`
- Create: `tests/test_activity_selector.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_activity_selector.py`:
```python
from datetime import datetime, date, timedelta
from unittest.mock import patch

import pytest

from engine.activity_selector import ActivitySelector

BASE_CONFIG = {
    "persona": "focused_writer",
    "dead_zones": [
        {"start": "09:00", "end": "09:30", "days": ["mon", "tue", "wed", "thu", "fri"]},
    ],
    "time_profiles": {
        "typing":    [0.1] * 24,
        "mouse":     [0.1] * 24,
        "idle":      [0.1] * 24,
        "dead_stop": [0.1] * 24,
    },
    "personas": {
        "focused_writer": {
            "typing_mean_s": 60, "typing_stddev_s": 10,
            "mouse_lambda": 0.1, "idle_lambda": 0.2, "wpm": 70,
        },
        "custom": {
            "typing_mean_s": 60, "typing_stddev_s": 10,
            "mouse_lambda": 0.1, "idle_lambda": 0.2, "wpm": 60,
        },
    },
}

ACTIVITY_TYPES = {"typing", "mouse", "idle", "dead_stop"}


def test_select_returns_valid_activity_and_positive_duration():
    selector = ActivitySelector(BASE_CONFIG)
    activity_type, duration_s = selector.select()
    assert activity_type in ACTIVITY_TYPES
    assert duration_s >= 1.0


def test_select_returns_dead_stop_during_dead_zone():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 09:15 is inside the dead zone
    monday_0915 = datetime(2026, 3, 30, 9, 15)  # a Monday
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_0915
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        activity_type, duration_s = selector.select()
    assert activity_type == "dead_stop"
    assert duration_s >= 1.0


def test_select_outside_dead_zone_is_not_forced_dead_stop():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 14:00 is outside the dead zone
    monday_1400 = datetime(2026, 3, 30, 14, 0)
    results = set()
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_1400
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        for _ in range(50):
            activity_type, _ = selector.select()
            results.add(activity_type)
    # With uniform weights, all 4 types should appear eventually
    assert len(results) > 1


def test_select_dead_zone_duration_is_remaining_time_in_zone():
    selector = ActivitySelector(BASE_CONFIG)
    # 15 minutes into a 30-minute zone = ~15 minutes remaining
    monday_0915 = datetime(2026, 3, 30, 9, 15)
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_0915
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        activity_type, duration_s = selector.select()
    assert activity_type == "dead_stop"
    assert 800 <= duration_s <= 950  # ~15 minutes = 900s, allow slop


def test_dead_zone_not_active_on_wrong_day():
    selector = ActivitySelector(BASE_CONFIG)
    # Saturday at 09:15 — dead zone only applies mon-fri
    saturday_0915 = datetime(2026, 4, 4, 9, 15)  # a Saturday
    results = set()
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = saturday_0915
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        for _ in range(50):
            activity_type, _ = selector.select()
            results.add(activity_type)
    assert len(results) > 1  # not forced to dead_stop


def test_time_until_dead_zone_s_returns_positive_int():
    selector = ActivitySelector(BASE_CONFIG)
    # Monday at 08:00 — dead zone starts at 09:00 = 3600s ahead
    monday_0800 = datetime(2026, 3, 30, 8, 0)
    with patch("engine.activity_selector.datetime") as mock_dt:
        mock_dt.now.return_value = monday_0800
        mock_dt.combine = datetime.combine
        mock_dt.strptime = datetime.strptime
        mock_dt.date = date
        result = selector.time_until_dead_zone_s()
    assert result is not None
    assert 3500 <= result <= 3700  # ~1 hour = 3600s


def test_time_until_dead_zone_s_returns_none_when_no_zones():
    config = dict(BASE_CONFIG)
    config["dead_zones"] = []
    selector = ActivitySelector(config)
    assert selector.time_until_dead_zone_s() is None


def test_update_config_changes_persona():
    selector = ActivitySelector(BASE_CONFIG)
    assert selector.current_persona_name == "focused_writer"
    new_config = dict(BASE_CONFIG)
    new_config["persona"] = "custom"
    selector.update_config(new_config)
    assert selector.current_persona_name == "custom"


def test_typing_duration_uses_persona_gaussian():
    selector = ActivitySelector(BASE_CONFIG)
    for _ in range(100):
        _, duration = selector._sample_duration("typing")
        assert 1.0 <= duration <= 3600.0


def test_mouse_duration_uses_exponential():
    selector = ActivitySelector(BASE_CONFIG)
    for _ in range(100):
        _, duration = selector._sample_duration("mouse")
        assert 1.0 <= duration <= 600.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_activity_selector.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/activity_selector.py**

```python
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from engine.distributions import exponential_duration, gaussian_duration
from engine.personas import get_persona

_ACTIVITY_TYPES = ["typing", "mouse", "idle", "dead_stop"]


class ActivitySelector:
    def __init__(self, config: dict) -> None:
        self.config = config

    def update_config(self, config: dict) -> None:
        self.config = config

    @property
    def current_persona_name(self) -> str:
        return self.config["persona"]

    def select(self) -> Tuple[str, float]:
        """Return (activity_type, duration_s) for the next activity."""
        now = datetime.now()

        dead_zone_remaining = self._dead_zone_remaining_s(now)
        if dead_zone_remaining is not None:
            return ("dead_stop", float(dead_zone_remaining))

        hour = now.hour
        weights = [
            self.config["time_profiles"]["typing"][hour],
            self.config["time_profiles"]["mouse"][hour],
            self.config["time_profiles"]["idle"][hour],
            self.config["time_profiles"]["dead_stop"][hour],
        ]

        import random
        activity_type = random.choices(_ACTIVITY_TYPES, weights=weights, k=1)[0]
        _, duration_s = self._sample_duration(activity_type)
        return (activity_type, duration_s)

    def _sample_duration(self, activity_type: str) -> Tuple[str, float]:
        """Return (activity_type, duration_s) using per-persona distribution."""
        persona_name = self.current_persona_name
        p = self.config["personas"][persona_name]

        if activity_type == "typing":
            duration = gaussian_duration(float(p["typing_mean_s"]), float(p["typing_stddev_s"]))
        elif activity_type == "mouse":
            duration = exponential_duration(float(p["mouse_lambda"]))
        elif activity_type == "idle":
            duration = exponential_duration(float(p["idle_lambda"]))
        else:
            # dead_stop outside a dead zone: default 30-minute block
            duration = gaussian_duration(1800.0, 300.0)

        return (activity_type, duration)

    def _dead_zone_remaining_s(self, now: datetime) -> Optional[int]:
        """Return seconds remaining in current dead zone, or None if not in one.

        Dead zone times use 24h "HH:MM" strings — zero-padded (e.g. "09:00").
        String comparison is valid for zero-padded HH:MM format.
        """
        day_name = now.strftime("%a").lower()
        current_time_str = now.strftime("%H:%M")

        for zone in self.config.get("dead_zones", []):
            if day_name not in zone.get("days", []):
                continue
            if zone["start"] <= current_time_str <= zone["end"]:
                zone_end = datetime.combine(
                    now.date(),
                    datetime.strptime(zone["end"], "%H:%M").time(),
                )
                remaining = int((zone_end - now).total_seconds())
                return max(60, remaining)

        return None

    def time_until_dead_zone_s(self) -> Optional[int]:
        """Return seconds until the next dead zone starts (scanning 48h ahead), or None."""
        now = datetime.now()
        earliest: Optional[int] = None

        for offset_days in range(2):
            check_date = now.date() + timedelta(days=offset_days)
            day_name = check_date.strftime("%a").lower()

            for zone in self.config.get("dead_zones", []):
                if day_name not in zone.get("days", []):
                    continue
                zone_start = datetime.combine(
                    check_date,
                    datetime.strptime(zone["start"], "%H:%M").time(),
                )
                if zone_start > now:
                    delta = int((zone_start - now).total_seconds())
                    if earliest is None or delta < earliest:
                        earliest = delta

        return earliest
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_activity_selector.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/activity_selector.py tests/test_activity_selector.py
git commit -m "feat: ActivitySelector with time-of-day weights, dead zones, persona durations"
```

---

## Task 9: engine/logger.py — SQLite + stdout dual logging

**Files:**
- Create: `engine/logger.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_logger.py`:
```python
import json
import os
import sqlite3
import tempfile

import pytest

from engine.logger import ActivityEvent, ActivityLogger


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_presence.db")


def test_logger_creates_table_on_init(tmp_db):
    ActivityLogger(db_path=tmp_db, stdout=False)
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_log'"
        ).fetchone()
    assert row is not None


def test_log_activity_inserts_row(tmp_db):
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    event = ActivityEvent(
        activity="typing",
        persona="focused_writer",
        duration_s=42.5,
        metadata={"content_type": "email", "wpm": 70},
    )
    logger.log_activity(event)

    with sqlite3.connect(tmp_db) as conn:
        rows = conn.execute("SELECT activity, persona, duration_s, metadata FROM activity_log").fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "typing"
    assert rows[0][1] == "focused_writer"
    assert rows[0][2] == 42.5
    assert json.loads(rows[0][3])["content_type"] == "email"


def test_log_activity_multiple_rows(tmp_db):
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    for activity in ["typing", "idle", "mouse", "dead_stop"]:
        logger.log_activity(ActivityEvent(
            activity=activity, persona="power_user", duration_s=10.0, metadata={}
        ))

    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    assert count == 4


def test_log_activity_ts_is_iso8601(tmp_db):
    from datetime import datetime, timezone
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    logger.log_activity(ActivityEvent(
        activity="idle", persona="slow_and_steady", duration_s=5.0, metadata={}
    ))
    with sqlite3.connect(tmp_db) as conn:
        ts = conn.execute("SELECT ts FROM activity_log").fetchone()[0]
    # Should parse without error
    datetime.fromisoformat(ts)


def test_activity_event_defaults():
    event = ActivityEvent(activity="idle", persona="focused_writer", duration_s=5.0)
    assert event.metadata == {}


def test_logger_handles_sqlite_error_gracefully(tmp_db, caplog):
    import logging
    logger = ActivityLogger(db_path=tmp_db, stdout=False)
    # Make the db_path point to a directory (unwritable as a db)
    broken_logger = ActivityLogger(db_path="/dev/null/impossible.db", stdout=False)
    # Should not raise
    broken_logger.log_activity(ActivityEvent(
        activity="idle", persona="focused_writer", duration_s=1.0, metadata={}
    ))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_logger.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/logger.py**

```python
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ActivityEvent:
    activity: str
    persona: str
    duration_s: float
    metadata: dict = field(default_factory=dict)


class ActivityLogger:
    def __init__(self, db_path: str, stdout: bool = True) -> None:
        self.db_path = db_path
        self.stdout = stdout
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS activity_log (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts         TEXT NOT NULL,
                        activity   TEXT NOT NULL,
                        persona    TEXT NOT NULL,
                        duration_s REAL NOT NULL,
                        metadata   TEXT
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"sqlite_init_error={e!r} db_path={self.db_path}")

    def log_activity(self, event: ActivityEvent) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(event.metadata)

        if self.stdout:
            logger.info(
                f"ts={ts} activity={event.activity} persona={event.persona} "
                f"duration_s={event.duration_s:.1f} metadata={metadata_json}"
            )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO activity_log (ts, activity, persona, duration_s, metadata) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (ts, event.activity, event.persona, event.duration_s, metadata_json),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"sqlite_write_error={e!r} activity={event.activity}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_logger.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/logger.py tests/test_logger.py
git commit -m "feat: ActivityLogger with SQLite append-only log and stdout key=value format"
```

---

## Task 10: engine/config_watcher.py — file change detection

**Files:**
- Create: `engine/config_watcher.py`
- Create: `tests/test_config_watcher.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config_watcher.py`:
```python
import json
import os
import tempfile
import time

from engine.config_watcher import ConfigWatcher
from engine.status import ConfigStore, EngineControl


def _write_config(path: str, config: dict) -> None:
    with open(path, "w") as f:
        json.dump(config, f)


def test_config_watcher_fires_reload_on_change(tmp_path):
    config_file = str(tmp_path / "config.json")
    initial = {"persona": "focused_writer"}
    updated = {"persona": "power_user"}
    _write_config(config_file, initial)

    ctrl = EngineControl()
    store = ConfigStore(initial)
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    watcher.start()

    time.sleep(0.1)  # let watcher read initial mtime
    _write_config(config_file, updated)
    time.sleep(3)  # watcher polls every 2s

    ctrl.stopped.set()
    watcher.join(timeout=2)

    assert ctrl.reload.is_set()
    assert store.get()["persona"] == "power_user"


def test_config_watcher_bad_json_keeps_old_config(tmp_path):
    config_file = str(tmp_path / "config.json")
    initial = {"persona": "focused_writer"}
    _write_config(config_file, initial)

    ctrl = EngineControl()
    store = ConfigStore(initial)
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    watcher.start()

    time.sleep(0.1)
    # Write invalid JSON
    with open(config_file, "w") as f:
        f.write("{not valid json}")
    time.sleep(3)

    ctrl.stopped.set()
    watcher.join(timeout=2)

    # Config should remain unchanged
    assert store.get()["persona"] == "focused_writer"
    # Reload event should NOT be set (bad parse = no swap)
    assert not ctrl.reload.is_set()


def test_config_watcher_is_daemon_thread(tmp_path):
    config_file = str(tmp_path / "config.json")
    _write_config(config_file, {"persona": "focused_writer"})
    ctrl = EngineControl()
    store = ConfigStore({})
    watcher = ConfigWatcher(config_path=config_file, config_store=store, control=ctrl)
    assert watcher.daemon is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_config_watcher.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/config_watcher.py**

```python
import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


class ConfigWatcher(threading.Thread):
    """Polls config.json mtime every 2 seconds. On change, parses and swaps ConfigStore.

    Fires control.reload so the engine loop picks up the new config between activities.
    On parse failure, keeps the existing config and does not fire reload.
    """

    def __init__(self, config_path: str, config_store, control) -> None:
        super().__init__(daemon=True, name="config-watcher")
        self.config_path = config_path
        self.config_store = config_store
        self.control = control
        self._last_mtime: float = 0.0

    def run(self) -> None:
        while not self.control.stopped.is_set():
            try:
                mtime = os.path.getmtime(self.config_path)
                if self._last_mtime != 0.0 and mtime != self._last_mtime:
                    with open(self.config_path) as f:
                        new_config = json.load(f)
                    self.config_store.set(new_config)
                    self.control.reload.set()
                    logger.info(f"config_reloaded path={self.config_path}")
                self._last_mtime = mtime
            except json.JSONDecodeError as e:
                logger.error(f"config_parse_error={e!r} keeping_existing_config=True")
            except OSError as e:
                logger.error(f"config_watch_os_error={e!r}")
            time.sleep(2)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_config_watcher.py -v
```

Expected: 3 passed. These tests take ~6 seconds total (polling delays).

- [ ] **Step 5: Commit**

```bash
git add engine/config_watcher.py tests/test_config_watcher.py
git commit -m "feat: ConfigWatcher polls mtime every 2s, fires reload, rejects bad JSON"
```

---

## Task 11: engine/command_server.py — localhost HTTP command server

**Files:**
- Create: `engine/command_server.py`
- Create: `tests/test_command_server.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_command_server.py`:
```python
import json
import time
import urllib.request
from urllib.error import HTTPError

import pytest

from engine.command_server import CommandServer
from engine.status import EngineControl, StatusStore

TEST_PORT = 17777  # high port to avoid conflicts


@pytest.fixture
def server():
    ctrl = EngineControl()
    ctrl.running.set()
    store = StatusStore()
    store.update({"activity": "typing", "persona": "focused_writer",
                  "next_change_at": "14:00:00", "time_until_dead_zone_s": 3600})
    srv = CommandServer(host="127.0.0.1", port=TEST_PORT, control=ctrl, status_store=store)
    srv.start()
    time.sleep(0.1)  # let server bind
    yield srv, ctrl, store
    srv.shutdown()


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{TEST_PORT}{path}") as r:
        return json.loads(r.read())


def _post(path: str) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{TEST_PORT}{path}",
        data=b"",
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_get_status_returns_snapshot(server):
    srv, ctrl, store = server
    data = _get("/status")
    assert data["activity"] == "typing"
    assert data["persona"] == "focused_writer"


def test_post_stop_sets_stopped_event(server):
    srv, ctrl, store = server
    data = _post("/stop")
    assert data["status"] == "stopped"
    assert ctrl.stopped.is_set()
    assert not ctrl.running.is_set()


def test_post_start_sets_running_event(server):
    srv, ctrl, store = server
    ctrl.stopped.set()
    ctrl.running.clear()
    data = _post("/start")
    assert data["status"] == "started"
    assert ctrl.running.is_set()
    assert not ctrl.stopped.is_set()


def test_post_pause_toggles_paused(server):
    srv, ctrl, store = server
    assert not ctrl.paused.is_set()
    data = _post("/pause")
    assert data["status"] == "paused"
    assert ctrl.paused.is_set()
    data = _post("/pause")
    assert data["status"] == "resumed"
    assert not ctrl.paused.is_set()


def test_get_unknown_path_returns_404(server):
    srv, ctrl, store = server
    with pytest.raises(HTTPError) as exc_info:
        _get("/unknown")
    assert exc_info.value.code == 404


def test_server_is_daemon_thread(server):
    srv, ctrl, store = server
    assert srv.daemon is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_command_server.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/command_server.py**

```python
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


def _make_handler(control, status_store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # suppress default access log
            logger.debug(f"http {fmt % args}")

        def _send_json(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/status":
                snapshot = status_store.snapshot()
                self._send_json(200, snapshot or {})
            else:
                self._send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/start":
                control.stopped.clear()
                control.paused.clear()
                control.running.set()
                self._send_json(200, {"status": "started"})
            elif self.path == "/stop":
                control.running.clear()
                control.stopped.set()
                self._send_json(200, {"status": "stopped"})
            elif self.path == "/pause":
                if control.paused.is_set():
                    control.paused.clear()
                    self._send_json(200, {"status": "resumed"})
                else:
                    control.paused.set()
                    self._send_json(200, {"status": "paused"})
            else:
                self._send_json(404, {"error": "not found"})

    return Handler


class CommandServer(threading.Thread):
    """Minimal HTTP server on localhost for start/stop/pause/status commands."""

    def __init__(self, host: str, port: int, control, status_store) -> None:
        super().__init__(daemon=True, name="command-server")
        handler = _make_handler(control, status_store)
        self._server = HTTPServer((host, port), handler)

    def run(self) -> None:
        logger.info(f"command_server_listening host={self._server.server_address[0]} port={self._server.server_address[1]}")
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_command_server.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add engine/command_server.py tests/test_command_server.py
git commit -m "feat: CommandServer with /start /stop /pause /status over localhost HTTP"
```

---

## Task 12: engine/scheduler.py — main state machine + integration smoke test

**Files:**
- Create: `engine/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing integration smoke test**

`tests/test_scheduler.py`:
```python
import sqlite3
import tempfile
import threading
import time

from engine.activity_selector import ActivitySelector
from engine.logger import ActivityLogger
from engine.scheduler import run_engine
from engine.status import ConfigStore, EngineControl, StatusStore

SMOKE_CONFIG = {
    "persona": "focused_writer",
    "dead_zones": [],
    "time_profiles": {
        "typing":    [0.4] * 24,
        "mouse":     [0.2] * 24,
        "idle":      [0.3] * 24,
        "dead_stop": [0.1] * 24,
    },
    "personas": {
        "focused_writer": {
            "typing_mean_s": 2, "typing_stddev_s": 0.5,
            "mouse_lambda": 2.0, "idle_lambda": 2.0, "wpm": 60,
        },
        "custom": {
            "typing_mean_s": 2, "typing_stddev_s": 0.5,
            "mouse_lambda": 2.0, "idle_lambda": 2.0, "wpm": 60,
        },
    },
    "claude": {
        "model": "claude-sonnet-4-20250514",
        "content_types": ["email"],
        "max_tokens": 50,
    },
    "hid": {"keyboard": "/dev/null", "mouse": "/dev/null"},
    "logging": {"db_path": "", "stdout": False},
}


def test_engine_runs_multiple_activities_and_stops(tmp_path):
    db_path = str(tmp_path / "smoke.db")
    ctrl = EngineControl()
    ctrl.running.set()
    config_store = ConfigStore(SMOKE_CONFIG)
    status_store = StatusStore()
    activity_logger = ActivityLogger(db_path=db_path, stdout=False)

    engine_thread = threading.Thread(
        target=run_engine,
        kwargs=dict(
            control=ctrl,
            config_store=config_store,
            status_store=status_store,
            activity_logger=activity_logger,
            claude_client=None,  # force fallback bank
        ),
    )
    engine_thread.start()

    time.sleep(8)  # let a few short activities complete
    ctrl.stopped.set()
    engine_thread.join(timeout=5)

    assert not engine_thread.is_alive()

    # Status dict should be populated
    snap = status_store.snapshot()
    assert snap is not None
    assert snap["activity"] in {"typing", "mouse", "idle", "dead_stop"}
    assert snap["persona"] == "focused_writer"
    assert "next_change_at" in snap

    # SQLite should have at least one row
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    assert count >= 1


def test_engine_respects_pause_and_resume(tmp_path):
    db_path = str(tmp_path / "pause.db")
    ctrl = EngineControl()
    ctrl.running.set()
    config_store = ConfigStore(SMOKE_CONFIG)
    status_store = StatusStore()
    activity_logger = ActivityLogger(db_path=db_path, stdout=False)

    engine_thread = threading.Thread(
        target=run_engine,
        kwargs=dict(
            control=ctrl,
            config_store=config_store,
            status_store=status_store,
            activity_logger=activity_logger,
            claude_client=None,
        ),
    )
    engine_thread.start()
    time.sleep(1)

    ctrl.paused.set()
    time.sleep(0.5)
    snap_while_paused = status_store.snapshot()

    time.sleep(2)
    snap_still_paused = status_store.snapshot()

    # Status should not change while paused (no new activities run)
    assert snap_while_paused == snap_still_paused or snap_while_paused is None

    ctrl.paused.clear()
    time.sleep(3)
    ctrl.stopped.set()
    engine_thread.join(timeout=5)
    assert not engine_thread.is_alive()


def test_engine_handles_activity_exception_and_continues(tmp_path):
    """Engine should not die if an activity raises an exception."""
    from unittest.mock import patch
    db_path = str(tmp_path / "exc.db")
    ctrl = EngineControl()
    ctrl.running.set()
    config_store = ConfigStore(SMOKE_CONFIG)
    status_store = StatusStore()
    activity_logger = ActivityLogger(db_path=db_path, stdout=False)

    call_count = {"n": 0}
    original_select = ActivitySelector.select

    def flaky_select(self):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated selector crash")
        return original_select(self)

    engine_thread = threading.Thread(
        target=run_engine,
        kwargs=dict(
            control=ctrl,
            config_store=config_store,
            status_store=status_store,
            activity_logger=activity_logger,
            claude_client=None,
        ),
    )
    with patch.object(ActivitySelector, "select", flaky_select):
        engine_thread.start()
        time.sleep(6)
        ctrl.stopped.set()
        engine_thread.join(timeout=5)

    assert not engine_thread.is_alive()
    # At least one successful activity after the crash
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
    assert count >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement engine/scheduler.py**

```python
import logging
import time
from datetime import datetime, timedelta

from engine.activities.base import interruptible_sleep
from engine.activities.dead_stop import DeadStopActivity
from engine.activities.idle import IdleActivity
from engine.activities.mouse import MouseActivity
from engine.activities.typing import TypingActivity
from engine.activity_selector import ActivitySelector
from engine.logger import ActivityEvent, ActivityLogger
from engine.personas import get_persona
from engine.status import ConfigStore, EngineControl, StatusStore

logger = logging.getLogger(__name__)


def run_engine(
    control: EngineControl,
    config_store: ConfigStore,
    status_store: StatusStore,
    activity_logger: ActivityLogger,
    claude_client=None,
) -> None:
    """Main engine loop. Runs on the calling thread until control.stopped is set."""
    config = config_store.get()
    selector = ActivitySelector(config)
    logger.info("engine_loop_start")

    while True:
        if control.stopped.is_set():
            logger.info("engine_loop_stop")
            break

        if control.reload.is_set():
            config = config_store.get()
            selector.update_config(config)
            control.reload.clear()
            logger.info("engine_config_reloaded")

        if control.paused.is_set():
            time.sleep(1)
            continue

        try:
            activity_type, duration_s = selector.select()
        except Exception as e:
            logger.error(f"selector_error={e!r}", exc_info=True)
            time.sleep(1)
            continue

        persona_name = selector.current_persona_name
        next_change_at = (datetime.now() + timedelta(seconds=duration_s)).strftime("%H:%M:%S")

        status_store.update({
            "activity": activity_type,
            "persona": persona_name,
            "next_change_at": next_change_at,
            "time_until_dead_zone_s": selector.time_until_dead_zone_s(),
        })

        persona = get_persona(persona_name, config)
        hid_keyboard = config["hid"]["keyboard"]
        hid_mouse = config["hid"]["mouse"]

        if activity_type == "typing":
            activity = TypingActivity(
                config=config,
                wpm=persona.wpm,
                hid_path=hid_keyboard,
                claude_client=claude_client,
            )
        elif activity_type == "mouse":
            activity = MouseActivity(hid_path=hid_mouse)
        elif activity_type == "idle":
            activity = IdleActivity()
        else:
            activity = DeadStopActivity()

        logger.info(
            f"activity_start type={activity_type} persona={persona_name} "
            f"duration_s={duration_s:.1f}"
        )

        start = time.monotonic()
        try:
            result = activity.run(duration_s, control)
        except Exception as e:
            logger.error(f"activity_error type={activity_type} error={e!r}", exc_info=True)
            continue

        actual_duration = time.monotonic() - start

        activity_logger.log_activity(ActivityEvent(
            activity=activity_type,
            persona=persona_name,
            duration_s=actual_duration,
            metadata=result.metadata,
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: 3 passed. Tests take ~25 seconds total (real sleep-based timing).

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add engine/scheduler.py tests/test_scheduler.py
git commit -m "feat: run_engine() state machine with reload, pause, exception recovery"
```

---

## Task 13: run.py, presence.service, and docs/README.md

**Files:**
- Create: `run.py`
- Create: `presence.service`
- Create: `docs/README.md`

- [ ] **Step 1: Create run.py**

```python
#!/usr/bin/env python3
"""Presence behavioral engine entrypoint.

Usage:
    python run.py

Environment:
    PRESENCE_CONFIG  Path to config.json (default: config.json)
    ANTHROPIC_API_KEY  Required for Claude API content generation (optional — falls back to bank)
"""
import json
import logging
import os
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

log = logging.getLogger("presence")

from engine.command_server import CommandServer
from engine.config_watcher import ConfigWatcher
from engine.logger import ActivityLogger
from engine.scheduler import run_engine
from engine.status import ConfigStore, EngineControl, StatusStore

CONFIG_PATH = os.environ.get("PRESENCE_CONFIG", "config.json")


def main() -> None:
    log.info(f"presence_start config={CONFIG_PATH}")

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    control = EngineControl()
    control.running.set()

    config_store = ConfigStore(config)
    status_store = StatusStore()

    log_cfg = config.get("logging", {})
    db_path = log_cfg.get("db_path", "presence.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True) if os.path.dirname(db_path) else None
    activity_logger = ActivityLogger(
        db_path=db_path,
        stdout=log_cfg.get("stdout", True),
    )

    server_cfg = config.get("command_server", {})
    command_server = CommandServer(
        host=server_cfg.get("host", "127.0.0.1"),
        port=int(server_cfg.get("port", 7777)),
        control=control,
        status_store=status_store,
    )
    command_server.start()

    config_watcher = ConfigWatcher(
        config_path=CONFIG_PATH,
        config_store=config_store,
        control=control,
    )
    config_watcher.start()

    claude_client = None
    try:
        import anthropic
        claude_client = anthropic.Anthropic()
        log.info("claude_client_initialized")
    except Exception as e:
        log.warning(f"claude_client_unavailable={e!r} using_fallback_bank=True")

    def _handle_signal(sig, frame):
        log.info(f"signal={sig} shutting_down")
        control.stopped.set()
        command_server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    run_engine(
        control=control,
        config_store=config_store,
        status_store=status_store,
        activity_logger=activity_logger,
        claude_client=claude_client,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create presence.service**

```ini
[Unit]
Description=Presence Behavioral Engine (Infinite Saturdays)
After=network.target
Wants=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/presence
ExecStart=/home/pi/presence/venv/bin/python run.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PRESENCE_CONFIG=/home/pi/presence/config.json
Environment=ANTHROPIC_API_KEY=your_key_here

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Create docs/README.md**

```markdown
# Presence

Behavioral engine for Raspberry Pi Zero 2W (Infinite Saturdays). Simulates realistic human computer activity via USB/Bluetooth HID to avoid detection by workplace monitoring software.

## Hardware

- Raspberry Pi Zero 2W
- USB gadget mode: presents as keyboard (`/dev/hidg0`) and mouse (`/dev/hidg1`) to host
- Bluetooth HID pairing for wireless operation

## Project Structure

```
presence/
├── engine/                 # Core behavioral engine
│   ├── scheduler.py        # Main state machine loop
│   ├── activity_selector.py# Time-of-day weighting + dead zone detection
│   ├── distributions.py    # Gaussian/Exponential duration samplers
│   ├── personas.py         # 5 persona definitions
│   ├── activities/         # Activity implementations
│   │   ├── typing.py       # Claude API content + fallback bank
│   │   ├── mouse.py        # Mouse movement stub
│   │   ├── idle.py         # Micro-pause
│   │   └── dead_stop.py    # Meeting block silence
│   ├── status.py           # Thread-safe shared state
│   ├── logger.py           # SQLite + stdout logging
│   ├── config_watcher.py   # Live config reload
│   └── command_server.py   # HTTP control endpoint
├── config.json             # Runtime configuration
├── run.py                  # Entrypoint
└── presence.service        # systemd unit
```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python run.py
```

## Configuration

Edit `config.json` — changes are picked up live (no restart needed).

Key settings:
- `persona`: `focused_writer` | `distracted_multitasker` | `slow_and_steady` | `power_user` | `custom`
- `dead_zones`: list of `{start, end, days}` meeting blocks
- `time_profiles`: 24-element weight arrays per activity type
- `claude.model`: Claude model for content generation (default: `claude-sonnet-4-20250514`)

## systemd Deployment

```bash
sudo cp presence.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable presence
sudo systemctl start presence
sudo journalctl -u presence -f
```

## HTTP Control API

Runs on `127.0.0.1:7777` (configurable).

| Method | Path | Action |
|---|---|---|
| GET | /status | Returns current activity, persona, next change, time until dead zone |
| POST | /start | Start/resume the engine |
| POST | /stop | Stop the engine |
| POST | /pause | Toggle pause |

## Running Tests

```bash
python -m pytest tests/ -v
```

## Activity Types

| Type | Description | Distribution |
|---|---|---|
| `typing` | Generates content via Claude (or fallback bank), writes to HID keyboard | Gaussian duration |
| `mouse` | Mouse movement stub (HID encoding TBD) | Exponential duration |
| `idle` | Micro-pause, no HID output | Exponential duration |
| `dead_stop` | Complete silence (meeting block) | Duration = time remaining in dead zone |

## Personas

| Persona | WPM | Character |
|---|---|---|
| `focused_writer` | 70 | Long typing bursts, rare mouse |
| `distracted_multitasker` | 55 | Short bursts, frequent mouse |
| `slow_and_steady` | 35 | Stretched durations, low variance |
| `power_user` | 90 | Fast, dense, short gaps |
| `custom` | configurable | All params from config.json |
```

- [ ] **Step 4: Verify the engine starts**

```bash
cd ~/projects/presence
python run.py &
sleep 2
curl http://127.0.0.1:7777/status
kill %1
```

Expected: JSON response with `activity`, `persona`, `next_change_at`, `time_until_dead_zone_s`.

- [ ] **Step 5: Run full test suite one final time**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add run.py presence.service docs/README.md
git commit -m "feat: entrypoint, systemd unit, and project README"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Time-of-day probability profiles — `activity_selector.py` Task 8
- [x] Gaussian/Poisson/Exponential distributions — `distributions.py` Task 3 (Poisson → Exponential per spec correction)
- [x] Dead zones (meeting blocks) from config — `activity_selector.py` Task 8
- [x] 5 typing personas including Custom stub — `personas.py` Task 4
- [x] Claude API content generation — `typing.py` Task 6
- [x] 50+ fallback strings across 3 content types — `typing.py` Task 6 (55 strings)
- [x] used_recently 2-hour recency guard — `typing.py` Task 6
- [x] HID keyboard `/dev/hidg0` — `typing.py` (injectable, stub write)
- [x] HID mouse `/dev/hidg1` — `mouse.py` (stub, algorithm out of scope)
- [x] SQLite activity log — `logger.py` Task 9
- [x] Stdout journald-compatible logging — `logger.py` Task 9
- [x] ConfigWatcher live reload — `config_watcher.py` Task 10
- [x] CommandServer start/stop/pause/status — `command_server.py` Task 11
- [x] Status dict after each transition — `scheduler.py` Task 12
- [x] Interruptible sleep (~1s responsiveness) — `base.py` Task 5
- [x] Thread-safe EngineControl/StatusStore/ConfigStore — `status.py` Task 2
- [x] config.json schema with default values — Task 1
- [x] requirements.txt — Task 1
- [x] systemd unit — Task 13
- [x] README — Task 13
- [x] Error handling: Claude failure → fallback, HID unavailable → warn+continue, config parse error → keep old, SQLite failure → stdout only, activity exception → log+continue

**All tasks verified complete.**
```
