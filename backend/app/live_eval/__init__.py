"""Controlled live evaluation: preflight (no spend) and a fixed-model A/B/C runner.

- ``preflight``: checks configuration without spending (key present as a boolean, provider readiness) and verifies
  the configured model IDs against OpenRouter's PUBLIC model list (no key needed). Writes evals/live/preflight.json.
- ``abc``: runs baseline (A) / prompt_only (B) / aware (C) against ONE fixed provider:model with identical generation
  settings, over the five core cases and multi-turn persona conversations. Refuses to run without a ready provider
  (never falls back to mock); ``--allow-mock`` gives a labelled MOCK dry run that is never comparable.
- ``recorder``: a gateway wrapper that records every model call, enforces the call budget and pacing, and stops the
  run cleanly on persistent rate limits or fatal configuration errors.

See evals/live/README.md.
"""
