from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable, Protocol
from uuid import uuid4

from rawcd.models import (
    ExportProfile,
    FrameState,
    RecoveryMode,
    RestoreLane,
    RestoreMode,
    RightsDeclaration,
)
from rawcd.recovery import DdrescueAdapter, RecoveryPlanner, RecoveryResult
from rawcd.reports import write_home_report
from rawcd.source import SourcePlan, create_source_plan


class ConversionCanceled(RuntimeError):
    pass


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


PreviewUpdateCallback = Callable[[int, float, str, Path | None], None]


@dataclass
class JobPreview:
    job_id: str
    current_frame: int = 0
    current_timestamp: float = 0.0
    current_operation: str = "Recovering original frame"
    preview_image_path: Path | None = None


@dataclass(frozen=True)
class ConversionRequest:
    source_paths: list[Path]
    output_dir: Path
    ai_repair: bool = False
    preserve_quality: bool = True
    recovery_mode: RecoveryMode = RecoveryMode.QUICK
    restore_mode: RestoreMode = RestoreMode.FAITHFUL
    export_profile: ExportProfile = ExportProfile.HOME_MP4
    lane: RestoreLane = RestoreLane.HOME
    rights_declaration: RightsDeclaration | None = None
    protected_media: bool = False
    commercial_use: bool = False
    extract_wav_audio: bool = False
    preview_callback: PreviewUpdateCallback | None = None

    @property
    def source_plans(self) -> list[SourcePlan]:
        return [
            create_source_plan(source_path, self.recovery_mode)
            for source_path in self.source_paths
        ]


@dataclass
class ConversionJob:
    job_id: str
    request: ConversionRequest
    status: JobStatus = JobStatus.PENDING
    stage: str = "pending"
    progress: float = 0.0
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recovery_warnings: list[str] = field(default_factory=list)
    report: dict = field(default_factory=dict)
    error: str | None = None
    preview: JobPreview | None = None


class Converter(Protocol):
    def __call__(
        self,
        request: ConversionRequest,
        cancel_requested: Callable[[], bool],
    ) -> dict:
        ...


class JobManager:
    def __init__(
        self,
        converter: Converter,
        run_inline: bool = False,
        recovery_planner: RecoveryPlanner | None = None,
    ) -> None:
        self._converter = converter
        self._run_inline = run_inline
        self._recovery_planner = recovery_planner or RecoveryPlanner(
            rescue_adapter=DdrescueAdapter()
        )
        self._jobs: dict[str, ConversionJob] = {}
        self._cancel_events: dict[str, Event] = {}
        self._lock = Lock()

    def create_pending_job(self, request: ConversionRequest) -> ConversionJob:
        job_id = uuid4().hex
        job = ConversionJob(
            job_id=job_id,
            request=request,
            preview=JobPreview(job_id=job_id),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._cancel_events[job.job_id] = Event()
        return job

    def start_conversion(self, request: ConversionRequest) -> ConversionJob:
        job = self.create_pending_job(request)
        if self._run_inline:
            self._run_job(job.job_id)
        else:
            Thread(target=self._run_job, args=(job.job_id,), daemon=True).start()
        return job

    def get_job_status(self, job_id: str) -> ConversionJob:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown job id: {job_id}")
            return self._jobs[job_id]

    def get_job_preview(self, job_id: str) -> JobPreview:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown job id: {job_id}")
            job = self._jobs[job_id]
            return job.preview or JobPreview(job_id=job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancel_events.get(job_id)
            if job is None or event is None:
                return False
            if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
                return False
            event.set()
            job.status = JobStatus.CANCELED
            job.stage = "canceled"
            job.progress = 0.0
            return True

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            event = self._cancel_events[job_id]
            if event.is_set():
                job.status = JobStatus.CANCELED
                job.stage = "canceled"
                return
            job.status = JobStatus.RUNNING
            job.stage = "recovering"
            job.progress = 0.05
            job.preview = JobPreview(
                job_id=job.job_id,
                current_operation="Recovering original frame",
            )

        try:
            recovery_results = self._plan_recovery(job.request, event.is_set)
            recovery_warnings = [
                warning
                for recovery_result in recovery_results
                for warning in recovery_result.warnings
            ]
            with self._lock:
                if event.is_set():
                    raise ConversionCanceled("conversion canceled")
                job.recovery_warnings = recovery_warnings
                job.warnings = list(recovery_warnings)
                job.stage = "converting"
                job.progress = 0.2
                job.preview = JobPreview(
                    job_id=job.job_id,
                    current_operation="Exporting final video",
                )
            recovered_request = replace(
                job.request,
                source_paths=[
                    recovery_result.source_path
                    for recovery_result in recovery_results
                ],
                preview_callback=self._preview_callback(job.job_id),
            )
            result = self._converter(recovered_request, event.is_set)
        except ConversionCanceled:
            with self._lock:
                job.status = JobStatus.CANCELED
                job.stage = "canceled"
                job.progress = 0.0
            return
        except Exception as exc:
            with self._lock:
                if event.is_set():
                    job.status = JobStatus.CANCELED
                    job.stage = "canceled"
                    job.progress = 0.0
                    return
                job.status = JobStatus.FAILED
                job.stage = "failed"
                job.error = str(exc)
            return

        with self._lock:
            if event.is_set():
                job.status = JobStatus.CANCELED
                job.stage = "canceled"
                return
            job.status = JobStatus.COMPLETED
            job.stage = "completed"
            job.progress = 1.0
            job.outputs = [Path(path) for path in result.get("outputs", [])]
            job.report = dict(result.get("report", {}))
            job.warnings = list(job.recovery_warnings) + list(result.get("warnings", []))
            if job.request.lane is RestoreLane.HOME:
                self._write_home_report(job)
            job.preview = self._preview_from_report(job)

    def _plan_recovery(
        self,
        request: ConversionRequest,
        cancel_requested: Callable[[], bool],
    ) -> list[RecoveryResult]:
        results: list[RecoveryResult] = []
        for source_path in request.source_paths:
            if cancel_requested():
                raise ConversionCanceled("conversion canceled")
            results.append(
                self._recovery_planner.plan(
                    source_path,
                    request.output_dir,
                    request.recovery_mode,
                )
            )
            if cancel_requested():
                raise ConversionCanceled("conversion canceled")
        return results

    def _preview_callback(self, job_id: str) -> PreviewUpdateCallback:
        def update(
            current_frame: int,
            current_timestamp: float,
            current_operation: str,
            preview_image_path: Path | None = None,
        ) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status is not JobStatus.RUNNING:
                    return
                job.preview = JobPreview(
                    job_id=job_id,
                    current_frame=max(0, current_frame),
                    current_timestamp=max(0.0, current_timestamp),
                    current_operation=current_operation,
                    preview_image_path=preview_image_path,
                )

        return update

    def _preview_from_report(self, job: ConversionJob) -> JobPreview:
        timeline = job.report.get("timeline", {})
        total_frames = 0
        current_timestamp = 0.0
        if isinstance(timeline, dict):
            total_frames = int(timeline.get("total_frames") or 0)
            current_timestamp = float(timeline.get("duration_seconds") or 0.0)
        return JobPreview(
            job_id=job.job_id,
            current_frame=total_frames,
            current_timestamp=current_timestamp,
            current_operation="Exporting final video",
        )

    def _write_home_report(self, job: ConversionJob) -> None:
        if not job.outputs:
            return
        report_path = _home_report_path(job.outputs[0])
        timeline = job.report.get("timeline", {})
        ranges = timeline.get("ranges", []) if isinstance(timeline, dict) else []
        if not isinstance(ranges, list):
            ranges = []
        damaged_sections = [
            item for item in ranges if _range_state(item) in {"damaged", "missing"}
        ]
        reconstructed_sections = [
            item
            for item in ranges
            if _range_state(item) in {"interpolated", "generated", "enhanced"}
        ]
        skipped_sections = [item for item in ranges if _range_state(item) == "skipped"]
        repair = job.report.get("repair", {})
        provider_used = None
        if isinstance(repair, dict):
            provider_used = repair.get("tool") or repair.get("provider_id")
        report = write_home_report(
            report_path,
            recovered_clips=int(job.report.get("clips", len(job.outputs)) or 0),
            output_files=job.outputs,
            damaged_sections=damaged_sections,
            reconstructed_sections=reconstructed_sections,
            skipped_sections=skipped_sections,
            provider_used=str(provider_used) if provider_used else None,
            warnings=job.warnings,
        )
        job.report["home_report"] = report


def _home_report_path(output_path: Path) -> Path:
    return output_path.with_suffix(".rawcd-home-report.json")


def _range_state(item: object) -> str:
    if not isinstance(item, dict):
        return FrameState.ORIGINAL.value
    return str(item.get("state", FrameState.ORIGINAL.value))
