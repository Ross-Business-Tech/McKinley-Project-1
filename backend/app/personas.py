"""Persona catalog: fictional prospects (not from the workbook), an unmatched resident, and workbook residents.

Only safe labels are exposed by the API. Workbook-backed context is produced by `app.context`.
"""

from app.context import NEVER_FORWARDED, Workbook, build_resident_context, detect_topics
from app.models import ContextField, Persona, SafeContext

# Clearly fictional prospects. No live inventory, pricing or tour calendar exists for them.
FICTIONAL_PROSPECTS: dict[str, dict] = {
    "P-RELOCATE-AA": {
        "label": "Fictional prospect · relocating to Ann Arbor",
        "description": "Demo prospect moving for work next month; interested in two-bed floor plans.",
        "fields": [
            ("interest_area", "Ann Arbor, Michigan area"),
            ("desired_floor_plan", "two-bed"),
            ("move_in_timeframe", "next month"),
            ("lead_channel", "website chat"),
        ],
    },
    "P-BROWSE-FL": {
        "label": "Fictional prospect · browsing Florida",
        "description": "Demo prospect browsing online; no community selected.",
        "fields": [
            ("interest_area", "Florida (no community selected)"),
            ("lead_channel", "website chat"),
        ],
    },
}

UNMATCHED_RESIDENT_ID = "U-NOMATCH"

PROSPECT_NOTES = [
    "Fictional prospect profile created for the demo; not from the resident workbook.",
    "No live inventory, pricing, specials or tour calendar is connected in this prototype.",
]


def list_personas(wb: Workbook | None) -> list[Persona]:
    out = [
        Persona(id=pid, label=p["label"], kind="prospect", description=p["description"])
        for pid, p in FICTIONAL_PROSPECTS.items()
    ]
    out.append(Persona(
        id=UNMATCHED_RESIDENT_ID,
        label="Fictional resident · no matched record",
        kind="unmatched_resident",
        description="Says they are a resident, but no verified record is linked.",
    ))
    if wb:
        for rid, res in sorted(wb.residents.items()):
            first = (res.get("first_name") or "Resident")[:30]
            out.append(Persona(
                id=rid,
                label=f"{rid} · {first} (synthetic resident)",
                kind="resident",
                description=f"Synthetic workbook resident at {res.get('community') or 'unknown community'}.",
            ))
    return out


def build_context(persona_id: str | None, message: str, wb: Workbook | None) -> SafeContext:
    topics = detect_topics(message)
    if persona_id in FICTIONAL_PROSPECTS:
        p = FICTIONAL_PROSPECTS[persona_id]
        return SafeContext(
            persona_id=persona_id,
            persona_kind="prospect",
            audience="prospect",
            record_found=True,
            topics=topics,
            fields=[ContextField(name=n, value=v, source="fictional_prospect_fixture") for n, v in p["fields"]],
            notes=PROSPECT_NOTES,
        )
    if persona_id == UNMATCHED_RESIDENT_ID:
        return SafeContext(
            persona_id=persona_id,
            persona_kind="unmatched_resident",
            audience="resident",
            record_found=False,
            topics=topics,
            fields=[],
            notes=["Person identifies as a resident but no verified record is matched. Do not guess history."],
        )
    if persona_id and wb and persona_id in wb.residents:
        return build_resident_context(wb.residents[persona_id], message, persona_id)
    return SafeContext(
        persona_id=persona_id,
        persona_kind=None,
        audience="unknown",
        record_found=False,
        topics=topics,
        fields=[],
        withheld_fields=NEVER_FORWARDED if persona_id else [],
        notes=["No persona selected or record unavailable; audience unknown."],
    )
