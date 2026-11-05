"""Provider-agnostic decision gate: `classify(message, context) -> GateDecision`.

Rules always run. An external gate (LLM or Jev) may add risk or raise urgency, but the deterministic
safety floor in `policy.py` can never be lowered by it. See docs/GATE_DESIGN.md.
"""

from app.gates.base import GateContext, GateUnavailable
from app.gates.service import DecisionGateService

__all__ = ["DecisionGateService", "GateContext", "GateUnavailable"]
