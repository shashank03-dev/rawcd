from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from rawcd.converter import MediaConverter
from rawcd.devices import OpticalDriveScanner
from rawcd.disc import DiscClassifier, DiscInspection, DiscType
from rawcd.jobs import ConversionJob, ConversionRequest, JobManager, JobStatus
from rawcd.models import (
    ExportProfile,
    ProProfile,
    ProVerificationStatus,
    RecoveryMode,
    RestoreLane,
    RestoreMode,
    RightsDeclaration,
)
from rawcd.reports import write_home_report, write_pro_audit_report
from rawcd.rights import validate_restore_rights
from rawcd.settings import ProProfileSettingsStore, ProviderRegistry


class InspectDiscRequest(BaseModel):
    path: str


class ConfigureProviderRequest(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    base_url: str | None = None
    executable_path: str | None = None
    extra: dict[str, Any] | None = None


class ProProfileRequest(BaseModel):
    name: str = ""
    organization: str = ""
    email: str = ""
    country: str = ""
    intended_use: str = ""
    verification_status: ProVerificationStatus = ProVerificationStatus.NOT_REQUESTED
    approved_at: datetime | None = None
    server_verification_id: str | None = None


class ProVerificationUpdateRequest(BaseModel):
    verification_token: str
    verification_status: ProVerificationStatus
    server_verification_id: str
    approved_at: datetime | None = None


class RightsDeclarationRequest(BaseModel):
    project_name: str
    organization: str
    source_title: str
    rights_basis: str
    permission_reference: str
    declared_at: datetime | None = None


class StartConversionRequest(BaseModel):
    source_paths: list[str]
    output_dir: str
    ai_repair: bool = False
    preserve_quality: bool = True
    recovery_mode: RecoveryMode = RecoveryMode.QUICK
    restore_mode: RestoreMode = RestoreMode.FAITHFUL
    export_profile: ExportProfile = ExportProfile.HOME_MP4
    lane: RestoreLane = RestoreLane.HOME
    rights_declaration: RightsDeclarationRequest | None = None
    protected_media: bool = False
    commercial_use: bool = False
    extract_wav_audio: bool = False


class ValidateRightsRequest(BaseModel):
    lane: RestoreLane
    rights_declaration: RightsDeclarationRequest | None = None
    protected_media: bool = False
    commercial_use: bool = False


class HomeReportRequest(BaseModel):
    report_path: str
    recovered_clips: int
    output_files: list[str]
    damaged_sections: list[dict[str, Any]] = []
    reconstructed_sections: list[dict[str, Any]] = []
    skipped_sections: list[dict[str, Any]] = []
    provider_used: str | None = None
    warnings: list[str] = []


class ProAuditReportRequest(BaseModel):
    job_id: str
    json_path: str
    operator_notes: str = ""
    warnings: list[str] = []
    markdown_path: str | None = None


def create_app(
    scanner: Any | None = None,
    classifier: DiscClassifier | None = None,
    job_manager: JobManager | None = None,
    provider_registry: ProviderRegistry | None = None,
) -> FastAPI:
    drive_scanner = scanner or OpticalDriveScanner()
    disc_classifier = classifier or DiscClassifier()
    providers = provider_registry or ProviderRegistry()
    pro_profiles = ProProfileSettingsStore(providers.settings_store.path)
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
        lane = _effective_lane(request.lane, request.export_profile)
        protected_media = request.protected_media or _source_paths_include_protected_media(
            disc_classifier,
            [Path(path).expanduser() for path in request.source_paths],
        )
        declaration = (
            _rights_declaration_from_request(request.rights_declaration)
            if request.rights_declaration is not None
            else None
        )
        rights_result = validate_restore_rights(
            lane=lane,
            pro_profile=pro_profiles.get(),
            rights_declaration=declaration,
            protected_media=protected_media,
            commercial_use=request.commercial_use or lane is RestoreLane.PRO,
        )
        if not rights_result.allowed:
            raise HTTPException(status_code=403, detail=rights_result.reason)

        job = manager.start_conversion(
            ConversionRequest(
                source_paths=[Path(path).expanduser() for path in request.source_paths],
                output_dir=Path(request.output_dir).expanduser(),
                ai_repair=request.ai_repair,
                preserve_quality=request.preserve_quality,
                recovery_mode=request.recovery_mode,
                restore_mode=request.restore_mode,
                export_profile=request.export_profile,
                lane=lane,
                rights_declaration=rights_result.declaration,
                protected_media=protected_media,
                commercial_use=request.commercial_use or lane is RestoreLane.PRO,
                extract_wav_audio=request.extract_wav_audio,
            )
        )
        return _serialize_job(manager.get_job_status(job.job_id))

    @app.get("/get_job_status/{job_id}")
    def get_job_status(job_id: str) -> dict[str, Any]:
        try:
            return _serialize_job(manager.get_job_status(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/get_job_preview/{job_id}")
    def get_job_preview(job_id: str) -> dict[str, Any]:
        try:
            return _serialize_job_preview(manager.get_job_preview(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/preview_image/{job_id}")
    def preview_image(job_id: str) -> FileResponse:
        try:
            preview = manager.get_job_preview(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if preview.preview_image_path is None or not preview.preview_image_path.exists():
            raise HTTPException(status_code=404, detail="Preview image is unavailable.")
        return FileResponse(preview.preview_image_path, media_type="image/jpeg")

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

    @app.get("/pro/profile")
    def get_pro_profile() -> dict[str, Any]:
        profile = pro_profiles.get()
        return _serialize_pro_profile(profile)

    @app.post("/pro/profile")
    def save_pro_profile(request: ProProfileRequest) -> dict[str, Any]:
        verification_status = (
            ProVerificationStatus.PENDING
            if any(
                value.strip()
                for value in (
                    request.name,
                    request.organization,
                    request.email,
                    request.country,
                    request.intended_use,
                )
            )
            else ProVerificationStatus.NOT_REQUESTED
        )
        profile = ProProfile(
            name=request.name,
            organization=request.organization,
            email=request.email,
            country=request.country,
            intended_use=request.intended_use,
            verification_status=verification_status,
            approved_at=None,
            server_verification_id=None,
        )
        return _serialize_pro_profile(pro_profiles.save(profile))

    @app.post("/pro/profile/verification")
    def update_pro_verification(
        request: ProVerificationUpdateRequest,
    ) -> dict[str, Any]:
        configured_token = os.environ.get("RAWCD_PRO_VERIFICATION_TOKEN")
        if not configured_token:
            raise HTTPException(
                status_code=403,
                detail="Pro verification updates are not configured.",
            )
        if request.verification_token != configured_token:
            raise HTTPException(status_code=403, detail="Invalid verification token.")
        if (
            request.verification_status is ProVerificationStatus.APPROVED
            and not request.server_verification_id.strip()
        ):
            raise HTTPException(
                status_code=400,
                detail="Approved Pro verification requires a server verification id.",
            )

        current = pro_profiles.get()
        if current is None or not _pro_profile_complete(current):
            raise HTTPException(
                status_code=400,
                detail="A complete Pro profile is required before verification approval.",
            )
        approved_at = (
            request.approved_at
            if request.approved_at is not None
            else datetime.now(timezone.utc)
        )
        profile = ProProfile(
            name=current.name,
            organization=current.organization,
            email=current.email,
            country=current.country,
            intended_use=current.intended_use,
            verification_status=request.verification_status,
            approved_at=(
                approved_at
                if request.verification_status is ProVerificationStatus.APPROVED
                else None
            ),
            server_verification_id=request.server_verification_id,
        )
        return _serialize_pro_profile(pro_profiles.save(profile))

    @app.post("/rights/validate")
    def validate_rights(request: ValidateRightsRequest) -> dict[str, Any]:
        declaration = (
            _rights_declaration_from_request(request.rights_declaration)
            if request.rights_declaration is not None
            else None
        )
        result = validate_restore_rights(
            lane=request.lane,
            pro_profile=pro_profiles.get(),
            rights_declaration=declaration,
            protected_media=request.protected_media,
            commercial_use=request.commercial_use,
        )
        return {
            "allowed": result.allowed,
            "reason": result.reason,
            "declaration": (
                _serialize_rights_declaration(result.declaration)
                if result.declaration is not None
                else None
            ),
        }

    @app.post("/reports/home")
    def create_home_report(request: HomeReportRequest) -> dict[str, Any]:
        return write_home_report(
            Path(request.report_path).expanduser(),
            recovered_clips=request.recovered_clips,
            output_files=[Path(path).expanduser() for path in request.output_files],
            damaged_sections=request.damaged_sections,
            reconstructed_sections=request.reconstructed_sections,
            skipped_sections=request.skipped_sections,
            provider_used=request.provider_used,
            warnings=request.warnings,
        )

    @app.post("/reports/pro")
    def create_pro_audit_report(request: ProAuditReportRequest) -> dict[str, Any]:
        try:
            job = manager.get_job_status(request.job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if job.status is not JobStatus.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail="Pro audit reports can only be written for completed jobs.",
            )
        if job.request.lane is not RestoreLane.PRO:
            raise HTTPException(
                status_code=403,
                detail="Pro audit reports require a Pro restore job.",
            )
        if job.request.rights_declaration is None:
            raise HTTPException(
                status_code=403,
                detail="Pro audit reports require a rights declaration.",
            )

        return write_pro_audit_report(
            Path(request.json_path).expanduser(),
            rights_declaration=_serialize_rights_declaration(job.request.rights_declaration),
            source_hash=_job_source_hash(job),
            recovery_attempts=_pro_recovery_attempts(job),
            providers=_pro_providers(job),
            model_names=_pro_model_names(job),
            generated_frame_counts=_generated_frame_counts(job),
            export_profile=job.request.export_profile,
            operator_notes=request.operator_notes,
            warnings=[*job.warnings, *request.warnings],
            markdown_path=(
                Path(request.markdown_path).expanduser()
                if request.markdown_path is not None
                else None
            ),
        )

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


def _effective_lane(lane: RestoreLane, export_profile: ExportProfile) -> RestoreLane:
    if export_profile is not ExportProfile.HOME_MP4:
        return RestoreLane.PRO
    return lane


def _source_paths_include_protected_media(
    classifier: DiscClassifier,
    source_paths: list[Path],
) -> bool:
    for source_path in source_paths:
        inspection_root = _inspection_root_for_source(source_path)
        if inspection_root is None:
            continue
        try:
            if classifier.classify(inspection_root).disc_type is DiscType.PROTECTED_MEDIA:
                return True
        except OSError:
            continue
    return False


def _inspection_root_for_source(source_path: Path) -> Path | None:
    if not source_path.exists():
        return None
    if source_path.is_dir():
        return source_path
    if source_path.parent.name.upper() in {"VIDEO_TS", "MPEGAV", "MPEG2"}:
        return source_path.parent.parent
    return source_path.parent


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


def _serialize_job_preview(preview: Any) -> dict[str, Any]:
    return {
        "job_id": preview.job_id,
        "current_frame": preview.current_frame,
        "current_timestamp": preview.current_timestamp,
        "current_operation": preview.current_operation,
        "preview_image_path": (
            f"http://127.0.0.1:8765/preview_image/{preview.job_id}"
            if preview.preview_image_path is not None
            else None
        ),
    }


def _serialize_pro_profile(profile: ProProfile | None) -> dict[str, Any]:
    if profile is None:
        return {
            "name": "",
            "organization": "",
            "email": "",
            "country": "",
            "intended_use": "",
            "verification_status": ProVerificationStatus.NOT_REQUESTED.value,
            "approved_at": None,
            "server_verification_id": None,
            "can_enable_pro_projects": False,
        }
    return {
        "name": profile.name,
        "organization": profile.organization,
        "email": profile.email,
        "country": profile.country,
        "intended_use": profile.intended_use,
        "verification_status": profile.verification_status.value,
        "approved_at": profile.approved_at.isoformat()
        if profile.approved_at is not None
        else None,
        "server_verification_id": profile.server_verification_id,
        "can_enable_pro_projects": (
            profile.verification_status is ProVerificationStatus.APPROVED
        ),
    }


def _pro_profile_complete(profile: ProProfile) -> bool:
    return all(
        value.strip()
        for value in (
            profile.name,
            profile.organization,
            profile.email,
            profile.country,
            profile.intended_use,
        )
    )


def _rights_declaration_from_request(
    request: RightsDeclarationRequest,
) -> RightsDeclaration:
    return RightsDeclaration(
        project_name=request.project_name,
        organization=request.organization,
        source_title=request.source_title,
        rights_basis=request.rights_basis,
        permission_reference=request.permission_reference,
        declared_at=request.declared_at
        if request.declared_at is not None
        else datetime.now(timezone.utc),
    )


def _serialize_rights_declaration(
    declaration: RightsDeclaration,
) -> dict[str, Any]:
    return {
        "project_name": declaration.project_name,
        "organization": declaration.organization,
        "source_title": declaration.source_title,
        "rights_basis": declaration.rights_basis,
        "permission_reference": declaration.permission_reference,
        "declared_at": declaration.declared_at.isoformat(),
    }


def _generated_frame_counts(job: ConversionJob) -> dict[str, int]:
    timeline = job.report.get("timeline", {})
    frame_counts = timeline.get("frame_counts", {}) if isinstance(timeline, dict) else {}
    if not isinstance(frame_counts, dict):
        return {}
    return {
        state: int(frame_counts.get(state, 0) or 0)
        for state in ("generated", "interpolated", "enhanced")
    }


def _pro_providers(job: ConversionJob) -> list[Any]:
    providers: list[Any] = []
    seen: set[str] = set()
    repair = job.report.get("repair", {})
    if isinstance(repair, dict):
        for key in ("provider_id", "tool"):
            provider_id = repair.get(key)
            if provider_id and str(provider_id) not in seen:
                providers.append({"provider_id": str(provider_id), "source": "job_repair"})
                seen.add(str(provider_id))
    timeline = job.report.get("timeline", {})
    ranges = timeline.get("ranges", []) if isinstance(timeline, dict) else []
    if isinstance(ranges, list):
        for frame_range in ranges:
            if not isinstance(frame_range, dict):
                continue
            provider_id = frame_range.get("provider_id")
            if provider_id and str(provider_id) not in seen:
                providers.append(
                    {"provider_id": str(provider_id), "source": "timeline_range"}
                )
                seen.add(str(provider_id))
    return providers


def _pro_recovery_attempts(job: ConversionJob) -> list[Any]:
    return [
        {
            "mode": job.request.recovery_mode.value,
            "warnings": job.recovery_warnings,
        }
    ]


def _pro_model_names(job: ConversionJob) -> list[str]:
    model_names: list[str] = []
    repair = job.report.get("repair", {})
    if isinstance(repair, dict) and repair.get("model_name"):
        model_names.append(str(repair["model_name"]))
    return model_names


def _job_source_hash(job: ConversionJob) -> str | None:
    existing_sources = [path for path in job.request.source_paths if path.is_file()]
    if not existing_sources:
        return None
    digest = sha256()
    for source_path in sorted(existing_sources):
        digest.update(str(source_path).encode("utf-8"))
        with source_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
