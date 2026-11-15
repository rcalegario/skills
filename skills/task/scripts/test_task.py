"""Tests for task.py, through its CLI. Run: python -m pytest <skill-dir>/scripts -q"""
import datetime
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import task as task_cli  # noqa: E402
from test_status import ACS, D01, D02, V01, write  # noqa: E402

TODAY = datetime.date.today().isoformat()


@pytest.fixture
def folder(tmp_path):
    write(tmp_path, "acs.yaml", ACS)
    write(tmp_path, "decisions/D-01-source.yaml", D01)
    write(tmp_path, "validations/V-01-published.yaml", V01)
    write(tmp_path, "journal.yaml",
          "# journal\n\n- id: J-001\n  date: 2026-11-12\n  type: decision\n  text: x\n  refs: [D-01]\n")
    write(tmp_path, "pending.yaml", "# pending\n[]\n")
    return tmp_path


def run(root, *args):
    return task_cli.main([str(root)] + list(args))


def load(root, rel):
    return yaml.safe_load((root / rel).read_text(encoding="utf-8"))


def test_journal_appends_the_next_id_with_today(folder):
    assert run(folder, "journal", "--type", "decision", "--text", "Picked X", "--refs", "D-01") == 0
    notes = load(folder, "journal.yaml")
    assert [n["id"] for n in notes] == ["J-001", "J-002"]
    assert notes[1] == {"id": "J-002", "date": datetime.date.today(), "type": "decision", "text": "Picked X", "refs": ["D-01"]}
    assert (folder / "journal.yaml").read_text().startswith("# journal\n\n- id: J-001\n")


def text(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def test_new_pending_numbers_and_opens_the_item(folder):
    assert run(folder, "new", "pending", "--with", "ana,team", "--action", "Ask about the lock", "--refs", "D-01") == 0
    assert run(folder, "new", "pending", "--with", "me", "--action", "Second") == 0
    items = load(folder, "pending.yaml")
    assert [i["id"] for i in items] == ["P-1", "P-2"]
    assert items[0] == {"id": "P-1", "with": ["ana", "team"], "action": "Ask about the lock",
                        "refs": ["D-01"], "status": "open"}
    assert text(folder, "pending.yaml").startswith("# pending\n")


def test_new_decision_takes_the_next_id_and_links_to_its_parent(folder):
    assert run(folder, "new", "decision", "template-name", "--title", "Template name",
               "--question", "Which prefix?", "--born-from", "D-01", "--discuss-with", "team") == 0
    d = load(folder, "decisions/D-02-template-name.yaml")
    assert (d["id"], d["status"], str(d["date"]), d["born_from"], d["discuss_with"]) == \
        ("D-02", "open", TODAY, ["D-01"], ["team"])
    assert d["question"].strip() == "Which prefix?"


def test_new_decision_for_a_requirement_becomes_its_root(folder):
    write(folder, "acs.yaml", ACS + "    - id: AC-1.2\n      text: \"second thing\"\n      validations: [V-01]\n")
    assert run(folder, "new", "decision", "second", "--title", "Second", "--question", "How?",
               "--requirement", "AC-1.2") == 0
    reqs = load(folder, "acs.yaml")[0]["requirements"]
    assert reqs[0]["decision"] == "D-01" and reqs[1]["decision"] == "D-02"
    assert load(folder, "decisions/D-02-second.yaml")["born_from"] == []


def test_new_validation_with_decides_is_a_spike(folder):
    write(folder, "decisions/D-02-name.yaml", D02)
    assert run(folder, "new", "validation", "lock", "--title", "Lock holds", "--how", "Try two clones",
               "--expected", "Second push fails", "--where", "clone", "--decides", "D-02") == 0
    v = load(folder, "validations/V-02-lock.yaml")
    assert (v["id"], v["status"], v["decides"], v["where"]) == ("V-02", "pending", ["D-02"], "clone")


def test_decide_records_status_date_and_reason(folder):
    write(folder, "decisions/D-02-name.yaml", D02)
    assert run(folder, "decide", "D-02", "--decision", "Prefix tpl-", "--why", "- Matches the fleet.") == 0
    d = load(folder, "decisions/D-02-name.yaml")
    assert (d["status"], str(d["date"])) == ("decided", TODAY)
    assert d["decision"].strip() == "Prefix tpl-" and d["why"].strip() == "- Matches the fleet."
    assert d["question"].strip() == "Which prefix?"


def test_decide_proposed_needs_no_reason_but_decided_does(folder):
    write(folder, "decisions/D-02-name.yaml", D02)
    before = text(folder, "decisions/D-02-name.yaml")
    assert run(folder, "decide", "D-02", "--decision", "Prefix tpl-") == 1
    assert text(folder, "decisions/D-02-name.yaml") == before
    assert run(folder, "decide", "D-02", "--decision", "Prefix tpl-", "--proposed") == 0
    assert load(folder, "decisions/D-02-name.yaml")["status"] == "proposed"


def test_supersede_links_both_decisions(folder):
    write(folder, "decisions/D-02-name.yaml", D02)
    run(folder, "decide", "D-02", "--decision", "Prefix tpl-", "--why", "- ok")
    run(folder, "new", "decision", "name-v2", "--title", "Name v2", "--question", "Again?", "--born-from", "D-01")
    assert run(folder, "supersede", "D-02", "D-03") == 0
    old, new = load(folder, "decisions/D-02-name.yaml"), load(folder, "decisions/D-03-name-v2.yaml")
    assert (old["status"], old["superseded_by"], new["supersedes"]) == ("superseded", "D-03", "D-02")
    assert str(old["date"]) == TODAY


def test_validate_records_the_run(folder):
    write(folder, "validations/evidence/shot.png", "png")
    assert run(folder, "validate", "V-01", "--status", "passed", "--evidence", "Seen in vCenter.",
               "--attach", "shot.png") == 0
    v = load(folder, "validations/V-01-published.yaml")
    assert (v["status"], str(v["date"]), v["attachments"]) == ("passed", TODAY, ["shot.png"])
    assert v["evidence"].strip() == "Seen in vCenter."


def test_validate_passed_without_evidence_is_refused(folder):
    before = text(folder, "validations/V-01-published.yaml")
    assert run(folder, "validate", "V-01", "--status", "passed") == 1
    assert text(folder, "validations/V-01-published.yaml") == before


def test_close_stamps_the_pending_item(folder):
    run(folder, "new", "pending", "--with", "ana", "--action", "Ask")
    assert run(folder, "close", "P-1", "--link", "https://example.com/c/1") == 0
    p = load(folder, "pending.yaml")[0]
    assert (p["status"], str(p["closed"]), p["link"]) == ("done", TODAY, "https://example.com/c/1")


def test_consolidate_sets_the_brief_date(folder):
    write(folder, "brief.md", "---\ndate: 2026-01-01   # last consolidation\n---\n# Brief\n")
    assert run(folder, "consolidate") == 0
    assert text(folder, "brief.md") == "---\ndate: %s   # last consolidation\n---\n# Brief\n" % TODAY
