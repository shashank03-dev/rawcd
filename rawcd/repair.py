from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class FrameIssueKind(str, Enum):
    FROZEN_RANGE = "frozen_range"


@dataclass(frozen=True)
class FrameIssue:
    kind: FrameIssueKind
    start_seconds: float
    end_seconds: float
    duration_seconds: float


_FREEZE_LINE = re.compile(r"freeze_(start|duration|end):\s*([0-9]+(?:\.[0-9]+)?)")


def parse_freezedetect_output(
    stderr: str,
    minimum_duration: float = 0.5,
) -> list[FrameIssue]:
    issues: list[FrameIssue] = []
    current: dict[str, float] = {}

    for line in stderr.splitlines():
        match = _FREEZE_LINE.search(line)
        if match is None:
            continue
        key, value = match.groups()
        current[key] = float(value)
        if {"start", "duration", "end"} <= current.keys():
            duration = current["duration"]
            if duration >= minimum_duration:
                issues.append(
                    FrameIssue(
                        kind=FrameIssueKind.FROZEN_RANGE,
                        start_seconds=current["start"],
                        end_seconds=current["end"],
                        duration_seconds=duration,
                    )
                )
            current = {}

    return issues
