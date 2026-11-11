"""Quick-fix tips offered BEFORE a repair request, for a few clearly low-risk, commonly resolved issues (Sprint 8, D).

STATUS: every entry is a TEAM DRAFT, "DRAFT — Pending McKinley Approval". None is approved. With the default
QUICKFIX_CONTENT_MODE=approved_only (app/config.py) none of these is ever shown; QUICKFIX_CONTENT_MODE=demo_drafts
shows them on a local demo only, labelled as drafts (app/quickfix.py). A hosted backend refuses demo_drafts.

To approve an entry McKinley maintenance sets `status` to exactly "approved" and fills `approved_by` / `approved_on`
(a person's role and a date, no personal data). Changing a step's wording un-approves it (set the status back).

Safety rules every step follows (NEEDS McKINLEY REVIEW, docs/workflows/traceability.md I-20):
- no tools, no disassembly, no reaching into machinery, no chemical drain cleaners, no boiling water;
- no removing any cover (outlet plate, breaker panel cover, disposal housing), no touching wiring;
- breaker: only flipping a switch in a panel INSIDE the resident's own home whose door opens by hand. Conservative
  decision: a panel in a hallway, garage, meter room or locked utility room, a main breaker, a wet, hot, buzzing or
  scorched panel, or a breaker that trips again is never a tip (app/quickfix.py excludes those messages);
- every entry ends with "if it happens again / doesn't work, stop and we'll send a repair request", so the resident
  is never asked to repeat a reset.
Spanish strings are DRAFT translations and need review by a fluent McKinley staff member.
"""

from typing import Any

DRAFT_STATUS = "DRAFT — Pending McKinley Approval"
APPROVED_STATUS = "approved"
AUTHOR = "Sprint 8 team draft (Agent D, quick-fix workflow); synthetic prototype"
DATE = "2026-11-10"

ENTRIES: list[dict[str, Any]] = [
    {
        "id": "qf-breaker-reset",
        "category": "electrical_breaker",
        "triggers": "A breaker tripped, or the lights/outlets in one room or part of the home stopped working while "
                    "the rest of the home has power. EN + ES.",
        "exclusions": "Burning smell, smoke, sparks, heat, buzzing/crackling, scorch marks, water near the panel or "
                      "outlets, exposed wires, a shock, a panel outside the home or locked, the main breaker, the "
                      "whole building or neighbours without power, a breaker that keeps tripping or was already "
                      "reset.",
        "steps": {
            "en": [
                "Unplug or switch off things on the outlets that stopped working.",
                "Only if your breaker panel is inside your home and its door opens by hand: find the switch that is "
                "in the middle or OFF position, push it firmly to OFF, then back to ON. Leave the panel's cover "
                "on.",
                "If it trips again, leave it off and don't reset it again. Tell me and I'll start a repair request.",
            ],
            "es": [
                "Desconecte o apague lo que esté enchufado en los tomacorrientes que dejaron de funcionar.",
                "Solo si su panel de breakers está dentro de su casa y la puerta se abre con la mano: busque el "
                "interruptor que esté en el medio o en OFF, empújelo firme a OFF y luego a ON. Nunca quite la tapa "
                "del panel.",
                "Si se vuelve a botar, déjelo apagado y no lo reinicie otra vez. Dígame y empiezo una solicitud de "
                "reparación.",
            ],
        },
        "status": DRAFT_STATUS, "author": AUTHOR, "date": DATE, "approved_by": None, "approved_on": None,
    },
    {
        "id": "qf-gfci-reset",
        "category": "electrical_gfci",
        "triggers": "A bathroom, kitchen, laundry, garage or outdoor outlet stopped working, or the resident names a "
                    "GFCI / GFI / outlet with test and reset buttons. EN + ES.",
        "exclusions": "Wet or damp outlet or hands, water nearby, a shock, warm/hot outlet, burning smell, sparks, "
                      "smoke, melted or cracked outlet, buzzing, the reset button won't stay in, already reset.",
        "steps": {
            "en": [
                "Look for an outlet with TEST and RESET buttons nearby (often in the kitchen, bathroom, laundry or "
                "garage). One of them can control several outlets.",
                "With dry hands, and only if the outlet and the area around it are dry, press RESET firmly until it "
                "clicks.",
                "If it won't stay in or clicks off again, stop there. Tell me and I'll start a repair request.",
            ],
            "es": [
                "Busque un tomacorriente cercano con botones TEST y RESET (suele estar en la cocina, el baño, la "
                "lavandería o el garaje). Uno solo puede controlar varios tomacorrientes.",
                "Con las manos secas, y solo si el tomacorriente y la zona alrededor están secos, presione RESET con "
                "firmeza hasta que haga clic.",
                "Si no se queda presionado o se vuelve a botar, no siga. Dígame y empiezo una solicitud de "
                "reparación.",
            ],
        },
        "status": DRAFT_STATUS, "author": AUTHOR, "date": DATE, "approved_by": None, "approved_on": None,
    },
    {
        "id": "qf-disposal-reset",
        "category": "appliance_disposal",
        "triggers": "The garbage disposal won't turn on, stopped working or only hums. EN + ES.",
        "exclusions": "Water leaking under the sink, burning smell, smoke, sparks, a hand or object stuck inside, "
                      "anyone hurt, already reset. Never: reaching into the disposal, tools, unjamming the blades.",
        "steps": {
            "en": [
                "Turn the disposal switch OFF. Never put your hand inside the disposal.",
                "Under the sink, on the bottom of the disposal, press the small red or black reset button once.",
                "Run cold water and switch it back on. If it still hums or won't start, switch it off and tell me. "
                "I'll start a repair request.",
            ],
            "es": [
                "Apague el interruptor del triturador. Nunca meta la mano dentro del triturador.",
                "Debajo del fregadero, en la parte de abajo del triturador, presione una vez el botoncito rojo o "
                "negro de reinicio (reset).",
                "Abra el agua fría y vuelva a encenderlo. Si sigue zumbando o no arranca, apáguelo y dígame. Empiezo "
                "una solicitud de reparación.",
            ],
        },
        "status": DRAFT_STATUS, "author": AUTHOR, "date": DATE, "approved_by": None, "approved_on": None,
    },
    {
        "id": "qf-slow-drain",
        "category": "plumbing_drain",
        "triggers": "A sink, tub or shower drains slowly or is clogged, with no leak and no overflow. EN + ES. "
                    "Toilets are excluded (overflow risk) and go straight to a repair request.",
        "exclusions": "Toilet, overflowing / backing up, water on the floor or under the sink, any leak, sewage "
                      "smell, several drains at once, chemical drain cleaner already used, already tried.",
        "steps": {
            "en": [
                "Stop using that drain for now so it doesn't overflow.",
                "If the stopper or hair catcher lifts out by hand, take it out and clear off any hair or debris.",
                "Run warm tap water for a minute. Please don't use chemical drain cleaners or boiling water. If it's "
                "still slow, tell me and I'll start a repair request.",
            ],
            "es": [
                "Deje de usar ese desagüe por ahora para que no se desborde.",
                "Si el tapón o el filtro de pelo se saca con la mano, sáquelo y quite el pelo o la suciedad.",
                "Deje correr agua tibia de la llave un minuto. Por favor no use destapacaños químicos ni agua "
                "hirviendo. Si sigue lento, dígame y empiezo una solicitud de reparación.",
            ],
        },
        "status": DRAFT_STATUS, "author": AUTHOR, "date": DATE, "approved_by": None, "approved_on": None,
    },
]
