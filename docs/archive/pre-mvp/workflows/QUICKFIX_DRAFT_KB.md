# Quick-fix tips: draft knowledge base (Sprint 8)

**Status of every entry: DRAFT — Pending McKinley Approval.** None of these is approved, so none is shown to residents in a real
user-facing mode. This file is generated from `backend/app/content/quickfix_drafts.py`; that file is the source of truth.

## Approval boundary

| `QUICKFIX_CONTENT_MODE` | What residents see |
| --- | --- |
| `approved_only` (default) | only entries with status `approved` **and** `approved_by` **and** `approved_on` filled; today none |
| `demo_drafts` | the drafts, visibly labelled "Draft tips for this demo, not yet approved by McKinley"; **local backend and direct local requests only**; a hosted backend or a proxied request falls back to `approved_only`, and hosted startup refuses this value |
| `off` (or any unknown value) | nothing |

The older checks in `backend/app/workflows.py` (`LEGACY_DRAFT_TROUBLESHOOTING`, previously misnamed `APPROVED_TROUBLESHOOTING`)
are drafts too and go through the same gate and the same safety checks.

**To approve an entry** McKinley maintenance reviews the wording, then the entry gets `status="approved"`, `approved_by` and
`approved_on`. Nothing else changes.

## Safety checks before any tip (`backend/app/quickfix.py`)
A tip is shown only when the safety decision for that turn is a clean "none" (no alert, no care line, no person in danger, no
incident), the safety classifier did not fail or report uncertainty, no general exclusion is present (gas, smoke or fire,
burning, sparks / arcing / exposed wiring / a shock, water leaking, flooding, overflowing or spreading, carbon monoxide or an
alarm, an injury, sewage, urgency words), the issue's own exclusions are absent, it is not a repeat issue, the resident did not
ask to skip, and tips were not already offered for this issue. Unsafe questions ("can I reach into the disposal?", removing a
panel cover, chemicals or boiling water in a drain) get a direct "No" and no tips.

## Flow
Tips (1–3) → "Did that fix it?" → *fixed*: closes, nothing is sent, no record · *not fixed / unclear / skip*: the normal repair
request opens with the original issue (and on-file details) · a side question is answered and the offer stays open for up to 2
turns · a new problem gets its own card and the tips' issue is queued · one round per issue.

## Entries

### `qf-breaker-reset` (electrical_breaker)

- **Status:** DRAFT — Pending McKinley Approval (author: Sprint 8 team draft (Agent D, quick-fix workflow); synthetic prototype; 2026-11-10)
- **When:** A breaker tripped, or the lights/outlets in one room or part of the home stopped working while the rest of the home has power. EN + ES.
- **Never when:** Burning smell, smoke, sparks, heat, buzzing/crackling, scorch marks, water near the panel or outlets, exposed wires, a shock, a panel outside the home or locked, the main breaker, the whole building or neighbours without power, a breaker that keeps tripping or was already reset.
- **Steps (EN):**
  1. Unplug or switch off things on the outlets that stopped working.
  2. Only if your breaker panel is inside your home and its door opens by hand: find the switch that is in the middle or OFF position, push it firmly to OFF, then back to ON. Leave the panel's cover on.
  3. If it trips again, leave it off and don't reset it again. Tell me and I'll start a repair request.
- **Steps (ES, draft):**
  1. Desconecte o apague lo que esté enchufado en los tomacorrientes que dejaron de funcionar.
  2. Solo si su panel de breakers está dentro de su casa y la puerta se abre con la mano: busque el interruptor que esté en el medio o en OFF, empújelo firme a OFF y luego a ON. Nunca quite la tapa del panel.
  3. Si se vuelve a botar, déjelo apagado y no lo reinicie otra vez. Dígame y empiezo una solicitud de reparación.

### `qf-gfci-reset` (electrical_gfci)

- **Status:** DRAFT — Pending McKinley Approval (author: Sprint 8 team draft (Agent D, quick-fix workflow); synthetic prototype; 2026-11-10)
- **When:** A bathroom, kitchen, laundry, garage or outdoor outlet stopped working, or the resident names a GFCI / GFI / outlet with test and reset buttons. EN + ES.
- **Never when:** Wet or damp outlet or hands, water nearby, a shock, warm/hot outlet, burning smell, sparks, smoke, melted or cracked outlet, buzzing, the reset button won't stay in, already reset.
- **Steps (EN):**
  1. Look for an outlet with TEST and RESET buttons nearby (often in the kitchen, bathroom, laundry or garage). One of them can control several outlets.
  2. With dry hands, and only if the outlet and the area around it are dry, press RESET firmly until it clicks.
  3. If it won't stay in or clicks off again, stop there. Tell me and I'll start a repair request.
- **Steps (ES, draft):**
  1. Busque un tomacorriente cercano con botones TEST y RESET (suele estar en la cocina, el baño, la lavandería o el garaje). Uno solo puede controlar varios tomacorrientes.
  2. Con las manos secas, y solo si el tomacorriente y la zona alrededor están secos, presione RESET con firmeza hasta que haga clic.
  3. Si no se queda presionado o se vuelve a botar, no siga. Dígame y empiezo una solicitud de reparación.

### `qf-disposal-reset` (appliance_disposal)

- **Status:** DRAFT — Pending McKinley Approval (author: Sprint 8 team draft (Agent D, quick-fix workflow); synthetic prototype; 2026-11-10)
- **When:** The garbage disposal won't turn on, stopped working or only hums. EN + ES.
- **Never when:** Water leaking under the sink, burning smell, smoke, sparks, a hand or object stuck inside, anyone hurt, already reset. Never: reaching into the disposal, tools, unjamming the blades.
- **Steps (EN):**
  1. Turn the disposal switch OFF. Never put your hand inside the disposal.
  2. Under the sink, on the bottom of the disposal, press the small red or black reset button once.
  3. Run cold water and switch it back on. If it still hums or won't start, switch it off and tell me. I'll start a repair request.
- **Steps (ES, draft):**
  1. Apague el interruptor del triturador. Nunca meta la mano dentro del triturador.
  2. Debajo del fregadero, en la parte de abajo del triturador, presione una vez el botoncito rojo o negro de reinicio (reset).
  3. Abra el agua fría y vuelva a encenderlo. Si sigue zumbando o no arranca, apáguelo y dígame. Empiezo una solicitud de reparación.

### `qf-slow-drain` (plumbing_drain)

- **Status:** DRAFT — Pending McKinley Approval (author: Sprint 8 team draft (Agent D, quick-fix workflow); synthetic prototype; 2026-11-10)
- **When:** A sink, tub or shower drains slowly or is clogged, with no leak and no overflow. EN + ES. Toilets are excluded (overflow risk) and go straight to a repair request.
- **Never when:** Toilet, overflowing / backing up, water on the floor or under the sink, any leak, sewage smell, several drains at once, chemical drain cleaner already used, already tried.
- **Steps (EN):**
  1. Stop using that drain for now so it doesn't overflow.
  2. If the stopper or hair catcher lifts out by hand, take it out and clear off any hair or debris.
  3. Run warm tap water for a minute. Please don't use chemical drain cleaners or boiling water. If it's still slow, tell me and I'll start a repair request.
- **Steps (ES, draft):**
  1. Deje de usar ese desagüe por ahora para que no se desborde.
  2. Si el tapón o el filtro de pelo se saca con la mano, sáquelo y quite el pelo o la suciedad.
  3. Deje correr agua tibia de la llave un minuto. Por favor no use destapacaños químicos ni agua hirviendo. Si sigue lento, dígame y empiezo una solicitud de reparación.
