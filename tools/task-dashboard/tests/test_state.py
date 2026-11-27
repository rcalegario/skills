"""state.py: one row per task folder, with the state status.py computes."""
import datetime
import os

from conftest import write

import state


def rows_by_id(home):
    return {row["id"]: row for row in state.task_rows(str(home))}


def test_rows_carry_status_of_each_task(home):
    rows = rows_by_id(home)
    assert set(rows) == {"2026-11-12-0900-alpha", "2026-11-10-1000-old"}
    alpha = rows["2026-11-12-0900-alpha"]
    assert alpha["repo"] == "skills"
    assert alpha["path"] == "tasks/skills/2026-11-12-0900-alpha"
    assert alpha["legacy"] is False
    assert alpha["title"] == "Alpha task"
    assert (alpha["step"]["step"], alpha["step"]["reason"]) == ("decide", "D-01 is open")
    assert alpha["counts"] == {"failures": 0, "warnings": 0}
    assert alpha["error"] is None


def test_row_reason_summarizes_the_step(home):
    alpha = rows_by_id(home)["2026-11-12-0900-alpha"]
    assert alpha["reason"] == {"text": "D-01 open", "hover": alpha["step"]["reason"], "failed": False}
    assert alpha["step"]["reason"] == "D-01 is open"


def test_snapshot_is_the_api_payload(home):
    snap = state.snapshot(str(home))
    assert set(snap) == {"home", "generated", "tasks"}
    assert "\\" not in snap["home"]
    assert [t["id"] for t in snap["tasks"]] == ["2026-11-10-1000-old", "2026-11-12-0900-alpha"]


def test_legacy_row_has_name_only(home):
    assert rows_by_id(home)["2026-11-10-1000-old"] == {
        "repo": "iac", "id": "2026-11-10-1000-old", "path": "tasks/iac/2026-11-10-1000-old", "legacy": True}


def test_broken_task_does_not_hide_the_others(home):
    write(home, "tasks/skills/2026-11-13-0900-broken/acs.yaml", "- id: [unclosed\n")
    rows = rows_by_id(home)
    broken = rows["2026-11-13-0900-broken"]
    assert broken["legacy"] is False
    assert "is not valid YAML" in broken["error"]
    assert rows["2026-11-12-0900-alpha"]["error"] is None
    assert "2026-11-10-1000-old" in rows


def test_row_has_progress_and_last_activity(home):
    alpha = "tasks/skills/2026-11-12-0900-alpha/"
    write(home, alpha + "journal.yaml", '- id: J-001\n  date: 2026-11-12\n  type: start\n  text: "first"\n'
                                         '- id: J-002\n  date: 2026-11-13\n  type: progress\n  text: "second"\n')
    write(home, alpha + "pending.yaml", '- id: P-1\n  status: open\n  with: [ana]\n  action: "ask"\n'
                                         '- id: P-2\n  status: closed\n  with: [ana]\n  action: "done"\n')
    write(home, alpha + "repos/skills/late.txt", "a worktree file never counts\n")
    row = rows_by_id(home)["2026-11-12-0900-alpha"]
    assert row["items"] == {"total": 1, "by_status": {"deciding": 1}}
    assert row["features"] == {"done": 0, "total": 0}
    assert row["decisions"] == {"open": 1, "proposed": 0}
    assert row["pending_open"] == 1
    assert row["last_note"] == {"id": "J-002", "date": "2026-11-13", "text": "second"}
    newest = max(os.path.getmtime(os.path.join(str(home), alpha, f)) for f in ("journal.yaml", "pending.yaml"))
    assert row["last_activity"] == datetime.datetime.fromtimestamp(newest).isoformat(timespec="seconds")
    os.utime(os.path.join(str(home), alpha, "repos/skills/late.txt"), (newest + 999, newest + 999))
    assert rows_by_id(home)["2026-11-12-0900-alpha"]["last_activity"] == row["last_activity"]


def test_row_lists_open_requirements_with_missing(home):
    row = rows_by_id(home)["2026-11-12-0900-alpha"]
    [req] = row["open_requirements"]
    assert (req["id"], req["item"], req["text"], req["status"]) == ("AC-1.1", "AC-1", "it works", "deciding")
    assert [m["id"] for m in req["missing"]] == ["D-01"]
    assert req["missing"][0]["text"]


def test_failures_replace_the_reason(home):
    alpha = "tasks/skills/2026-11-12-0900-alpha/"
    write(home, alpha + "acs.yaml", ACS_CITING_MISSING)
    row = rows_by_id(home)["2026-11-12-0900-alpha"]
    failures = state.collect(os.path.join(str(home), alpha))[1]["failures"]
    assert len(failures) == 2
    assert row["reason"] == {"text": "2 check failures", "hover": "\n".join(failures), "failed": True}
    assert row["step"]["your_turn"] is True


ACS_CITING_MISSING = """\
- id: AC-1
  text: "The thing works."
  status: deciding
  requirements:
    - id: AC-1.1
      text: "it works, see V-08"
      status: deciding
      decision: D-01
      validations: [V-01, V-09]
"""
