from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

from rawcd.models import RecoveryMode, RestoreSource, SourceState


@dataclass(frozen=True)
class SourcePlan:
    input_path: Path
    recovery_mode: RecoveryMode
    source: RestoreSource
    recovered_image_path: Path | None = None

    @property
    def active_path(self) -> Path:
        return self.recovered_image_path or self.source.path

    @property
    def recovery_requested(self) -> bool:
        return self.recovery_mode is RecoveryMode.MAXIMUM

    def with_recovered_image(self, image_path: Path) -> "SourcePlan":
        return replace(
            self,
            source=RestoreSource(
                path=image_path,
                state=SourceState.RECOVERED_IMAGE,
                label=self.source.label,
                recovery_mode=self.recovery_mode,
            ),
            recovered_image_path=image_path,
        )


def create_source_plan(input_path: Path, recovery_mode: RecoveryMode) -> SourcePlan:
    return SourcePlan(
        input_path=input_path,
        recovery_mode=recovery_mode,
        source=RestoreSource(
            path=input_path,
            state=SourceState.MOUNTED,
            label=input_path.name or str(input_path),
            recovery_mode=recovery_mode,
        ),
    )


__all__ = ["SourcePlan", "create_source_plan"]
