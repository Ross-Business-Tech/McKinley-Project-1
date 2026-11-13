"""Manual live-model checks (development only; never imported by the running app).

- ``preflight``: checks configuration without spending (key present as a boolean, provider readiness) and verifies
  the configured model IDs against the provider's model list. Writes evals/live/preflight.json (git-ignored; the
  folder is created on demand).
- ``smoke``: a short, budgeted conversation through the real pipeline against ONE fixed provider:model; writes
  evals/live/smoke-<label>.json (git-ignored). Stops on the first 429 or a fatal configuration error.
- ``recorder``: the gateway wrapper both use to record calls, enforce the call budget and stop cleanly.
"""
