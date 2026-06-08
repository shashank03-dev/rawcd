from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from typing import Iterable

from rawcd.models import FrameRange, FrameState


@dataclass(frozen=True)
class _FrameMark:
    state: FrameState
    reason: str


class FrameTimeline:
    def __init__(
        self,
        duration_seconds: float,
        frame_rate: str | int | float,
        known_damaged_ranges: Iterable[FrameRange] = (),
    ) -> None:
        if not isfinite(duration_seconds):
            raise ValueError("duration_seconds must be finite")
        if duration_seconds < 0:
            raise ValueError("duration_seconds must be greater than or equal to zero")

        self.duration_seconds = float(duration_seconds)
        self.frame_rate = _format_frame_rate(frame_rate)
        self._rate = _parse_frame_rate(frame_rate)
        self.total_frames = _ceil_fraction(
            Fraction(str(self.duration_seconds)) * self._rate
        )
        self._marks = [
            _FrameMark(FrameState.ORIGINAL, "") for _ in range(self.total_frames)
        ]

        for damaged_range in known_damaged_ranges:
            self.mark_range(
                damaged_range.start_seconds,
                damaged_range.end_seconds,
                damaged_range.state,
                damaged_range.reason,
            )

    @classmethod
    def from_duration(
        cls,
        duration_seconds: float,
        frame_rate: str | int | float,
        known_damaged_ranges: Iterable[FrameRange] = (),
    ) -> FrameTimeline:
        return cls(duration_seconds, frame_rate, known_damaged_ranges)

    @property
    def ranges(self) -> tuple[FrameRange, ...]:
        if not self._marks:
            return ()

        ranges: list[FrameRange] = []
        start_frame = 0
        current = self._marks[0]
        for frame_index, mark in enumerate(self._marks[1:], start=1):
            if mark != current:
                ranges.append(self._range_for_frames(start_frame, frame_index, current))
                start_frame = frame_index
                current = mark

        ranges.append(self._range_for_frames(start_frame, len(self._marks), current))
        return tuple(ranges)

    def mark_range(
        self,
        start_seconds: float,
        end_seconds: float,
        state: FrameState | str,
        reason: str = "",
    ) -> FrameTimeline:
        normalized_state = FrameState(state)
        frame_range = FrameRange(
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            state=normalized_state,
            reason=reason,
        )
        if frame_range.start_seconds == frame_range.end_seconds:
            return self

        start_frame = max(0, self._floor_seconds(frame_range.start_seconds))
        end_frame = min(self.total_frames, self._ceil_seconds(frame_range.end_seconds))
        if start_frame >= end_frame:
            return self

        mark = _FrameMark(normalized_state, frame_range.reason)
        for frame_index in range(start_frame, end_frame):
            self._marks[frame_index] = mark
        return self

    def summary(self) -> dict[str, object]:
        range_counts = _state_count_map()
        frame_counts = _state_count_map()
        seconds = {state.value: 0.0 for state in FrameState}

        for frame_mark in self._marks:
            frame_counts[frame_mark.state.value] += 1

        for frame_range in self.ranges:
            state = frame_range.state.value
            range_counts[state] += 1
            seconds[state] += frame_range.end_seconds - frame_range.start_seconds

        return {
            "duration_seconds": _round_seconds(self.duration_seconds),
            "frame_rate": self.frame_rate,
            "total_frames": self.total_frames,
            "range_counts": range_counts,
            "frame_counts": frame_counts,
            "seconds": {
                state: _round_seconds(total_seconds)
                for state, total_seconds in seconds.items()
            },
        }

    def _range_for_frames(
        self,
        start_frame: int,
        end_frame: int,
        mark: _FrameMark,
    ) -> FrameRange:
        return FrameRange(
            start_seconds=self._seconds_for_frame(start_frame),
            end_seconds=min(
                self._seconds_for_frame(end_frame),
                _round_seconds(self.duration_seconds),
            ),
            state=mark.state,
            reason=mark.reason,
        )

    def _floor_seconds(self, seconds: float) -> int:
        return int(Fraction(str(seconds)) * self._rate)

    def _ceil_seconds(self, seconds: float) -> int:
        return _ceil_fraction(Fraction(str(seconds)) * self._rate)

    def _seconds_for_frame(self, frame_index: int) -> float:
        return _round_seconds(float(Fraction(frame_index, 1) / self._rate))


def _parse_frame_rate(frame_rate: str | int | float) -> Fraction:
    try:
        rate = Fraction(str(frame_rate))
    except ValueError as exc:
        raise ValueError("frame_rate must be a positive number or fraction") from exc
    if rate <= 0:
        raise ValueError("frame_rate must be greater than zero")
    return rate


def _format_frame_rate(frame_rate: str | int | float) -> str:
    return str(frame_rate)


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _state_count_map() -> dict[str, int]:
    return {state.value: 0 for state in FrameState}


def _round_seconds(seconds: float) -> float:
    rounded = round(seconds, 10)
    if rounded == 0:
        return 0.0
    return rounded


__all__ = ["FrameTimeline"]
