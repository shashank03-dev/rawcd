from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import Path
from typing import Callable, Iterable, Protocol

from rawcd.exporter import build_export_command, output_extension
from rawcd.ffmpeg_tools import (
    build_freezedetect_command,
    is_protected_media_error,
    MediaProbe,
    parse_ffprobe_json,
)
from rawcd.jobs import ConversionRequest
from rawcd.models import ExportProfile, FrameRange, FrameState, ProviderCapability
from rawcd.repair import FrameIssue, parse_freezedetect_output
from rawcd.repair_pipeline import RepairAction, RepairDecisionEngine, RepairGap, RepairProvider
from rawcd.timeline import FrameTimeline


class ProtectedMediaError(RuntimeError):
    pass


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        ...


class FrameRepairer(Protocol):
    def repair(
        self,
        video_path: Path,
        issues: list[FrameIssue],
        cancel_requested: Callable[[], bool],
    ) -> dict:
        ...


class SubprocessRunner:
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, capture_output=True, text=True, check=False)  # nosec B603


class MediaConverter:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        frame_repairer: FrameRepairer | None = None,
        repair_providers: Iterable[RepairProvider] | None = None,
        repair_decision_engine: RepairDecisionEngine | None = None,
    ) -> None:
        self._runner = runner or SubprocessRunner()
        self._frame_repairer = frame_repairer
        self._repair_providers = tuple(
            repair_providers
            if repair_providers is not None
            else _legacy_repair_providers(frame_repairer)
        )
        self._repair_decision_engine = repair_decision_engine or RepairDecisionEngine()

    def convert(
        self,
        request: ConversionRequest,
        cancel_requested: Callable[[], bool],
    ) -> dict:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []
        warnings: list[str] = []
        timeline_ranges: list[FrameRange] = []
        timeline_duration_seconds: float | None = None
        timeline_frame_rate: str | None = None
        repair_report = {
            "mode": "smart",
            "ai_enabled": request.ai_repair,
            "damaged_ranges": 0,
            "frames_regenerated": 0,
        }

        for source_path in request.source_paths:
            if cancel_requested():
                raise RuntimeError("conversion canceled")

            export_profile = ExportProfile.HOME_MP4
            output_path = self._unique_output_path(
                source_path,
                request.output_dir,
                outputs,
                output_extension(export_profile),
            )
            result = self._runner.run(
                build_export_command(source_path, output_path, export_profile)
            )
            if result.returncode != 0:
                self._raise_for_failure(result.stderr)

            outputs.append(output_path)

            probe = self._probe_output(output_path)
            if probe is not None:
                if probe.duration_seconds is not None:
                    timeline_duration_seconds = max(
                        timeline_duration_seconds or 0.0,
                        probe.duration_seconds,
                    )
                timeline_frame_rate = timeline_frame_rate or probe.primary_video.frame_rate

            repair_result = self._runner.run(build_freezedetect_command(output_path))
            if repair_result.returncode == 0:
                issues = parse_freezedetect_output(repair_result.stderr)
                repair_report["damaged_ranges"] += len(issues)
                if issues and not request.ai_repair:
                    timeline_ranges.extend(
                        _frame_ranges_from_issues(issues, FrameState.DAMAGED, "freezedetect")
                    )
                    warnings.append(
                        f"{output_path.name} contains {len(issues)} frozen range(s); "
                        "enable AI repair to regenerate them."
                    )
                elif issues:
                    for issue in issues:
                        decision = self._repair_decision_engine.decide(
                            _repair_gap_for_issue(issue),
                            self._repair_providers,
                        )
                        if (
                            decision.action is RepairAction.SKIPPED
                            or self._frame_repairer is None
                        ):
                            timeline_ranges.append(
                                _frame_range_from_issue(
                                    issue,
                                    FrameState.SKIPPED,
                                    "repair unavailable",
                                )
                            )
                            warnings.extend(decision.warnings)
                            if self._frame_repairer is None:
                                warnings.append(
                                    "AI repair was requested, but no repair execution adapter is configured."
                                )
                            warnings.append(
                                f"{output_path.name} has 1 skipped frame range because no repair adapter is configured."
                            )
                            continue

                        repair_result_payload = self._frame_repairer.repair(
                            output_path, [issue], cancel_requested
                        )
                        repair_report["frames_regenerated"] += int(
                            repair_result_payload.get("frames_regenerated", 0)
                        )
                        if "tool" in repair_result_payload:
                            repair_report["tool"] = repair_result_payload["tool"]
                        timeline_state = decision.output_state
                        timeline_ranges.append(
                            _frame_range_from_issue(
                                issue,
                                timeline_state,
                                decision.provider_id
                                or str(repair_result_payload.get("tool", "repair")),
                            )
                        )
                        if timeline_state is FrameState.GENERATED:
                            warnings.append(
                                f"{output_path.name} contains generated frame range(s); "
                                "the restoration report labels them separately from original frames."
                            )

        return {
            "outputs": outputs,
            "warnings": warnings,
            "report": {
                "clips": len(outputs),
                "repair": repair_report,
                "timeline": _serialize_timeline_ranges(
                    timeline_ranges,
                    duration_seconds=timeline_duration_seconds,
                    frame_rate=timeline_frame_rate,
                ),
            },
        }

    def _probe_output(self, output_path: Path) -> MediaProbe | None:
        result = self._runner.run(build_ffprobe_command(output_path))
        if result.returncode != 0:
            return None
        try:
            return parse_ffprobe_json(result.stdout)
        except Exception:
            return None

    def _raise_for_failure(self, stderr: str) -> None:
        if is_protected_media_error(stderr):
            raise ProtectedMediaError(
                "This disc appears to be protected or encrypted. RawCD v1 only "
                "supports personal, unprotected media."
            )
        raise RuntimeError(stderr.strip() or "ffmpeg failed")

    def _unique_output_path(
        self,
        source_path: Path,
        output_dir: Path,
        existing_outputs: list[Path],
        extension: str = ".mp4",
    ) -> Path:
        base = self._safe_stem(source_path.stem) or "clip"
        candidate = output_dir / f"{base}{extension}"
        index = 2
        while candidate in existing_outputs or candidate.exists():
            candidate = output_dir / f"{base}-{index}{extension}"
            index += 1
        return candidate

    def _safe_stem(self, stem: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")


def build_ffprobe_command(input_path: Path) -> list[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]


def _frame_range_from_issue(
    issue: FrameIssue,
    state: FrameState,
    reason: str,
) -> FrameRange:
    return FrameRange(
        start_seconds=issue.start_seconds,
        end_seconds=issue.end_seconds,
        state=state,
        reason=reason,
    )


def _frame_ranges_from_issues(
    issues: list[FrameIssue],
    state: FrameState,
    reason: str,
) -> list[FrameRange]:
    return [_frame_range_from_issue(issue, state, reason) for issue in issues]


def _serialize_timeline_ranges(
    ranges: list[FrameRange],
    duration_seconds: float | None,
    frame_rate: str | None,
) -> dict:
    if duration_seconds is not None and frame_rate:
        timeline = FrameTimeline.from_duration(
            duration_seconds=duration_seconds,
            frame_rate=frame_rate,
        )
        for frame_range in ranges:
            timeline.mark_range(
                frame_range.start_seconds,
                frame_range.end_seconds,
                frame_range.state,
                frame_range.reason,
            )
        summary = timeline.summary()
    else:
        summary = _range_only_timeline_summary(ranges)
    states = dict(summary["range_counts"])

    return {
        **summary,
        "states": states,
        "ranges": [
            {
                "start_seconds": frame_range.start_seconds,
                "end_seconds": frame_range.end_seconds,
                "state": frame_range.state.value,
                "reason": frame_range.reason,
            }
            for frame_range in ranges
        ],
    }


def _range_only_timeline_summary(ranges: list[FrameRange]) -> dict:
    range_counts = {state.value: 0 for state in FrameState}
    seconds = {state.value: 0.0 for state in FrameState}
    for frame_range in ranges:
        range_counts[frame_range.state.value] += 1
        seconds[frame_range.state.value] += frame_range.end_seconds - frame_range.start_seconds

    return {
        "duration_seconds": None,
        "frame_rate": None,
        "total_frames": None,
        "range_counts": range_counts,
        "frame_counts": dict(range_counts),
        "seconds": {state: round(total, 10) for state, total in seconds.items()},
    }


def _legacy_repair_providers(
    frame_repairer: FrameRepairer | None,
) -> tuple[RepairProvider, ...]:
    if frame_repairer is None:
        return ()
    return (
        RepairProvider(
            id="configured-frame-repairer",
            capabilities=frozenset(
                {
                    ProviderCapability.INTERPOLATION,
                    ProviderCapability.INPAINTING,
                }
            ),
        ),
    )


def _repair_gap_for_issue(issue: FrameIssue) -> RepairGap:
    return RepairGap(
        start_seconds=issue.start_seconds,
        end_seconds=issue.end_seconds,
        missing_frames=1,
    )
