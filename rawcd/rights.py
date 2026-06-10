from __future__ import annotations

from dataclasses import dataclass

from rawcd.models import ProProfile, RestoreLane, RightsDeclaration
from rawcd.settings import pro_projects_enabled


@dataclass(frozen=True)
class RightsValidationResult:
    allowed: bool
    reason: str
    declaration: RightsDeclaration | None = None


def validate_restore_rights(
    *,
    lane: RestoreLane,
    pro_profile: ProProfile | None = None,
    rights_declaration: RightsDeclaration | None = None,
    protected_media: bool = False,
    commercial_use: bool = False,
) -> RightsValidationResult:
    if lane is RestoreLane.HOME:
        if protected_media:
            return RightsValidationResult(
                allowed=False,
                reason=(
                    "This disc appears protected. RawCD restores personal media "
                    "and cannot process protected commercial discs."
                ),
            )
        return RightsValidationResult(
            allowed=True,
            reason="Home restore accepted.",
        )

    if rights_declaration is None:
        return RightsValidationResult(
            allowed=False,
            reason="A rights declaration is required for Pro restore projects.",
        )

    if not _rights_declaration_complete(rights_declaration):
        return RightsValidationResult(
            allowed=False,
            reason="A complete rights declaration is required for Pro restore projects.",
        )

    if not pro_projects_enabled(pro_profile):
        reason = (
            "Commercial restoration requires verified rights-holder access."
            if commercial_use
            else "Pro restoration requires approved verification status."
        )
        return RightsValidationResult(
            allowed=False,
            reason=reason,
            declaration=rights_declaration,
        )

    return RightsValidationResult(
        allowed=True,
        reason="Rights declaration accepted.",
        declaration=rights_declaration,
    )


def _rights_declaration_complete(declaration: RightsDeclaration) -> bool:
    return all(
        value.strip()
        for value in (
            declaration.project_name,
            declaration.organization,
            declaration.source_title,
            declaration.rights_basis,
            declaration.permission_reference,
        )
    )


__all__ = [
    "RightsDeclaration",
    "RightsValidationResult",
    "validate_restore_rights",
]
