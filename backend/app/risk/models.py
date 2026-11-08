"""Typed results of each safety stage. Detection, classification, policy and response selection are separate."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskCategory = Literal["fire_smoke", "gas", "co", "electrical", "flood", "structural", "trapped", "medical", "poison",
                       "personal_safety", "self_harm"]
RISK_CATEGORIES: list[str] = list(RiskCategory.__args__)  # type: ignore[attr-defined]
RiskLevel = Literal["none", "uncertain", "urgent", "emergency"]
Framing = Literal["report", "hypothetical", "past", "joking", "quoted", "figurative", "none"]
CareKind = Literal["distress", "unwell", "danger", "info"]
ClassifierStatus = Literal["ok", "disabled", "unavailable", "timeout", "rate_limited", "error", "bad_output", "mock"]


class DeterministicRisk(BaseModel):
    """Layer 1: high-confidence rules on the message and on the recent conversation window."""

    kind: str | None = None  # hazard kind when the rules say "emergency being reported now"
    framing: Framing = "none"
    mentioned_kind: str | None = None  # hazard named but framed as hypothetical/past/joking (not an alert by itself)
    care: Literal["distress", "unwell", "danger"] | None = None  # lower tier: calm safety line
    via_window: bool = False  # only the combination of recent turns + this message matched
    self_harm_intent: bool = False  # poisoning/overdose that may be deliberate (adds the 988 line)


class SemanticRisk(BaseModel):
    """Layer 2 output contract. Anything outside it is rejected, never guessed."""

    risk_level: RiskLevel
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    immediate_danger: bool = False
    needs_human: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)
    framing: Framing = "none"
    reason: str = Field(default="", max_length=300)

    @field_validator("reason", mode="before")
    @classmethod
    def _clip(cls, v: object) -> str:
        return str(v or "")[:300]


class SemanticResult(BaseModel):
    status: ClassifierStatus
    risk: SemanticRisk | None = None
    target: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    detail: str | None = None  # error code / why it did not run (no message content)


class RiskDecision(BaseModel):
    """Layer 3: the conservative combination that the app acts on."""

    response: Literal["full_alert", "care_line", "safety_info", "none"]
    kind: str | None = None  # hazard kind for the full alert / safety info
    care: CareKind | None = None
    also_988: bool = False
    needs_human: bool = False
    escalation_priority: Literal["urgent", "high", "normal"] | None = None
    sources: list[str] = Field(default_factory=list)  # deterministic | window | semantic | policy
    rule: str  # which policy rule decided (see docs/SAFETY_EVALUATION.md)
    conflict: str | None = None  # how a disagreement between layers was resolved
    degraded: bool = False  # semantic layer did not produce a usable answer this turn


class RiskAssessment(BaseModel):
    deterministic: DeterministicRisk
    semantic: SemanticResult
    decision: RiskDecision
