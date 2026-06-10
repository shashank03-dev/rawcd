import json
from pathlib import Path

from rawcd.models import ExportProfile, FrameRange, FrameState, ProviderKind
from rawcd.reports import write_home_report, write_pro_audit_report


def test_home_report_saves_required_summary_fields(tmp_path: Path) -> None:
    report_path = tmp_path / "restore-report.json"

    report = write_home_report(
        report_path,
        recovered_clips=2,
        output_files=(tmp_path / "clip-1.mp4", tmp_path / "clip-2.mp4"),
        damaged_sections=(
            FrameRange(10.0, 12.5, FrameState.DAMAGED, "freeze detected"),
        ),
        reconstructed_sections=(
            FrameRange(12.5, 13.0, FrameState.INTERPOLATED, "rife"),
        ),
        skipped_sections=(
            FrameRange(44.0, 45.0, FrameState.SKIPPED, "unreadable"),
        ),
        provider_used="open_local",
        warnings=("One unreadable section was skipped.",),
    )

    assert report == {
        "recovered_clips": 2,
        "output_files": [str(tmp_path / "clip-1.mp4"), str(tmp_path / "clip-2.mp4")],
        "damaged_sections": [
            {
                "start_seconds": 10.0,
                "end_seconds": 12.5,
                "state": "damaged",
                "reason": "freeze detected",
            }
        ],
        "reconstructed_sections": [
            {
                "start_seconds": 12.5,
                "end_seconds": 13.0,
                "state": "interpolated",
                "reason": "rife",
            }
        ],
        "skipped_sections": [
            {
                "start_seconds": 44.0,
                "end_seconds": 45.0,
                "state": "skipped",
                "reason": "unreadable",
            }
        ],
        "provider_used": "open_local",
        "warnings": ["One unreadable section was skipped."],
        "json_save_path": str(report_path),
    }
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_pro_audit_report_saves_json_and_markdown_with_redaction(
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "audit.json"
    markdown_path = tmp_path / "audit.md"

    report = write_pro_audit_report(
        json_path,
        markdown_path=markdown_path,
        rights_declaration={
            "project_name": "Archive Film",
            "organization": "RawCD Studio",
            "rights_basis": "Rights holder restoration",
            "permission_reference": "contract-2026-06",
        },
        source_hash="sha256:abc123",
        recovery_attempts=(
            {
                "tool": "ddrescue",
                "retry_count": 3,
                "returncode": 0,
                "api_key": "should-not-leak",
            },
        ),
        providers=(
            {
                "id": "topaz",
                "kind": ProviderKind.TOPAZ,
                "model_name": "Proteus",
                "secret": "topaz-secret",
            },
            {
                "id": "cloud-inpaint",
                "kind": "cloud",
                "models": ["vision-repair-v1"],
                "token": "cloud-token",
            },
        ),
        model_names=("Proteus", "vision-repair-v1"),
        generated_frame_counts={"generated": 14, "interpolated": 8},
        export_profile=ExportProfile.PRORES_422_HQ,
        operator_notes="Approved source. api_key=operator-note-secret",
        warnings=("Provider token=warning-secret was redacted.",),
    )

    assert report["rights_declaration"]["project_name"] == "Archive Film"
    assert report["source_hash"] == "sha256:abc123"
    assert report["recovery_attempts"][0]["api_key"] == "[REDACTED]"
    assert report["providers"][0]["secret"] == "[REDACTED]"
    assert report["providers"][1]["token"] == "[REDACTED]"
    assert report["model_names"] == ["Proteus", "vision-repair-v1"]
    assert report["generated_frame_counts"] == {"generated": 14, "interpolated": 8}
    assert report["export_profile"] == "prores_422_hq"
    assert report["operator_notes"] == "Approved source. api_key=[REDACTED]"
    assert report["warnings"] == ["Provider token=[REDACTED] was redacted."]
    assert report["json_save_path"] == str(json_path)
    assert report["markdown_save_path"] == str(markdown_path)

    saved_json = json_path.read_text(encoding="utf-8")
    saved_markdown = markdown_path.read_text(encoding="utf-8")
    assert "should-not-leak" not in saved_json
    assert "topaz-secret" not in saved_json
    assert "cloud-token" not in saved_json
    assert "operator-note-secret" not in saved_json
    assert "warning-secret" not in saved_markdown
    assert "prores_422_hq" in saved_markdown
