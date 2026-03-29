import time
from datetime import datetime, timedelta, timezone
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
    typing_module._used_recently[first] = datetime.now(timezone.utc) - timedelta(hours=3)
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
    typing_module._used_recently[target] = datetime.now(timezone.utc)
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
