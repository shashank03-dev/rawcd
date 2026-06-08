from pathlib import Path
from threading import Event
from time import sleep

from rawcd.jobs import ConversionRequest, JobManager, JobStatus
from rawcd.models import RecoveryMode


def test_completed_job_contains_output_paths_and_report(tmp_path: Path) -> None:
    output = tmp_path / "clip.mp4"

    def converter(request: ConversionRequest, _cancel_requested) -> dict:
        assert request.source_paths == [Path("/media/disc/VIDEO_TS/VTS_01_1.VOB")]
        return {
            "outputs": [output],
            "report": {"repair": "none-needed", "frames_regenerated": 0},
            "warnings": [],
        }

    manager = JobManager(converter=converter, run_inline=True)
    job = manager.start_conversion(
        ConversionRequest(
            source_paths=[Path("/media/disc/VIDEO_TS/VTS_01_1.VOB")],
            output_dir=tmp_path,
            ai_repair=True,
        )
    )

    status = manager.get_job_status(job.job_id)
    assert status.status is JobStatus.COMPLETED
    assert status.progress == 1.0
    assert status.stage == "completed"
    assert status.outputs == [output]
    assert status.report == {"repair": "none-needed", "frames_regenerated": 0}


def test_failed_job_records_error_message(tmp_path: Path) -> None:
    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        raise RuntimeError("ffmpeg could not read the disc")

    manager = JobManager(converter=converter, run_inline=True)
    job = manager.start_conversion(
        ConversionRequest(source_paths=[Path("/bad.vob")], output_dir=tmp_path)
    )

    status = manager.get_job_status(job.job_id)
    assert status.status is JobStatus.FAILED
    assert status.stage == "failed"
    assert status.error == "ffmpeg could not read the disc"


def test_pending_job_can_be_cancelled_before_it_starts(tmp_path: Path) -> None:
    manager = JobManager(converter=lambda *_: {}, run_inline=True)
    job = manager.create_pending_job(
        ConversionRequest(source_paths=[Path("/clip.dat")], output_dir=tmp_path)
    )

    cancelled = manager.cancel_job(job.job_id)

    status = manager.get_job_status(job.job_id)
    assert cancelled is True
    assert status.status is JobStatus.CANCELED
    assert status.stage == "canceled"


def test_job_cancelled_during_recovery_does_not_run_converter(
    tmp_path: Path,
) -> None:
    recovery_started = Event()
    recovery_returned = Event()
    release_recovery = Event()
    converter_called = False

    class BlockingRecoveryPlanner:
        def plan(self, source_path: Path, output_dir: Path, mode: RecoveryMode):
            recovery_started.set()
            release_recovery.wait(timeout=5)
            from rawcd.models import RecoveryResult

            recovery_returned.set()
            return RecoveryResult(
                input_path=source_path,
                mode=mode,
                source_path=source_path,
            )

    def converter(_request: ConversionRequest, _cancel_requested) -> dict:
        nonlocal converter_called
        converter_called = True
        return {"outputs": [], "report": {}, "warnings": []}

    manager = JobManager(
        converter=converter,
        recovery_planner=BlockingRecoveryPlanner(),
    )
    job = manager.start_conversion(
        ConversionRequest(
            source_paths=[Path("/media/disc/clip.vob")],
            output_dir=tmp_path,
            recovery_mode=RecoveryMode.MAXIMUM,
        )
    )
    assert recovery_started.wait(timeout=5)

    assert manager.cancel_job(job.job_id) is True
    immediate = manager.get_job_status(job.job_id)
    assert immediate.status is JobStatus.CANCELED
    assert immediate.stage == "canceled"
    release_recovery.set()
    assert recovery_returned.wait(timeout=5)

    for _ in range(50):
        status = manager.get_job_status(job.job_id)
        if status.status is JobStatus.FAILED:
            break
        sleep(0.05)

    status = manager.get_job_status(job.job_id)
    assert status.status is JobStatus.CANCELED
    assert status.stage == "canceled"
    assert converter_called is False


def test_job_cancelled_during_conversion_stays_cancelled(
    tmp_path: Path,
) -> None:
    converter_started = Event()

    def converter(_request: ConversionRequest, cancel_requested) -> dict:
        converter_started.set()
        for _ in range(50):
            if cancel_requested():
                raise RuntimeError("conversion canceled")
            sleep(0.05)
        return {"outputs": [], "report": {}, "warnings": []}

    manager = JobManager(converter=converter)
    job = manager.start_conversion(
        ConversionRequest(
            source_paths=[Path("/media/disc/clip.vob")],
            output_dir=tmp_path,
        )
    )
    assert converter_started.wait(timeout=5)

    assert manager.cancel_job(job.job_id) is True
    immediate = manager.get_job_status(job.job_id)
    assert immediate.status is JobStatus.CANCELED

    for _ in range(50):
        status = manager.get_job_status(job.job_id)
        if status.error is not None or status.status is JobStatus.FAILED:
            break
        if status.status is JobStatus.CANCELED:
            sleep(0.05)

    status = manager.get_job_status(job.job_id)
    assert status.status is JobStatus.CANCELED
    assert status.stage == "canceled"
    assert status.error is None
