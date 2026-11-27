"""Tests for task.py, through its CLI. Run: python -m pytest <skill-dir>/scripts -q"""
import datetime
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402
import task as task_cli  # noqa: E402
from test_status import ACS, D01, D02, MAIN_README, V01, open_items, requirements, write  # noqa: E402

TODAY = datetime.date.today().isoformat()
# BRIEF-2 of the folder fixture: its one item and requirement, rooted at D-01
REQUIREMENTS = "- **AC-1** The build produces a template.\n  - AC-1.1 (D-01) a separate template exists"
# BRIEF-2 and BRIEF-4 of the folder fixture: D-01 is decided and no pending item is open
BRIEF_BODY = requirements(REQUIREMENTS) + open_items(status.NOTHING_OPEN)


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


def start_folder(tmp_path):
    """The folder as step 3 of start leaves it: a filled README and the three YAML lists empty."""
    root = tmp_path / "iac" / "2026-11-15-1430-metrics-base-image"
    write(root, "README.md", MAIN_README)
    for name in ("acs.yaml", "pending.yaml", "journal.yaml"):
        write(root, name, "[]\n")
    return root


def test_journal_takes_the_first_note_in_a_folder_made_by_start(tmp_path, capsys):
    root = start_folder(tmp_path)
    assert run(root, "journal", "--type", "investigation", "--text", "Task folder created.") == 0
    assert [n["id"] for n in load(root, "journal.yaml")] == ["J-001"]
    capsys.readouterr()
    assert status.main([str(root)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("No failures.")


def test_a_folder_without_acs_yaml_is_refused(tmp_path, capsys):
    root = start_folder(tmp_path)
    (root / "acs.yaml").unlink()
    assert run(root, "journal", "--type", "investigation", "--text", "x") == 2
    assert "has no acs.yaml; not a task folder" in capsys.readouterr().out
    assert load(root, "journal.yaml") == []


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


def test_consolidate_stamps_the_date_and_the_sources(folder):
    write(folder, "context/now.md", "---\ncode: NOW\n---\n\n## NOW-1 Today\n")
    write(folder, "brief.md", "---\ndate: 2026-01-01   # last consolidation\n---\n# Brief\n" + BRIEF_BODY)
    assert run(folder, "consolidate") == 0
    digest = status.sources_digest(str(folder))
    expected = ("---\ndate: %s   # last consolidation\nsources:\n  context: \"%s\"\n  acs: \"%s\"\n"
                "  decisions: \"%s\"\n---\n# Brief\n" % (TODAY, digest["context"], digest["acs"], digest["decisions"])
                + BRIEF_BODY)
    assert text(folder, "brief.md") == expected
    assert run(folder, "consolidate") == 0
    assert text(folder, "brief.md") == expected


def test_consolidate_replaces_an_old_sources_map(folder):
    write(folder, "brief.md", "---\ncode: BRIEF\ndate: 2026-01-01\nsources:\n  context: \"aaaaaaaaaaaa\"\n  acs: \"bbbbbbbbbbbb\"\ntitle: b\n---\n# Brief\n" + BRIEF_BODY)
    assert run(folder, "consolidate") == 0
    head = yaml.safe_load(text(folder, "brief.md").split("---\n")[1])
    assert head["sources"] == status.sources_digest(str(folder))
    assert head["title"] == "b" and head["code"] == "BRIEF"
    assert status.Task(str(folder)).step()["reason"] != "brief.md has no sources"


def test_consolidate_quotes_a_hash_made_only_of_digits(folder, monkeypatch):
    write(folder, "brief.md", "---\ndate: 2026-01-01\n---\n# Brief\n" + BRIEF_BODY)
    monkeypatch.setattr(status, "sources_digest", lambda root: {g: "012345678901" for g in status.SOURCE_GROUPS})
    assert run(folder, "consolidate") == 0
    assert yaml.safe_load(text(folder, "brief.md").split("---\n")[1])["sources"]["acs"] == "012345678901"


# ---------------------------------------------------------------- sync and state machines

def test_sync_writes_the_status_of_every_requirement_and_item(folder):
    write(folder, "acs.yaml", "# outcomes\n" + ACS.replace("      status: decided\n", "").replace("  status: decided\n", ""))
    assert run(folder, "sync") == 0
    acs = load(folder, "acs.yaml")
    assert acs[0]["status"] == "decided" and acs[0]["requirements"][0]["status"] == "decided"
    assert text(folder, "acs.yaml").startswith("# outcomes\n")
    assert run(folder, "sync") == 0
    assert load(folder, "acs.yaml") == acs


def test_sync_overwrites_a_status_edited_by_hand(folder):
    write(folder, "acs.yaml", ACS.replace("      status: decided", "      status: concluded"))
    assert run(folder, "sync") == 0
    assert load(folder, "acs.yaml")[0]["requirements"][0]["status"] == "decided"


def test_sync_leaves_a_dropped_item_alone(folder):
    write(folder, "acs.yaml", ACS + "\n- id: X-1\n  text: extra\n  status: dropped\n  requirements: []\n")
    assert run(folder, "sync") == 0
    assert load(folder, "acs.yaml")[1]["status"] == "dropped"


def test_commands_keep_the_stored_status_in_step(folder):
    assert run(folder, "new", "decision", "child", "--title", "Child", "--question", "Q?", "--born-from", "D-01") == 0
    acs = load(folder, "acs.yaml")
    assert acs[0]["requirements"][0]["status"] == "deciding" and acs[0]["status"] == "deciding"
    assert run(folder, "decide", "D-02", "--decision", "x", "--why", "y") == 0
    assert load(folder, "acs.yaml")[0]["requirements"][0]["status"] == "decided"
    assert run(folder, "validate", "V-01", "--status", "passed", "--evidence", "Seen.") == 0
    assert load(folder, "acs.yaml")[0]["status"] == "decided"      # needs_code and no feature yet


def test_sync_writes_the_roadmap_status(folder):
    write(folder, ".specs/features/F1.1-template/feature.yaml",
          "id: F1.1-template\ntitle: T\nsize: M\nstatus: building\nroadmap: F1.1\n")
    write(folder, ".specs/roadmap.yaml", "vision: x\nmilestones:\n  - id: M1\n    title: M\n    outcome: o\n"
          "    features:\n      - id: F1.1\n        title: Template\n        goal: g\n        done_when: d\n"
          "        blocked_by: []\n")
    assert run(folder, "sync") == 0
    road = load(folder, ".specs/roadmap.yaml")
    assert road["milestones"][0]["status"] == "building"
    assert road["milestones"][0]["features"][0]["status"] == "building"


def test_a_decided_decision_cannot_be_decided_again(folder):
    before = text(folder, "decisions/D-01-source.yaml")
    assert run(folder, "decide", "D-01", "--decision", "other", "--why", "z") == 1
    assert text(folder, "decisions/D-01-source.yaml") == before


def test_a_dropped_validation_cannot_be_run(folder):
    assert run(folder, "validate", "V-01", "--status", "dropped", "--evidence", "Gone.") == 0
    assert run(folder, "validate", "V-01", "--status", "passed", "--evidence", "Seen.") == 1
    assert load(folder, "validations/V-01-published.yaml")["status"] == "dropped"


def test_a_closed_pending_item_cannot_be_closed_again(folder):
    run(folder, "new", "pending", "--with", "ana", "--action", "Ask")
    assert run(folder, "close", "P-1") == 0
    assert run(folder, "close", "P-1", "--status", "dropped") == 1
    assert load(folder, "pending.yaml")[0]["status"] == "done"


def test_validate_replaces_attachments_written_as_an_unindented_list(folder):
    path = "validations/V-01-published.yaml"
    write(folder, "validations/evidence/new.png", "png")
    write(folder, path, text(folder, path) + "attachments:\n- old.png\n- older.png\n")
    assert run(folder, "validate", "V-01", "--status", "passed", "--evidence", "Seen.", "--attach", "new.png") == 0
    assert load(folder, path)["attachments"] == ["new.png"]


# ---------------------------------------------------------------- the generated blocks of the brief

HAND = "---\ncode: BRIEF\ndate: 2026-11-12\n---\n\n# b\n" + requirements(REQUIREMENTS) + "\n## BRIEF-3 Path\n\nSteps.\n\n## BRIEF-4 Open items\n\n- Follow-up by hand.\n"


def block_of(root):
    return status.generated_block(text(root, "brief.md"), "open-items")


def test_open_items_block_follows_decisions_and_pending(folder):
    write(folder, "brief.md", HAND)
    assert run(folder, "new", "pending", "--with", "PO,me", "--action", "Ask for the snapshot") == 0
    assert block_of(folder) == "**PO**\n- P-1 (pending) Ask for the snapshot\n\n**me**\n- P-1 (pending) Ask for the snapshot"
    assert run(folder, "new", "decision", "lock", "--title", "Lock", "--question", "Which?",
               "--born-from", "D-01", "--discuss-with", "me") == 0
    assert block_of(folder) == ("**PO**\n- P-1 (pending) Ask for the snapshot\n\n"
                                "**me**\n- D-02 (open) Lock\n- P-1 (pending) Ask for the snapshot")
    assert run(folder, "new", "validation", "lock", "--title", "Lock holds", "--how", "Two clones",
               "--expected", "Second fails", "--decides", "D-02") == 0
    assert "- D-02 (open) Lock - awaiting spike V-02" in block_of(folder)
    assert run(folder, "decide", "D-02", "--decision", "A file lock", "--proposed") == 0
    assert "- D-02 (proposed) Lock - awaiting spike V-02" in block_of(folder)
    assert run(folder, "validate", "V-02", "--status", "passed", "--evidence", "Seen") == 0
    assert run(folder, "decide", "D-02", "--decision", "A file lock", "--why", "Spike V-02") == 0
    assert run(folder, "close", "P-1") == 0
    assert block_of(folder) == status.NOTHING_OPEN


def test_open_items_block_is_inserted_under_brief_4(folder):
    write(folder, "brief.md", HAND)
    assert run(folder, "sync") == 0
    assert text(folder, "brief.md") == HAND.replace(
        "## BRIEF-4 Open items\n\n",
        "## BRIEF-4 Open items\n\n<!-- task:generated open-items -->\n%s\n<!-- /task:generated -->\n\n"
        % status.NOTHING_OPEN)
    before = text(folder, "brief.md")
    assert run(folder, "sync") == 0
    assert text(folder, "brief.md") == before


def test_open_items_sync_keeps_the_hand_text_byte_for_byte(folder):
    head = HAND.replace("\n", "\r\n").replace("Steps.", "Steps é não.  ") + "\r\n"
    tail = "\r\n\r\nNotes out of scope, no final newline"
    stale = "<!-- task:generated open-items -->\r\n**x**\r\n- D-09 (open) gone\r\n<!-- /task:generated -->"
    (folder / "brief.md").write_bytes((head + stale + tail).encode("utf-8"))
    assert run(folder, "new", "pending", "--with", "PO", "--action", "Ask") == 0
    data = (folder / "brief.md").read_bytes().decode("utf-8")
    assert data.startswith(head) and data.endswith(tail)
    assert data[len(head):len(data) - len(tail)] == (
        "<!-- task:generated open-items -->\r\n**PO**\r\n- P-1 (pending) Ask\r\n<!-- /task:generated -->")


def test_open_items_without_brief_4_heading_or_brief(folder, capsys):
    no_heading = HAND.split("## BRIEF-4")[0]
    write(folder, "brief.md", no_heading)
    assert run(folder, "sync") == 1
    assert text(folder, "brief.md") == no_heading
    assert "FAIL: brief.md: no BRIEF-4 heading to hold the open-items block" in capsys.readouterr().out
    (folder / "brief.md").unlink()
    assert run(folder, "sync") == 0
    assert not (folder / "brief.md").exists()


def test_open_items_block_is_inserted_with_the_brief_line_endings(folder):
    crlf = HAND.replace("\n", "\r\n")
    (folder / "brief.md").write_bytes(crlf.encode("utf-8"))
    assert run(folder, "sync") == 0
    assert (folder / "brief.md").read_bytes().decode("utf-8") == crlf.replace(
        "## BRIEF-4 Open items\r\n\r\n",
        "## BRIEF-4 Open items\r\n\r\n<!-- task:generated open-items -->\r\n%s\r\n<!-- /task:generated -->\r\n\r\n"
        % status.NOTHING_OPEN)


def test_open_items_block_is_inserted_under_a_heading_at_the_end(folder):
    head = HAND.split("## BRIEF-4")[0]
    (folder / "brief.md").write_bytes((head + "## BRIEF-4 Open items").encode("utf-8"))
    assert run(folder, "sync") == 0
    assert text(folder, "brief.md") == (head + "## BRIEF-4 Open items\n\n<!-- task:generated open-items -->\n%s\n"
                                        "<!-- /task:generated -->\n" % status.NOTHING_OPEN)


def test_open_items_markers_on_one_line_are_rewritten(folder):
    write(folder, "brief.md", HAND.replace("- Follow-up by hand.\n",
                                           "<!-- task:generated open-items --><!-- /task:generated -->\n"))
    assert run(folder, "sync") == 0
    assert block_of(folder) == status.NOTHING_OPEN
    assert text(folder, "brief.md").endswith(
        "<!-- task:generated open-items -->\n%s\n<!-- /task:generated -->\n" % status.NOTHING_OPEN)


def requirements_of(root):
    return status.generated_block(text(root, "brief.md"), "requirements")


def test_requirements_block_follows_acs(folder):
    write(folder, "brief.md", HAND)
    write(folder, "acs.yaml", ACS + "- id: X-1\n  text: \"Beyond the base text\"\n  requirements:\n"
          "    - id: X-1.1\n      text: \"kept\"\n      decision: D-01\n      validations: [V-01]\n")
    assert run(folder, "sync") == 0
    assert requirements_of(folder) == REQUIREMENTS + "\n- **X-1** Beyond the base text\n  - X-1.1 (D-01) kept"
    write(folder, "acs.yaml", ACS.replace("a separate template exists", "a template exists"))
    assert run(folder, "new", "pending", "--with", "PO", "--action", "Ask") == 0
    assert requirements_of(folder) == REQUIREMENTS.replace("a separate template exists", "a template exists")


def test_requirements_block_is_inserted_under_brief_2(folder):
    synced = HAND.replace("## BRIEF-4 Open items\n\n", "## BRIEF-4 Open items\n\n" + open_items(status.NOTHING_OPEN)
                          .split("\n\n", 1)[1] + "\n")
    bare = synced.replace(requirements(REQUIREMENTS), "\n## BRIEF-2 Target\n\nWhere it departs, by hand.\n")
    write(folder, "brief.md", bare)
    assert run(folder, "sync") == 0
    assert text(folder, "brief.md") == synced.replace(
        "<!-- /task:generated -->\n\n## BRIEF-3", "<!-- /task:generated -->\n\nWhere it departs, by hand.\n\n## BRIEF-3", 1)
    crlf = bare.replace("\n", "\r\n")
    (folder / "brief.md").write_bytes(crlf.encode("utf-8"))
    assert run(folder, "sync") == 0
    data = (folder / "brief.md").read_bytes().decode("utf-8")
    assert data == crlf.replace("## BRIEF-2 Target\r\n\r\n", "## BRIEF-2 Target\r\n\r\n<!-- task:generated requirements -->\r\n"
                                + REQUIREMENTS.replace("\n", "\r\n") + "\r\n<!-- /task:generated -->\r\n\r\n")


def test_requirements_without_brief_2_heading(folder, capsys):
    no_heading = HAND.replace(requirements(REQUIREMENTS), "").replace("- Follow-up by hand.\n", "")
    write(folder, "brief.md", no_heading)
    assert run(folder, "sync") == 1
    assert requirements_of(folder) is None and "## BRIEF-2" not in text(folder, "brief.md")
    assert status.generated_block(text(folder, "brief.md"), "open-items") == status.NOTHING_OPEN
    assert "FAIL: brief.md: no BRIEF-2 heading to hold the requirements block" in capsys.readouterr().out


def test_sync_never_deletes_text_after_a_block_without_its_end_marker(folder, capsys):
    broken = HAND.replace("<!-- /task:generated -->\n\n## BRIEF-3", "\nBy hand.\n\n## BRIEF-3", 1)
    broken = broken.replace("- Follow-up by hand.\n", open_items(status.NOTHING_OPEN).split("\n\n", 1)[1])
    write(folder, "brief.md", broken)
    assert run(folder, "sync") == 1
    assert text(folder, "brief.md") == broken
    assert "FAIL: brief.md: block requirements has no end marker (fix it by hand)" in capsys.readouterr().out


def test_sync_inserts_both_blocks_into_a_brief_with_neither(folder):
    bare = HAND.replace(requirements(REQUIREMENTS), "\n## BRIEF-2 Target\n")
    want = HAND.replace("## BRIEF-4 Open items\n\n", "## BRIEF-4 Open items\n\n" + open_items(status.NOTHING_OPEN)
                        .split("\n\n", 1)[1] + "\n")
    for nl in ("\n", "\r\n"):
        (folder / "brief.md").write_bytes(bare.replace("\n", nl).encode("utf-8"))
        assert run(folder, "sync") == 0
        assert (folder / "brief.md").read_bytes().decode("utf-8") == want.replace("\n", nl)
