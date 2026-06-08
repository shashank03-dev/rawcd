from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable

from rawcd.models import FrameState, ProviderCapability


class RepairAction(str, Enum):
    AUTO_INTERPOLATE = "auto_interpolate"
    AUTO_REPAIR = "auto_repair"
    CREATIVE_RECONSTRUCTION = "creative_reconstruction"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RepairGap:
    start_seconds: float
    end_seconds: float
    missing_frames: int

    def __post_init__(self) -> None:
        if not isfinite(self.start_seconds) or not isfinite(self.end_seconds):
            raise ValueError("repair gap timestamps must be finite")
        if self.start_seconds < 0:
            raise ValueError("start_seconds must be greater than or equal to zero")
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be greater than or equal to start_seconds")
        if self.missing_frames < 0:
            raise ValueError("missing_frames must be greater than or equal to zero")

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class RepairProvider:
    id: str
    capabilities: frozenset[ProviderCapability]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capabilities",
            frozenset(ProviderCapability(capability) for capability in self.capabilities),
        )


@dataclass(frozen=True)
class RepairDecision:
    action: RepairAction
    gap: RepairGap
    required_capability: ProviderCapability | None
    provider_id: str | None
    output_state: FrameState
    preview_recommended: bool = False
    report_label_required: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RepairStrategy:
    action: RepairAction
    required_capability: ProviderCapability | None
    output_state: FrameState
    preview_recommended: bool
    report_label_required: bool


class RepairDecisionEngine:
    def decide(
        self,
        gap: RepairGap,
        providers: Iterable[RepairProvider],
    ) -> RepairDecision:
        strategy = self._strategy_for_gap(gap)
        if strategy.required_capability is None:
            return RepairDecision(
                action=strategy.action,
                gap=gap,
                required_capability=None,
                provider_id=None,
                output_state=strategy.output_state,
                preview_recommended=strategy.preview_recommended,
                report_label_required=strategy.report_label_required,
            )

        provider_id = _first_supporting_provider_id(
            providers,
            strategy.required_capability,
        )
        if provider_id is None:
            return RepairDecision(
                action=RepairAction.SKIPPED,
                gap=gap,
                required_capability=strategy.required_capability,
                provider_id=None,
                output_state=FrameState.SKIPPED,
                warnings=(
                    "No provider supports "
                    f"{strategy.required_capability.value}; skipped repair for "
                    f"{gap.missing_frames} missing frame(s).",
                ),
            )

        return RepairDecision(
            action=strategy.action,
            gap=gap,
            required_capability=strategy.required_capability,
            provider_id=provider_id,
            output_state=strategy.output_state,
            preview_recommended=strategy.preview_recommended,
            report_label_required=strategy.report_label_required,
        )

    def _strategy_for_gap(self, gap: RepairGap) -> _RepairStrategy:
        if gap.missing_frames == 0:
            return _RepairStrategy(
                action=RepairAction.SKIPPED,
                required_capability=None,
                output_state=FrameState.SKIPPED,
                preview_recommended=False,
                report_label_required=False,
            )

        if gap.duration_seconds > 2.0 or gap.missing_frames > 48:
            return _RepairStrategy(
                action=RepairAction.CREATIVE_RECONSTRUCTION,
                required_capability=ProviderCapability.INPAINTING,
                output_state=FrameState.GENERATED,
                preview_recommended=True,
                report_label_required=True,
            )

        if gap.missing_frames <= 5:
            return _RepairStrategy(
                action=RepairAction.AUTO_INTERPOLATE,
                required_capability=ProviderCapability.INTERPOLATION,
                output_state=FrameState.INTERPOLATED,
                preview_recommended=False,
                report_label_required=False,
            )

        return _RepairStrategy(
            action=RepairAction.AUTO_REPAIR,
            required_capability=ProviderCapability.INPAINTING,
            output_state=FrameState.GENERATED,
            preview_recommended=True,
            report_label_required=False,
        )


def _first_supporting_provider_id(
    providers: Iterable[RepairProvider],
    required_capability: ProviderCapability,
) -> str | None:
    for provider in providers:
        capabilities = {
            ProviderCapability(capability) for capability in provider.capabilities
        }
        if required_capability in capabilities:
            return provider.id
    return None


__all__ = [
    "RepairAction",
    "RepairDecision",
    "RepairDecisionEngine",
    "RepairGap",
    "RepairProvider",
]
