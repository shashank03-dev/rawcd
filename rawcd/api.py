from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rawcd.converter import MediaConverter
from rawcd.devices import OpticalDriveScanner
from rawcd.disc import DiscClassifier, DiscInspection
from rawcd.jobs import ConversionJob, ConversionRequest, JobManager
from rawcd.models import RecoveryMode, RestoreMode
from rawcd.settings import ProviderRegistry


class InspectDiscRequest(BaseModel):
    path: str


class StartConversionRequest(BaseModel):
    source_paths: list[str]
    output_dir: str
    ai_repair: bool = False
    preserve_quality: bool = True
    recovery_mode: RecoveryMode = RecoveryMode.QUICK
    restore_mode: RestoreMode = RestoreMode.FAITHFUL


class ConfigureProviderRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    base_url: str | None = None
    executable_path: str | None = None
    extra: dict[str, Any] | None = None


def create_app(
    scanner: Any | None = None,
    classifier: DiscClassifier | None = None,
    job_manager: JobManager | None = None,
    provider_registry: ProviderRegistry | None = None,
) -> FastAPI:
    drive_scanner = scanner or OpticalDriveScanner()
    disc_classifier = classifier or DiscClassifier()
    providers = provider_registry or ProviderRegistry()
    manager = job_manager or JobManager(
        converter=MediaConverter(
            repair_providers=providers.repair_providers(),
        ).convert
    )

    app = FastAPI(title="RawCD Engine", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:1420", "http://localhost:1420"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/scan_devices")
    def scan_devices() -> list[dict[str, Any]]:
        return [asdict(device) for device in drive_scanner.scan()]

    @app.post("/inspect_disc")
    def inspect_disc(request: InspectDiscRequest) -> dict[str, Any]:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {path}")
        return _serialize_disc_inspection(disc_classifier.classify(path))

    @app.post("/start_conversion")
    def start_conversion(request: StartConversionRequest) -> dict[str, Any]:
        job = manager.start_conversion(
            ConversionRequest(
                source_paths=[Path(path).expanduser() for path in request.source_paths],
                output_dir=Path(request.output_dir).expanduser(),
                ai_repair=request.ai_repair,
                preserve_quality=request.preserve_quality,
                recovery_mode=request.recovery_mode,
                restore_mode=request.restore_mode,
            )
        )
        return _serialize_job(manager.get_job_status(job.job_id))

    @app.get("/get_job_status/{job_id}")
    def get_job_status(job_id: str) -> dict[str, Any]:
        try:
            return _serialize_job(manager.get_job_status(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/cancel_job/{job_id}")
    def cancel_job(job_id: str) -> dict[str, Any]:
        cancelled = manager.cancel_job(job_id)
        return {"cancelled": cancelled}

    @app.get("/providers")
    def list_providers() -> list[dict[str, Any]]:
        return providers.list_providers()

    @app.post("/providers/{provider_id}/test")
    def test_provider(provider_id: str) -> dict[str, Any]:
        try:
            return providers.test_provider(provider_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/providers/{provider_id}/configure")
    def configure_provider(
        provider_id: str,
        request: ConfigureProviderRequest,
    ) -> dict[str, Any]:
        try:
            return providers.configure_provider(
                provider_id,
                _model_dump_set(request),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def _serialize_disc_inspection(inspection: DiscInspection) -> dict[str, Any]:
    return {
        "disc_type": inspection.disc_type.value,
        "label": inspection.label,
        "playable_sources": [
            {
                "path": str(source.path),
                "kind": source.kind.value,
                "label": source.label,
            }
            for source in inspection.playable_sources
        ],
        "warnings": inspection.warnings,
    }


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_dump_set(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_fields_set"):
        fields_set = model.model_fields_set
    else:
        fields_set = getattr(model, "__fields_set__", set())
    payload = _model_dump(model)
    return {key: payload[key] for key in fields_set}


def _serialize_job(job: ConversionJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "stage": job.stage,
        "progress": job.progress,
        "outputs": [str(path) for path in job.outputs],
        "warnings": job.warnings,
        "recovery_warnings": job.recovery_warnings,
        "report": job.report,
        "error": job.error,
    }
