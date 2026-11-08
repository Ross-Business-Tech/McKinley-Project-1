"""Synthetic persona usability suite.

Three parts, kept separate on purpose:
- ``personas`` / ``scenarios``: test GENERATION (who the person is, what they want, how they type). Scenarios say
  what the person wants and how they talk, never what the assistant should reply.
- ``simulator``: an adaptive simulated user that reads each real response (open card, missing details) and decides
  the next move, instead of replaying a fixed script.
- ``evaluator``: judges the finished conversation against the goal and safety rules using its own checks
  (it does not reuse the app's safety module), so a reply cannot pass just by matching the script.

Run against a running backend: ``uv run python -m app.usability.run --base-url http://127.0.0.1:8000``.
All personas and data are fictional.
"""
