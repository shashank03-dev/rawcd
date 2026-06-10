from __future__ import annotations

import re
import subprocess  # nosec B404
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable, Protocol

from rawcd.damage import DamageDetector, DamageRange
from rawcd.exporter import (
    build_export_command,
    build_preview_image_command,
    build_wav_audio_command,
    output_extension,
)
from rawcd.ffmpeg_tools import (
    build_freezedetect_command,
    is_protected_media_error,
    MediaProbe,
    parse_ffprobe_json,
)
from rawcd.jobs import ConversionRequest
from rawcd.models import ExportProfile, FrameState, ProviderCapability
from rawcd.repair import FrameIssue, FrameIssueKind
from rawcd.repair_pipeline import (
    RepairAction,
    RepairDecision,
    RepairDecisionEngine,
    RepairGap,
    RepairProvider,
)
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


@dataclass(frozen=True)
class _TimelineRange:
    start_seconds: float
    end_seconds: float
    state: FrameState
    reason: str
    action: RepairAction | None = None
    required_capability: ProviderCapability | None = None
    provider_id: str | None = None
    preview_recommended: bool | None = None
    report_label_required: bool | None = None


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
        clips_detail: list[dict] = []
        repair_report = {
            "mode": "smart",
            "ai_enabled": request.ai_repair,
            "damaged_ranges": 0,
            "frames_regenerated": 0,
        }

        for source_index, source_path in enumerate(request.source_paths):
            if cancel_requested():
                raise RuntimeError("conversion canceled")

            export_profile = request.export_profile
            output_path = self._unique_output_path(
                source_path,
                request.output_dir,
                outputs,
                output_extension(export_profile),
            )
            _emit_preview(
                request,
                current_frame=source_index,
                current_timestamp=0.0,
                current_operation="Exporting final video",
            )
            result = self._runner.run(
                build_export_command(
                    source_path,
                    output_path,
                    export_profile,
                    restore_mode=request.restore_mode,
                )
            )
            if result.returncode != 0:
                self._raise_for_failure(result.stderr)

            outputs.append(output_path)
            preview_image_path = _try_preview_image(request, self._runner, output_path)
            if request.extract_wav_audio:
                wav_output_path = self._unique_output_path(
                    source_path,
                    request.output_dir,
                    outputs,
                    ".wav",
                )
                wav_result = self._runner.run(
                    build_wav_audio_command(source_path, wav_output_path)
                )
                if wav_result.returncode != 0:
                    self._raise_for_failure(wav_result.stderr)
                outputs.append(wav_output_path)

            probe = self._probe_output(output_path)
            clip_duration_seconds: float | None = None
            clip_frame_rate: str | None = None
            if probe is not None:
                clip_duration_seconds = probe.duration_seconds
                clip_frame_rate = probe.primary_video.frame_rate
                _emit_preview(
                    request,
                    current_frame=_frame_count_for_duration(
                        clip_duration_seconds,
                        clip_frame_rate,
                    ),
                    current_timestamp=clip_duration_seconds,
                    current_operation="Recovering original frame",
                    preview_image_path=preview_image_path,
                )

            repair_result = self._runner.run(build_freezedetect_command(output_path))
            clip_ranges: list[_TimelineRange] = []
            damage_report = _detect_damage(
                frame_rate=clip_frame_rate,
                freeze_stderr=repair_result.stderr if repair_result.returncode == 0 else "",
                ffmpeg_stderr=result.stderr,
            )
            damage_ranges = list(damage_report.ranges)
            repair_report["damaged_ranges"] += len(damage_ranges)

            if damage_ranges:
                if not request.ai_repair:
                    clip_ranges.extend(_timeline_ranges_from_damage(damage_ranges))
                    warnings.append(
                        f"{output_path.name} contains {len(damage_ranges)} damaged range(s); "
                        "enable AI repair to regenerate them."
                    )
                else:
                    for damage_range in damage_ranges:
                        issue = _frame_issue_from_damage_range(damage_range)
                        decision = self._repair_decision_engine.decide(
                            _repair_gap_for_damage_range(damage_range, clip_frame_rate),
                            self._repair_providers,
                        )

                        if self._frame_repairer is None:
                            skipped_decision = _skipped_repair_decision(decision)
                            clip_ranges.append(
                                _timeline_range_from_damage(
                                    damage_range,
                                    FrameState.SKIPPED,
                                    "repair unavailable",
                                    skipped_decision,
                                )
                            )
                            warnings.append(
                                "AI repair was requested, but no repair execution adapter is configured."
                            )
                            warnings.append(
                                f"{output_path.name} has 1 skipped frame range because no repair adapter is configured."
                            )
                            continue

                        if decision.action is RepairAction.SKIPPED:
                            clip_ranges.append(
                                _timeline_range_from_damage(
                                    damage_range,
                                    FrameState.SKIPPED,
                                    "repair unavailable",
                                    decision,
                                )
                            )
                            warnings.extend(decision.warnings)
                            if decision.required_capability is not None:
                                warnings.append(
                                    f"{output_path.name} has 1 skipped frame range because "
                                    f"no provider supports {decision.required_capability.value}."
                                )
                            else:
                                warnings.append(
                                    f"{output_path.name} has 1 skipped frame range."
                                )
                            continue

                        repair_result_payload = self._frame_repairer.repair(
                            output_path, [issue], cancel_requested
                        )
                        _emit_preview(
                            request,
                            current_frame=_frame_count_for_duration(
                                damage_range.end_seconds,
                                clip_frame_rate,
                            ),
                            current_timestamp=damage_range.end_seconds,
                            current_operation=_preview_operation_for_decision(decision),
                        )
                        repair_report["frames_regenerated"] += int(
                            repair_result_payload.get("frames_regenerated", 0)
                        )
                        if "tool" in repair_result_payload:
                            repair_report["tool"] = repair_result_payload["tool"]
                        timeline_state = decision.output_state
                        clip_ranges.append(
                            _timeline_range_from_damage(
                                damage_range,
                                timeline_state,
                                decision.provider_id
                                or str(repair_result_payload.get("tool", "repair")),
                                decision,
                            )
                        )
                        if timeline_state is FrameState.GENERATED:
                            warnings.append(
                                f"{output_path.name} contains generated frame range(s); "
                                "the restoration report labels them separately from original frames."
                            )

            clip_timeline = _serialize_timeline_ranges(
                clip_ranges,
                duration_seconds=clip_duration_seconds,
                frame_rate=clip_frame_rate,
            )
            clips_detail.append(
                {
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "timeline": clip_timeline,
                }
            )

        return {
            "outputs": outputs,
            "warnings": warnings,
            "report": {
                "clips": len(clips_detail),
                "export_profile": request.export_profile.value,
                "repair": repair_report,
                "timeline": _aggregate_timelines(
                    [clip["timeline"] for clip in clips_detail]
                ),
                "clips_detail": clips_detail,
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


def _serialize_timeline_ranges(
    ranges: list[_TimelineRange],
    duration_seconds: float | None,
    frame_rate: str | None,
) -> dict:
    if duration_seconds is not None and frame_rate:
        try:
            timeline = FrameTimeline.from_duration(
                duration_seconds=duration_seconds,
                frame_rate=frame_rate,
            )
        except (ValueError, ZeroDivisionError):
            timeline = FrameTimeline.from_duration(
                duration_seconds=duration_seconds,
                frame_rate="25/1",
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
        "ranges": [_serialize_timeline_range(frame_range) for frame_range in ranges],
    }


def _range_only_timeline_summary(ranges: list[_TimelineRange]) -> dict:
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


def _detect_damage(
    frame_rate: str | None,
    freeze_stderr: str,
    ffmpeg_stderr: str,
):
    try:
        detector = DamageDetector(frame_rate=frame_rate or "25/1")
    except (ValueError, ZeroDivisionError):
        detector = DamageDetector(frame_rate="25/1")
    return detector.detect(
        freeze_stderr=freeze_stderr,
        ffmpeg_stderr=ffmpeg_stderr,
    )


def _timeline_ranges_from_damage(
    damage_ranges: list[DamageRange],
) -> list[_TimelineRange]:
    return [
        _timeline_range_from_damage(damage_range, damage_range.state, damage_range.reason)
        for damage_range in damage_ranges
    ]


def _timeline_range_from_damage(
    damage_range: DamageRange,
    state: FrameState,
    reason: str,
    decision: RepairDecision | None = None,
) -> _TimelineRange:
    if decision is None:
        return _TimelineRange(
            start_seconds=damage_range.start_seconds,
            end_seconds=damage_range.end_seconds,
            state=state,
            reason=reason,
        )

    return _TimelineRange(
        start_seconds=damage_range.start_seconds,
        end_seconds=damage_range.end_seconds,
        state=state,
        reason=reason,
        action=decision.action,
        required_capability=decision.required_capability,
        provider_id=decision.provider_id,
        preview_recommended=decision.preview_recommended,
        report_label_required=decision.report_label_required,
    )


def _frame_issue_from_damage_range(damage_range: DamageRange) -> FrameIssue:
    return FrameIssue(
        kind=FrameIssueKind.FROZEN_RANGE,
        start_seconds=damage_range.start_seconds,
        end_seconds=damage_range.end_seconds,
        duration_seconds=damage_range.end_seconds - damage_range.start_seconds,
    )


def _repair_gap_for_damage_range(
    damage_range: DamageRange,
    frame_rate: str | None,
) -> RepairGap:
    duration_seconds = damage_range.end_seconds - damage_range.start_seconds
    return RepairGap(
        start_seconds=damage_range.start_seconds,
        end_seconds=damage_range.end_seconds,
        missing_frames=_frame_count_for_duration(duration_seconds, frame_rate),
    )


def _frame_count_for_duration(duration_seconds: float, frame_rate: str | None) -> int:
    if duration_seconds <= 0:
        return 0

    try:
        frames = Fraction(str(duration_seconds)) * _parse_frame_rate(frame_rate or "25/1")
    except (ValueError, ZeroDivisionError):
        frames = Fraction(str(duration_seconds)) * Fraction(25, 1)
    return max(1, _ceil_fraction(frames))


def _emit_preview(
    request: ConversionRequest,
    *,
    current_frame: int,
    current_timestamp: float,
    current_operation: str,
    preview_image_path: Path | None = None,
) -> None:
    if request.preview_callback is None:
        return
    request.preview_callback(
        current_frame,
        current_timestamp,
        current_operation,
        preview_image_path,
    )


def _try_preview_image(
    request: ConversionRequest,
    runner: CommandRunner,
    output_path: Path,
) -> Path | None:
    if request.preview_callback is None:
        return None
    preview_path = output_path.with_suffix(".rawcd-preview.jpg")
    result = runner.run(build_preview_image_command(output_path, preview_path))
    if result.returncode != 0 or not preview_path.exists():
        return None
    _emit_preview(
        request,
        current_frame=0,
        current_timestamp=0.0,
        current_operation="Recovering original frame",
        preview_image_path=preview_path,
    )
    return preview_path


def _preview_operation_for_decision(decision: RepairDecision) -> str:
    if decision.output_state is FrameState.INTERPOLATED:
        return "Interpolating missing frames"
    if decision.output_state is FrameState.GENERATED:
        return "AI reconstructing damaged section"
    if decision.output_state is FrameState.ENHANCED:
        return "Enhancing restored section"
    return "Recovering original frame"


def _parse_frame_rate(frame_rate: str) -> Fraction:
    rate = Fraction(str(frame_rate))
    if rate <= 0:
        raise ValueError("frame_rate must be greater than zero")
    return rate


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _skipped_repair_decision(decision: RepairDecision) -> RepairDecision:
    return RepairDecision(
        action=RepairAction.SKIPPED,
        gap=decision.gap,
        required_capability=decision.required_capability,
        provider_id=decision.provider_id,
        output_state=FrameState.SKIPPED,
        preview_recommended=decision.preview_recommended,
        report_label_required=decision.report_label_required,
        warnings=decision.warnings,
    )


def _serialize_timeline_range(frame_range: _TimelineRange) -> dict:
    payload = {
        "start_seconds": frame_range.start_seconds,
        "end_seconds": frame_range.end_seconds,
        "state": frame_range.state.value,
        "reason": frame_range.reason,
    }
    if frame_range.action is not None:
        payload.update(
            {
                "action": frame_range.action.value,
                "required_capability": (
                    frame_range.required_capability.value
                    if frame_range.required_capability is not None
                    else None
                ),
                "provider_id": frame_range.provider_id,
                "preview_recommended": bool(frame_range.preview_recommended),
                "report_label_required": bool(frame_range.report_label_required),
            }
        )
    return payload


def _aggregate_timelines(timelines: list[dict]) -> dict:
    if not timelines:
        return _serialize_timeline_ranges([], duration_seconds=None, frame_rate=None)

    range_counts = {state.value: 0 for state in FrameState}
    frame_counts = {state.value: 0 for state in FrameState}
    seconds = {state.value: 0.0 for state in FrameState}
    duration_seconds = 0.0
    total_frames = 0
    frame_rates: list[str] = []
    ranges: list[dict] = []
    all_have_duration = True
    all_have_total_frames = True

    for timeline in timelines:
        for state in range_counts:
            range_counts[state] += int(timeline["range_counts"][state])
            frame_counts[state] += int(timeline["frame_counts"][state])
            seconds[state] += float(timeline["seconds"][state])

        if timeline["duration_seconds"] is None:
            all_have_duration = False
        else:
            duration_seconds += float(timeline["duration_seconds"])

        if timeline["total_frames"] is None:
            all_have_total_frames = False
        else:
            total_frames += int(timeline["total_frames"])

        if timeline["frame_rate"] is not None:
            frame_rates.append(str(timeline["frame_rate"]))
        ranges.extend(timeline["ranges"])

    frame_rate = frame_rates[0] if frame_rates and len(set(frame_rates)) == 1 else None
    return {
        "duration_seconds": round(duration_seconds, 10) if all_have_duration else None,
        "frame_rate": frame_rate,
        "total_frames": total_frames if all_have_total_frames else None,
        "range_counts": range_counts,
        "frame_counts": frame_counts,
        "seconds": {state: round(total, 10) for state, total in seconds.items()},
        "states": dict(range_counts),
        "ranges": ranges,
    }
