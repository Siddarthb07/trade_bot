"""L3 agreement — re-export supervisor helpers for stack clarity."""

from __future__ import annotations

from processor.hybrid.recognition.swarm.supervisor import decide_agreement, pick_expert

__all__ = ["decide_agreement", "pick_expert"]
