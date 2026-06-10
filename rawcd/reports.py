from __future__ import annotations

import json
import re
from dataclasses import asdict
from dataclasses import is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence

from rawcd.models import ExportProfile
from rawcd.models import FrameRange

REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "authheader",
    "accesskey",
    "privatekey",
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(api[_ -]?key|secret|token|password|credential|authorization)\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_OPENAI_STYLE_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def write_home_report(
    report_path: Path,
    *,
    recovered_clips: int,
    output_files: Sequence[Path | str],
    damaged_sections: Sequence[FrameRange | Mapping[str, Any]] = (),
    reconstructed_sections: Sequence[FrameRange | Mapping[str, Any]] = (),
    skipped_sections: Sequence[FrameRange | Mapping[str, Any]] = (),
    provider_used: str | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    report_path = Path(report_path)
    report = {
        "recovered_clips": recovered_clips,
        "output_files": [str(output_file) for output_file in output_files],
        "damaged_sections": [_section_to_dict(section) for section in damaged_sections],
        "reconstructed_sections": [
            _section_to_dict(section) for section in reconstructed_sections
        ],
        "skipped_sections": [_section_to_dict(section) for section in skipped_sections],
        "provider_used": provider_used,
        "warnings": [_redact_string(str(warning)) for warning in warnings],
        "json_save_path": str(report_path),
    }
    _write_json(report_path, report)
    return report


def write_pro_audit_report(
    json_path: Path,
    *,
    rights_declaration: Mapping[str, Any],
    source_hash: str | None = None,
    recovery_attempts: Sequence[Any] = (),
    providers: Sequence[Any] = (),
    model_names: Sequence[str] = (),
    generated_frame_counts: Mapping[str, int] | int | None = None,
    export_profile: ExportProfile | str,
    operator_notes: str = "",
    warnings: Sequence[str] = (),
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    json_path = Path(json_path)
    markdown_path = (
        Path(markdown_path)
        if markdown_path is not None
        else json_path.with_suffix(".md")
    )
    report = {
        "rights_declaration": _redact(rights_declaration),
        "source_hash": _redact_string(source_hash) if source_hash is not None else None,
        "recovery_attempts": [_redact(attempt) for attempt in recovery_attempts],
        "providers": [_redact(provider) for provider in providers],
        "model_names": [_redact_string(str(model_name)) for model_name in model_names],
        "generated_frame_counts": _normalize_generated_frame_counts(
            generated_frame_counts
        ),
        "export_profile": ExportProfile(export_profile).value,
        "operator_notes": _redact_string(operator_notes),
        "warnings": [_redact_string(str(warning)) for warning in warnings],
        "json_save_path": str(json_path),
        "markdown_save_path": str(markdown_path),
    }
    _write_json(json_path, report)
    _write_markdown(markdown_path, report)
    return report


def _section_to_dict(section: FrameRange | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(section, FrameRange):
        return {
            "start_seconds": section.start_seconds,
            "end_seconds": section.end_seconds,
            "state": section.state.value,
            "reason": section.reason,
        }
    serialized = _serialize(section)
    if not isinstance(serialized, dict):
        raise TypeError("section must be a FrameRange or mapping")
    return _redact(serialized)


def _normalize_generated_frame_counts(
    generated_frame_counts: Mapping[str, int] | int | None,
) -> dict[str, int]:
    if generated_frame_counts is None:
        return {}
    if isinstance(generated_frame_counts, int):
        return {"generated": generated_frame_counts}
    return {str(key): int(value) for key, value in generated_frame_counts.items()}


def _serialize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, FrameRange):
        return _section_to_dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, Mapping):
        return {str(_serialize(key)): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]
    return value


def _redact(value: Any) -> Any:
    serialized = _serialize(value)
    if isinstance(serialized, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(str(key)) else _redact(item)
            for key, item in serialized.items()
        }
    if isinstance(serialized, list):
        return [_redact(item) for item in serialized]
    if isinstance(serialized, str):
        return _redact_string(serialized)
    return serialized


def _redact_string(value: str) -> str:
    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        value,
    )
    redacted = _BEARER_RE.sub(f"Bearer {REDACTED}", redacted)
    return _OPENAI_STYLE_KEY_RE.sub(REDACTED, redacted)


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _write_json(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RawCD Pro Audit Report",
        "",
        f"- Export profile: {report['export_profile']}",
        f"- Source hash: {report['source_hash'] or 'unavailable'}",
        f"- JSON report: {report['json_save_path']}",
        "",
        "## Audit Data",
        "",
        "```json",
        json.dumps(report, indent=2, sort_keys=True),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = [
    "write_home_report",
    "write_pro_audit_report",
]
