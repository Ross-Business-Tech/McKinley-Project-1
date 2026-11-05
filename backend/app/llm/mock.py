"""Deterministic mock provider for development and tests.

Output is rule-based template text, NOT a language model. Every result is flagged `is_mock=True` and the UI
labels it MOCK; mock results must never be reported as model quality evidence.
"""

import hashlib
import json
import re
from typing import Any

from app.llm.base import GenerationConfig, LLMResult, ModelOutput, Target


def _last_user(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _ctx_value(text: str, name: str) -> str | None:
    m = re.search(rf"^{re.escape(name)}: (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


class MockProvider:
    name = "mock"

    def complete(self, system: str, messages: list[dict[str, str]], target: Target,
                 cfg: GenerationConfig, schema: dict[str, Any] | None = None,
                 schema_name: str = "mckinley_reply") -> LLMResult:
        turn = _last_user(messages)
        if schema_name == "mckinley_gate":
            return self._gate(turn, target)
        msg_match = re.search(r"<customer_message>\s*(.*?)\s*</customer_message>", turn, re.DOTALL)
        msg = (msg_match.group(1) if msg_match else turn).lower()
        audience = _ctx_value(turn, "audience") or (
            "resident" if re.search(r"\bmy (ac|faucet|sink|lease|renewal|unit|apartment)\b", msg) else
            "prospect" if re.search(r"tour|move|cheapest|available|apartment", msg) else "unknown"
        )
        has_history = "repeat_issue_flag:" in turn
        handoff, category, reason = False, "none", ""

        if re.search(r"gas|fire|flood|sparks|smoke", msg):
            reply = ("Your safety comes first. Please move to a safe place and call 911 or your community's "
                     "emergency maintenance line now. I can't dispatch anyone from this demo.")
            handoff, category, reason = True, "safety_emergency", "Possible hazard reported"
        elif audience == "prospect":
            reply = ("Thanks for reaching out! I'd be glad to help you explore floor plans and beds options. "
                     "I don't have live pricing or availability in this demo, but a leasing specialist can "
                     "confirm current options. Which city or community are you most interested in?")
            handoff, category, reason = True, "leasing_follow_up", "Leasing team to confirm availability"
        elif re.search(r"renew|lease|cost", msg):
            reply = ("I understand renewal decisions can feel stressful. I can't confirm pricing in this demo, "
                     "but I recommend your leasing team review your options with you"
                     + (", by text as you prefer" if _ctx_value(turn, "preferred_contact_channel") == "text"
                        else "") + ". Would a written summary help?")
            handoff, category, reason = True, "financial_or_lease", "Renewal options need staff review"
        elif has_history:
            reply = ("I'm sorry this is happening again. I can see related requests on record, so this should "
                     "be reviewed by your community team rather than filed as another routine request. I can't "
                     "contact them from this demo, but I recommend a prompt handoff.")
            handoff, category, reason = True, "repeat_issue", "Repeated related maintenance requests"
        else:
            reply = ("Sorry you're dealing with that. For now, only do simple safe checks, and please contact "
                     "your community's maintenance team if it continues. Is anything else affected?")

        digest = hashlib.sha256(f"{system}|{turn}".encode()).hexdigest()
        return LLMResult(
            output=ModelOutput(reply=reply, audience=audience if audience in ("prospect", "resident") else
                               "unknown", recommended_handoff=handoff, handoff_category=category,  # type: ignore[arg-type]
                               handoff_reason=reason, language="English"),
            provider=self.name,
            requested_model=target.model,
            model=target.model,
            stop_reason="mock",
            input_tokens=len(system.split()) + len(turn.split()),
            output_tokens=len(reply.split()),
            latency_ms=int(digest[:2], 16) % 20 + 5,  # deterministic pseudo-latency
            parse_mode="json",
            is_mock=True,
            estimated_cost_usd=0.0,
        )

    def _gate(self, turn: str, target: Target) -> LLMResult:
        """Naive keyword gate so the LLM-gate plumbing can be tested offline. Deliberately weaker than rules."""
        msg = turn.lower()
        intent = ("maintenance" if re.search(r"leak|drip|ac\b|broken|repair|heat|gas|flood", msg) else
                  "renewal" if "renew" in msg else
                  "leasing" if re.search(r"tour|bed|floor plan|cheapest|apartment", msg) else "general")
        if "simulate gate failure" in msg:
            content = "not json"
        else:
            content = json.dumps({"intent": intent, "urgency": "low", "requires_human": False,
                                  "handoff_reason": "", "confidence": 0.7 if intent != "general" else 0.3,
                                  "risk_flags": []})
        return LLMResult(
            output=ModelOutput(reply=content), provider=self.name, requested_model=target.model,
            model=target.model, stop_reason="mock", input_tokens=len(turn.split()), output_tokens=20,
            latency_ms=3, parse_mode="text_fallback", is_mock=True, estimated_cost_usd=0.0,
            extra={"content": content},
        )
