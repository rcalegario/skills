"""Tests for the text report (report.py). Run: python -m pytest <skill-dir>/scripts -q"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

STATE = {
    "step": {"step": "decide", "reason": "D-02 is open", "blockers": [], "your_turn": True},
    "items": [
        {"id": "AC-1", "text": "t", "status": "deciding", "pr_note": None, "requirements": ["AC-1.1", "AC-1.2"]},
        {"id": "AC-2", "text": "gone", "status": "dropped", "pr_note": None, "requirements": ["AC-2.1"]},
    ],
    "requirements": [
        {"id": "AC-1.1", "item": "AC-1", "text": "r", "status": "deciding", "decision": "D-01",
         "tree": ["D-01", "D-02"], "validations": [{"id": "V-01", "status": "passed"}],
         "missing": [{"text": "D-02 is open"}]},
        {"id": "AC-1.2", "item": "AC-1", "text": "s", "status": "decided", "decision": "D-03",
         "tree": ["D-03", "D-04"], "validations": [{"id": "V-09", "status": None}], "missing": []},
    ],
    "features": [{"id": "F1.1-a", "status": "building", "decisions": ["D-01"], "validations": []}],
    "spikes": [{"id": "V-05", "status": "pending", "where": None, "decides": ["D-02"], "blocks": []}],
    "agenda": {"me": [{"kind": "decision", "id": "D-02", "status": "open", "title": "Name  it", "awaits": ["V-05"]}]},
}
STATUSES = {"D-01": "decided", "D-02": "open", "D-03": "decided", "D-04": "decided", "V-01": "passed"}
ROOTS = [["D-01"], ["D-03", "D-04"]]


def test_report_renders_from_collected_state():
    # Plain data only: no task folder and no Task exist, so every cell comes from these three inputs.
    lines = status.task_report.render(STATE, STATUSES, ROOTS).split("\n")
    assert lines[0] == "Step: decide - D-02 is open"
    assert "| AC-1 | deciding | 2 | 3/4 | 1/2 |" in lines
    assert not any(line.startswith("| AC-2") for line in lines)
    assert "| AC-1.1 | deciding | D-01 | D-02 | D-02 (open) | V-01 (passed) | D-02 is open |" in lines
    assert "| AC-1.2 | decided | D-03, D-04 | - | - | V-09 (?) | - |" in lines
    assert "| F1.1-a | building | D-01 | - |" in lines
    assert "| V-05 | pending | - | D-02 | - |" in lines
    assert "- D-02 (open) Name it - awaiting spike V-05" in lines


def test_task_report_is_the_render_of_its_collected_state(task):
    t = status.Task(str(task))
    t.check()
    statuses = {d: dec.get("status") for d, dec in t.decisions.items()}
    statuses.update({v: val.get("status", "?") for v, val in t.validations.items()})
    assert t.report() == status.task_report.render(t.collect(), statuses, [["D-01"]])
