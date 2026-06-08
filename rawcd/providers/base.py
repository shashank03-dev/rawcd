from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Protocol
from typing import runtime_checkable

from rawcd.models import ProviderCapability
from rawcd.models import ProviderKind


class ProviderHealthStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    LICENSE_REQUIRED = "license_required"


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    kind: ProviderKind
    capabilities: tuple[ProviderCapability, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind.value,
            "capabilities": [capability.value for capability in self.capabilities],
        }


@dataclass(frozen=True)
class ProviderHealth:
    status: ProviderHealthStatus
    message: str
    details: dict[str, str] = field(default_factory=dict)

    @classmethod
    def available(
        cls,
        message: str = "available",
        details: dict[str, str] | None = None,
    ) -> ProviderHealth:
        return cls(
            status=ProviderHealthStatus.AVAILABLE,
            message=message,
            details=details or {},
        )

    @classmethod
    def unavailable(
        cls,
        message: str,
        details: dict[str, str] | None = None,
    ) -> ProviderHealth:
        return cls(
            status=ProviderHealthStatus.UNAVAILABLE,
            message=message,
            details=details or {},
        )

    @classmethod
    def degraded(
        cls,
        message: str,
        details: dict[str, str] | None = None,
    ) -> ProviderHealth:
        return cls(
            status=ProviderHealthStatus.DEGRADED,
            message=message,
            details=details or {},
        )

    @classmethod
    def license_required(
        cls,
        message: str,
        details: dict[str, str] | None = None,
    ) -> ProviderHealth:
        return cls(
            status=ProviderHealthStatus.LICENSE_REQUIRED,
            message=message,
            details=details or {},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ProviderEstimate:
    capability: ProviderCapability
    cost: str
    execution: str
    speed: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "capability": self.capability.value,
            "cost": self.cost,
            "execution": self.execution,
            "speed": self.speed,
            "notes": list(self.notes),
        }


@runtime_checkable
class EnhancementProvider(Protocol):
    id: str
    label: str
    kind: ProviderKind
    capabilities: tuple[ProviderCapability, ...]

    def health_check(self) -> ProviderHealth:
        ...

    def estimate(self, capability: ProviderCapability) -> ProviderEstimate:
        ...


__all__ = [
    "EnhancementProvider",
    "ProviderEstimate",
    "ProviderHealth",
    "ProviderHealthStatus",
    "ProviderInfo",
]
