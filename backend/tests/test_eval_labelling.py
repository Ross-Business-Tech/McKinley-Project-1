"""Evaluation honesty: fixed backend templates and the mock are never reported as live-model evidence."""

from app.usability.evaluator import _execution, turn_source


def test_template_turns_are_not_live():
    template = {"model": "deterministic-template", "is_mock": False, "reply_source": "template"}
    mock = {"model": "mock-deterministic-v1", "is_mock": True, "reply_source": "model"}
    live = {"model": "nvidia/nemotron-3.5-super-vl", "is_mock": False, "reply_source": "model"}
    assert turn_source(template) == "template" and turn_source(mock) == "mock" and turn_source(live) == "live"
    assert _execution([template]) == "mock"
    assert _execution([template, mock]) == "mock"
    assert _execution([template, live]) == "live"
    assert _execution([mock, live]) == "mixed"


def test_committed_usability_runs_are_all_mock():
    import json
    from pathlib import Path
    for f in sorted((Path(__file__).resolve().parents[2] / "evals" / "usability").glob("results-*.json")):
        doc = json.loads(f.read_text())
        assert set(doc["summary"]["execution"]) == {"mock"}, f.name
