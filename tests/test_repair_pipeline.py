from rawcd.models import FrameState, ProviderCapability
from rawcd.repair_pipeline import (
    RepairAction,
    RepairDecisionEngine,
    RepairGap,
    RepairProvider,
)


def test_tiny_missing_gap_auto_interpolates_when_provider_supports_it() -> None:
    decision = RepairDecisionEngine().decide(
        RepairGap(start_seconds=10.0, end_seconds=10.2, missing_frames=5),
        providers=(
            RepairProvider(
                id="rife",
                capabilities=frozenset({ProviderCapability.INTERPOLATION}),
            ),
        ),
    )

    assert decision.action is RepairAction.AUTO_INTERPOLATE
    assert decision.provider_id == "rife"
    assert decision.output_state is FrameState.INTERPOLATED
    assert decision.preview_recommended is False
    assert decision.report_label_required is False
    assert decision.warnings == ()


def test_medium_missing_gap_auto_repairs_and_recommends_preview() -> None:
    decision = RepairDecisionEngine().decide(
        RepairGap(start_seconds=20.0, end_seconds=21.0, missing_frames=25),
        providers=(
            RepairProvider(
                id="inpainter",
                capabilities=frozenset({ProviderCapability.INPAINTING}),
            ),
        ),
    )

    assert decision.action is RepairAction.AUTO_REPAIR
    assert decision.provider_id == "inpainter"
    assert decision.required_capability is ProviderCapability.INPAINTING
    assert decision.output_state is FrameState.GENERATED
    assert decision.preview_recommended is True
    assert decision.report_label_required is False
    assert decision.warnings == ()


def test_large_missing_gap_uses_creative_reconstruction_and_report_labeling() -> None:
    decision = RepairDecisionEngine().decide(
        RepairGap(start_seconds=30.0, end_seconds=33.2, missing_frames=80),
        providers=(
            RepairProvider(
                id="studio",
                capabilities=frozenset({ProviderCapability.INPAINTING}),
            ),
        ),
    )

    assert decision.action is RepairAction.CREATIVE_RECONSTRUCTION
    assert decision.provider_id == "studio"
    assert decision.output_state is FrameState.GENERATED
    assert decision.preview_recommended is True
    assert decision.report_label_required is True
    assert decision.warnings == ()


def test_more_than_48_missing_frames_requires_creative_reconstruction_even_under_two_seconds() -> None:
    decision = RepairDecisionEngine().decide(
        RepairGap(start_seconds=12.0, end_seconds=13.0, missing_frames=49),
        providers=(
            RepairProvider(
                id="studio",
                capabilities=frozenset({ProviderCapability.INPAINTING}),
            ),
        ),
    )

    assert decision.action is RepairAction.CREATIVE_RECONSTRUCTION
    assert decision.report_label_required is True


def test_missing_provider_capability_skips_with_warning() -> None:
    decision = RepairDecisionEngine().decide(
        RepairGap(start_seconds=40.0, end_seconds=40.12, missing_frames=3),
        providers=(
            RepairProvider(
                id="denoise-only",
                capabilities=frozenset({ProviderCapability.DENOISE}),
            ),
        ),
    )

    assert decision.action is RepairAction.SKIPPED
    assert decision.provider_id is None
    assert decision.required_capability is ProviderCapability.INTERPOLATION
    assert decision.output_state is FrameState.SKIPPED
    assert decision.preview_recommended is False
    assert decision.report_label_required is False
    assert decision.warnings == (
        "No provider supports interpolation; skipped repair for 3 missing frame(s).",
    )
