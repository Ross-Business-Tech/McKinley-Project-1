# Build vs Buy — decision structure (not a final verdict)

## Hypothesis
A **thin, owned context and policy orchestration layer** on top of a frontier model can improve helpfulness and appropriate escalation without replacing Yardi's mission-critical workflows. Test a hybrid first; do not assume a custom omnichannel build is cheaper or safer.

## Evidence from kickoff
- Yardi handles phone/email/SMS/chat and after-hours work orders; handoff estimated at 50–60% at many sites.
- McKinley has an existing Databricks copy of operational data with ~10-minute lag, enabling ownership of context but not necessarily live writes.
- Small technical team (2 full-stack + 2 data engineers) also supports other systems.
- Joshua requests strong recommendation, risk controls, costs, governance, and one measurable value proposition.

## Primary KPI (pick one lane)
**Context-appropriate resolution quality**: percentage of evaluated conversations that provide a correct, safe, helpful response and proper human handoff when needed. Secondary metrics: resident satisfaction survey, repeat contact rate within 7 days, escalation appropriateness, cost/conversation, and staff review load.

## Experiment
Same five prompts, baseline prompt vs. aware prompt, same model/temperature. Include reviewer blind scoring and record errors. Five cases are a functional demonstration, not statistically significant ROI evidence. Before pilots, extend to a representative, stratified set of anonymized conversations, include multilingual and emergency cases, and validate with human staff and counsel.

## Cost/ROI worksheet (must be filled with actual quotes and measurements)
Annual workload assumptions from Joshua: ~14,000 residents, ~100,000 unique prospect conversations/year; resident conversation volume is UNKNOWN. Model cost = (input tokens * vendor input price + output tokens * vendor output price), adjusted for caching, multimodal/voice and retry overhead. Add telephony/SMS, hosting, Yardi/Databricks access, security, eval/review, maintenance and opportunity cost of engineering. ROI = monetized *incremental* service benefits (e.g. reduction in repeat avoidable tickets) minus incremental total cost. Do not equate labor reduction with sustainable benefits or invent prices/volume.

## Decision gates
1. Prototype: response quality, privacy and staff review pass.
2. Limited pilot: legal/security review, operational rollback, logs and KPIs.
3. Production: auth, access control, real integration contracts, monitoring, audit and change governance.

Compare (a) existing Yardi, (b) vendor add-on, (c) thin contextual layer/hybrid, (d) full in-house. Show costs and ownership risk for each before recommending full deployment.
