"""One shared wall deadline for every externally active stage of a study step."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import time

from market_rsi import fresh_json


LOCAL_OVERHEAD_SECONDS = 30
PROFILE = "shared-absolute-step-deadline-v1"


class StepDeadline:
    """Bind research, coding and sandbox work to one non-renewable deadline."""

    def __init__(self, *, started_monotonic, deadline_monotonic, deadline_utc, cap_seconds):
        self.started_monotonic = started_monotonic
        self.deadline_monotonic = deadline_monotonic
        self.deadline_utc = deadline_utc
        self.cap_seconds = cap_seconds

    @classmethod
    def start(cls, path, *, study_deadline_utc, cap_seconds):
        if type(cap_seconds) is not int or not 1 <= cap_seconds <= 3600:
            raise ValueError("explicit whole-step cap required")
        try:
            study_deadline = datetime.fromisoformat(study_deadline_utc)
        except (TypeError, ValueError):
            raise ValueError("valid UTC study deadline required") from None
        if study_deadline.tzinfo is None or study_deadline.utcoffset().total_seconds() != 0:
            raise ValueError("valid UTC study deadline required")
        wall_now, mono_now = time.time(), time.monotonic()
        available = study_deadline.timestamp() - wall_now
        seconds = min(float(cap_seconds), available)
        if not math.isfinite(seconds) or seconds < cap_seconds:
            raise TimeoutError("a complete step no longer fits before the study deadline")
        deadline_monotonic = mono_now + seconds
        deadline_utc = datetime.fromtimestamp(wall_now + seconds, timezone.utc).isoformat()
        record = {"schema": "market_step_deadline_v1", "profile": PROFILE,
            "started_at_utc": datetime.fromtimestamp(wall_now, timezone.utc).isoformat(),
            "deadline_utc": deadline_utc, "cap_seconds": cap_seconds,
            "study_deadline_utc": study_deadline_utc, "renewable": False,
            "externally_active_stages": ["research", "coding", "sandbox"]}
        fresh_json(Path(path), record)
        return cls(started_monotonic=mono_now, deadline_monotonic=deadline_monotonic,
                   deadline_utc=deadline_utc, cap_seconds=cap_seconds)

    def require(self, seconds, stage):
        if (type(seconds) not in (int, float) or not math.isfinite(seconds)
                or seconds <= 0 or not isinstance(stage, str) or not stage):
            raise ValueError("positive shared-deadline allowance required")
        remaining = self.deadline_monotonic - time.monotonic()
        if remaining < seconds:
            raise TimeoutError(stage + " no longer fits inside the original step deadline")
        return remaining
