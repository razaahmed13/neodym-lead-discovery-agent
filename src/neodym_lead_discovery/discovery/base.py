from __future__ import annotations

from pathlib import Path
from typing import Protocol

from neodym_lead_discovery.models import LeadCandidate


class DiscoverySource(Protocol):
    """Interface for raw lead candidate discovery adapters."""

    def discover(self, path: Path) -> list[LeadCandidate]:
        """Return lead candidates from a source path."""
        ...
