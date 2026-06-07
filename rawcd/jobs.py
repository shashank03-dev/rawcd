from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable, Protocol
from uuid import uuid4

from rawcd.models import RecoveryMode
from rawcd.source import SourcePlan, create_source_plan


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class ConversionRequest:
    source_paths: list[Path]
    output_dir: Path
    ai_repair: bool = False
    preserve_quality: bool = True
    recovery_mode: RecoveryMode = RecoveryMode.QUICK

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
    report: dict = field(default_factory=dict)
    error: str | None = None


class Converter(Protocol):
    def __call__(
        self,
        request: ConversionRequest,
        cancel_requested: Callable[[], bool],
    ) -> dict:
        ...


class JobManager:
    def __init__(self, converter: Converter, run_inline: bool = False) -> None:
        self._converter = converter
        self._run_inline = run_inline
        self._jobs: dict[str, ConversionJob] = {}
        self._cancel_events: dict[str, Event] = {}
        self._lock = Lock()

    def create_pending_job(self, request: ConversionRequest) -> ConversionJob:
        job = ConversionJob(job_id=uuid4().hex, request=request)
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

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancel_events.get(job_id)
            if job is None or event is None:
                return False
            if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
                return False
            event.set()
            if job.status is JobStatus.PENDING:
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
            job.stage = "converting"
            job.progress = 0.05

        try:
            result = self._converter(job.request, event.is_set)
        except Exception as exc:
            with self._lock:
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
            job.warnings = list(result.get("warnings", []))
