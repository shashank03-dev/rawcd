from datetime import datetime, timezone

from rawcd.models import ProProfile, ProVerificationStatus, RestoreLane
from rawcd.rights import RightsDeclaration, validate_restore_rights


def _profile(status: ProVerificationStatus) -> ProProfile:
    return ProProfile(
        name="Asha Rao",
        organization="Archive House",
        email="asha@example.test",
        country="IN",
        intended_use="Commercial film restoration",
        verification_status=status,
        approved_at=(
            datetime(2026, 6, 7, 12, 30, tzinfo=timezone.utc)
            if status is ProVerificationStatus.APPROVED
            else None
        ),
    )


def _declaration() -> RightsDeclaration:
    return RightsDeclaration(
        project_name="Restored Feature",
        organization="Archive House",
        source_title="Original Camera DVD",
        rights_basis="rights_holder",
        permission_reference="contract-2026-001",
        declared_at=datetime(2026, 6, 7, 13, 0, tzinfo=timezone.utc),
    )


def test_home_restore_refuses_protected_media() -> None:
    result = validate_restore_rights(
        lane=RestoreLane.HOME,
        protected_media=True,
    )

    assert result.allowed is False
    assert "protected" in result.reason.lower()


def test_pro_restore_requires_rights_declaration() -> None:
    result = validate_restore_rights(
        lane=RestoreLane.PRO,
        pro_profile=_profile(ProVerificationStatus.APPROVED),
    )

    assert result.allowed is False
    assert "rights declaration" in result.reason.lower()


def test_unapproved_pro_commercial_restore_is_refused() -> None:
    result = validate_restore_rights(
        lane=RestoreLane.PRO,
        pro_profile=_profile(ProVerificationStatus.PENDING),
        rights_declaration=_declaration(),
        commercial_use=True,
    )

    assert result.allowed is False
    assert "verified rights-holder access" in result.reason.lower()


def test_approved_pro_commercial_restore_with_declaration_is_allowed() -> None:
    declaration = _declaration()

    result = validate_restore_rights(
        lane=RestoreLane.PRO,
        pro_profile=_profile(ProVerificationStatus.APPROVED),
        rights_declaration=declaration,
        protected_media=True,
        commercial_use=True,
    )

    assert result.allowed is True
    assert result.reason == "Rights declaration accepted."
    assert result.declaration == declaration
