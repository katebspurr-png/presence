import logging
import random
from datetime import datetime, timedelta

from engine.activities.base import ActivityBase, ActivityResult, interruptible_sleep

logger = logging.getLogger(__name__)

# Fallback content bank — 55 strings across 3 content types.
# Used when Claude API is unavailable.
# _used_recently prevents repeats within a 2-hour window.
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
