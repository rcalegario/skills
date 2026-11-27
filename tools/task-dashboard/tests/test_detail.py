"""detail.py and state.task_detail: one task folder read whole."""
from conftest import write

import state

ALPHA = "tasks/skills/2026-11-12-0900-alpha/"

FEATURE = """\
id: F1.1-thing
title: "The thing"
status: building
story:
  decisions: [D-01]
  validations: [V-01]
tasks:
  - id: T1
    title: "Do it"
    status: done
    sha: abc1234
"""

REVIEW = """\
findings:
  - id: R-1
    text: "a bug"
    severity: must-fix
"""


def test_detail_reads_the_whole_folder(home):
    write(home, ALPHA + "journal.yaml", '- id: J-001\n  date: 2026-11-12\n  type: start\n  text: "first"\n')
    write(home, ALPHA + "pending.yaml", '- id: P-1\n  status: open\n  with: [ana]\n  action: "ask"\n')
    write(home, ALPHA + ".specs/features/F1.1-thing/feature.yaml", FEATURE)
    write(home, ALPHA + ".specs/features/F1.1-thing/review.yaml", REVIEW)
    write(home, ALPHA + ".specs/features/F1.2-other/feature.yaml", "id: F1.2-other\ntitle: Other\nstatus: draft\n")
    detail = state.task_detail(str(home), "skills", "2026-11-12-0900-alpha")
    assert set(detail) == {"row", "status", "graph", "docs", "readme", "decisions", "validations", "features", "pending", "journal",
                           "next", "checks"}
    assert detail["row"]["title"] == "Alpha task" and detail["row"]["step"]["step"] == "decide"
    assert detail["status"]["requirements"][0]["id"] == "AC-1.1"
    assert detail["readme"] == {"title": "Alpha task", "link": None, "repos": [
        {"name": "skills", "origin": "~/skills", "worktree": "repos/skills", "branch": "feat/alpha", "main": True}]}
    assert detail["decisions"] == [{"id": "D-01", "title": "How it works", "status": "open", "date": "2026-11-12",
                                    "born_from": [], "discuss_with": ["me"], "question": "How?\n",
                                    "file": "D-01-how.yaml"}]
    assert detail["validations"][0]["id"] == "V-01" and detail["validations"][0]["how"] == "Run it.\n"
    features = {f["folder"]: f for f in detail["features"]}
    assert features["F1.1-thing"]["tasks"][0]["sha"] == "abc1234"
    assert features["F1.1-thing"]["review"]["findings"][0]["id"] == "R-1"
    assert features["F1.2-other"]["review"] is None
    assert detail["pending"][0]["id"] == "P-1"
    assert detail["journal"][0]["text"] == "first"


def test_detail_of_unknown_legacy_or_broken_task_is_none(home):
    write(home, "tasks/skills/2026-11-13-0900-broken/acs.yaml", "- id: [unclosed\n")
    assert state.task_detail(str(home), "skills", "nope") is None
    assert state.task_detail(str(home), "iac", "2026-11-10-1000-old") is None
    assert state.task_detail(str(home), "skills", "2026-11-13-0900-broken") is None
    assert state.task_detail(str(home), "iac", "2026-11-12-0900-alpha") is None
