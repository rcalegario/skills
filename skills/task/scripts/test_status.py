"""Tests for status.py. Run: python -m pytest <skill-dir>/scripts -q"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ACS = """\
- id: AC-1
  text: "The build produces a template."
  status: decided
  requirements:
    - id: AC-1.1
      text: "a separate template exists"
      status: decided
      decision: D-01
      validations: [V-01]
"""

DECIDING = ACS.replace("status: decided", "status: deciding")   # while a child decision is open

D01 = """\
id: D-01
title: "Where the template comes from"
status: decided
date: 2026-11-12
born_from: []
discuss_with: [PO]
question: |
  Which build makes it?
decision: |
  The base build.
why: |
  - Simplest.
options:
  - name: "Base build"
    status: chosen
"""

D02 = """\
id: D-02
title: "Template name"
status: open
born_from: [D-01]
discuss_with: [team]
question: |
  Which prefix?
"""

V01 = """\
id: V-01
title: "Template published"
status: pending
how: |
  Look in vCenter.
"""

FEATURE = """\
id: F1.1-template
title: Template
size: M
status: {status}
story:
  decisions: [D-01]
  validations: [V-01]
"""


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def task(tmp_path):
    write(tmp_path, "acs.yaml", ACS)
    write(tmp_path, "decisions/D-01-source.yaml", D01)
    write(tmp_path, "validations/V-01-published.yaml", V01)
    write(tmp_path, "journal.yaml", "- id: J-001\n  date: 2026-11-12\n  type: decision\n  text: x\n  refs: [D-01]\n")
    write(tmp_path, "pending.yaml", "[]\n")
    return tmp_path


def run(root, *args):
    return status.main([str(root)] + list(args))


def loaded(root):
    t = status.Task(str(root))
    t.check()
    return t


def test_clean_folder_passes(task, capsys):
    assert run(task) == 0
    out = capsys.readouterr().out
    assert "| AC-1.1 | decided |" in out


def test_open_child_moves_requirement_back_to_deciding(task):
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "acs.yaml", DECIDING)
    t = loaded(task)
    assert t.req_status({"id": "AC-1.1", "decision": "D-01", "validations": ["V-01"]}) == "deciding"
    assert not t.failures


def test_status_climbs_with_feature_done_and_validation_passed(task):
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="building"))
    req = {"id": "AC-1.1", "decision": "D-01", "validations": ["V-01"]}
    assert loaded(task).req_status(req) == "decided"
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="done"))
    assert loaded(task).req_status(req) == "built"
    write(task, "validations/V-01-published.yaml",
          V01.replace("status: pending", "status: passed\ndate: 2026-11-13\nevidence: |\n  Seen."))
    assert loaded(task).req_status(req) == "concluded"


def test_decision_without_code_skips_the_feature_step(task):
    write(task, "decisions/D-01-source.yaml", D01 + "needs_code: false\n")
    assert loaded(task).req_status({"id": "AC-1.1", "decision": "D-01", "validations": ["V-01"]}) == "built"


@pytest.mark.parametrize("rel,text,expected", [
    ("decisions/D-02-name.yaml", D02.replace("born_from: [D-01]", "born_from: []"), "D-02: orphan"),
    ("decisions/D-02-name.yaml", D02.replace("born_from: [D-01]", "born_from: [D-09]"), "cites D-09"),
    ("decisions/D-03-x.yaml", D02, "does not start with its id D-02"),
    ("decisions/D-02-name.yaml", D02.replace("status: open", "status: maybe"), "D-02: status must be"),
    ("decisions/D-02-name.yaml", D02.replace("status: open", "status: superseded"), "superseded needs"),
    ("acs.yaml", ACS.replace("decision: D-01", "decision: [D-01, D-01]"), "it takes one root"),
    ("acs.yaml", ACS.replace("validations: [V-01]", "validations: []"), "requirement without a validation"),
    ("pending.yaml", "- id: P-1\n  with: [PO]\n  action: Ask\n  status: done\n", "P-1: status done needs 'closed'"),
    ("validations/V-01-published.yaml", V01.replace("status: pending", "status: passed"), "needs 'date' and 'evidence'"),
])
def test_failures(task, rel, text, expected):
    write(task, rel, text)
    assert any(expected in f for f in loaded(task).failures), loaded(task).failures


def test_cycle_in_born_from(task):
    write(task, "decisions/D-01-source.yaml", D01.replace("born_from: []", "born_from: [D-02]"))
    write(task, "decisions/D-02-name.yaml", D02)
    assert any("cycle" in f for f in loaded(task).failures)


def test_context_section_ids_are_known(task):
    write(task, "context/now.md", "---\ncode: NOW\n---\n\n## NOW-1 Firewall\n\n### NOW-1.2 Docker\n")
    write(task, "decisions/D-01-source.yaml", D01 + "context: [NOW-1.2]\n")
    assert not loaded(task).failures
    write(task, "decisions/D-01-source.yaml", D01 + "context: [NOW-7]\n")
    assert any("cites NOW-7" in f for f in loaded(task).failures)


def test_gate_plan_blocks_open_and_warns_proposed(task, capsys):
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "acs.yaml", DECIDING)
    assert run(task, "--gate", "plan") == 1
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    assert run(task, "--gate", "plan") == 0
    assert "D-02 is proposed" in capsys.readouterr().out


def test_gate_pr_needs_concluded_or_pr_note(task):
    assert run(task, "--gate", "pr") == 1
    write(task, "acs.yaml", ACS.replace('  text: "The build', '  pr_note: |\n    Proven in the E2E.\n  text: "The build'))
    assert run(task, "--gate", "pr") == 0


def test_pr_notes_skip_inactive_decisions(task, capsys):
    write(task, "decisions/D-01-source.yaml", D01 + "pr_note: |\n  Uses the base build.\n")
    write(task, "decisions/D-02-name.yaml",
          D02.replace("status: open", "status: dropped") + "pr_note: |\n  Old note.\n")
    assert run(task, "--pr-notes") == 0
    out = capsys.readouterr().out
    assert "Uses the base build." in out and "Old note." not in out


def test_agenda_groups_open_items_by_person(task, capsys):
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "pending.yaml", "- id: P-1\n  with: [payments-api]\n  action: Share the script\n  refs: [D-01]\n  status: open\n")
    run(task)
    out = capsys.readouterr().out
    assert "**team**\n- D-02 (open)" in out
    assert "**payments-api**\n- P-1 (pending) Share the script" in out


README = """\
---
id: metrics-base-image
repos:
  - name: iac
    origin: ~/projects/iac
    worktree: repos/iac
    branch: feat/metrics-base-image
---

# metrics-base-image
"""


def test_feature_repo_must_be_in_readme(task):
    write(task, "README.md", README)
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="building") + "repo: other\n")
    assert any("repo 'other' is not in the README repos" in f for f in loaded(task).failures)
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="building") + "repo: iac\n")
    assert not loaded(task).failures


def test_worktree_contents_are_not_scanned(task):
    write(task, "repos/iac/docs/notes.md", "See D-99 and AC-42.\n")
    assert not loaded(task).failures


SPIKE = """\
id: V-02
title: "Spike: which build path"
status: pending
where: clone
decides: [D-02]
how: |
  Try both paths.
"""

ROADMAP = """\
vision: x
milestones:
  - id: M1
    title: M
    status: planned
    outcome: o
    features:
      - id: F1.2
        title: Name step
        status: planned
        goal: g
        done_when: d
        decisions: [D-02]
        blocked_by: []
"""


def test_spike_proves_no_requirement_and_raises_no_warning(task):
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    write(task, "acs.yaml", DECIDING)
    t = loaded(task)
    assert not t.failures
    assert not any("V-02" in w for w in t.warnings)
    write(task, "acs.yaml", DECIDING.replace("validations: [V-01]", "validations: [V-01, V-02]"))
    assert any("lists spike V-02" in f for f in loaded(task).failures)


def test_spike_must_name_existing_decision(task):
    write(task, "validations/V-02-spike.yaml", SPIKE)
    assert any("decides D-02, which does not exist" in f for f in loaded(task).failures)


@pytest.mark.parametrize("spike_status,blocked", [("pending", True), ("failed", True), ("passed", False)])
def test_decision_cannot_be_decided_before_its_spike(task, spike_status, blocked):
    decided = D02.replace("status: open", "status: decided") + "decision: |\n  x\nwhy: |\n  V-02.\n"
    write(task, "decisions/D-02-name.yaml", decided)
    extra = "\ndate: 2026-11-13\nevidence: |\n  Ran.\n" if spike_status != "pending" else ""
    write(task, "validations/V-02-spike.yaml", SPIKE.replace("status: pending", "status: " + spike_status + extra))
    assert any("decided while spike V-02" in f for f in loaded(task).failures) == blocked


def test_report_lists_spikes_and_agenda_waits(task, capsys):
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    write(task, ".specs/roadmap.yaml", ROADMAP)
    run(task)
    out = capsys.readouterr().out
    assert "| V-02 | pending | clone | D-02 | F1.2 |" in out
    assert "- D-02 (proposed) Template name - awaiting spike V-02" in out


def test_gate_spec_blocks_feature_until_spike_passes(task, capsys):
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    write(task, ".specs/roadmap.yaml", ROADMAP)
    write(task, "acs.yaml", DECIDING)
    assert run(task, "--gate", "spec", "--feature", "F1.2") == 1
    assert "F1.2 waits for spike V-02, which decides D-02" in capsys.readouterr().out
    write(task, "validations/V-02-spike.yaml",
          SPIKE.replace("status: pending", "status: passed\ndate: 2026-11-13\nevidence: |\n  Path A works."))
    write(task, "decisions/D-02-name.yaml",
          D02.replace("status: open", "status: decided") + "decision: |\n  A.\nwhy: |\n  V-02 passed.\n")
    write(task, "acs.yaml", ACS)
    assert run(task, "--gate", "spec", "--feature", "F1.2") == 0


def test_gate_spec_reads_story_decisions_and_unknown_feature(task, capsys):
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, ".specs/features/F1.1-template/feature.yaml",
          FEATURE.format(status="specifying").replace("decisions: [D-01]", "decisions: [D-01, D-02]"))
    assert run(task, "--gate", "spec", "--feature", "F1.1") == 1
    assert "F1.1 links D-02, which is open" in capsys.readouterr().out
    assert run(task, "--gate", "spec", "--feature", "F9.9") == 1
    assert "F9.9 is neither in the roadmap" in capsys.readouterr().out


def test_note_ids_are_not_task_ids(task):
    write(task, "context/now.md", "---\ncode: NOW\n---\n\n## NOW-1 Build\n\nStep N-1 of the vendor guide.\n")
    assert run(task) == 0


def test_find_prints_where_an_id_is_defined(task, capsys):
    write(task, "context/now.md", "---\ncode: NOW\n---\n\n## NOW-1 Firewall\n\n### NOW-1.2 Docker\n")
    assert run(task, "--find", "NOW-1.2") == 0
    assert capsys.readouterr().out.strip() == "context/now.md:7"
    assert run(task, "--find", "NOW-1") == 0
    assert capsys.readouterr().out.strip() == "context/now.md:5"
    assert run(task, "--find", "D-01") == 0
    assert capsys.readouterr().out.strip() == "decisions/D-01-source.yaml:1"
    assert run(task, "--find", "AC-1.1") == 0
    assert capsys.readouterr().out.strip() == "acs.yaml:5"


def test_find_prints_every_definition(task, capsys):
    write(task, ".specs/features/F1.1-a/feature.yaml", "tasks:\n  - id: T1\n")
    write(task, ".specs/features/F1.2-b/feature.yaml", "tasks:\n  - id: T1\n")
    assert run(task, "--find", "T1") == 0
    assert capsys.readouterr().out.split() == [".specs/features/F1.1-a/feature.yaml:2",
                                               ".specs/features/F1.2-b/feature.yaml:2"]


def test_find_skips_the_checks(task, capsys):
    write(task, "README.md", "see D-77\n")
    assert run(task, "--find", "D-01") == 0
    assert capsys.readouterr().out.strip() == "decisions/D-01-source.yaml:1"


def test_find_unknown_id_fails(task, capsys):
    assert run(task, "--find", "D-99") == 1
    assert capsys.readouterr().out.strip() == "D-99 is not defined"


MAIN_README = README.replace("    branch: feat/metrics-base-image\n", "    branch: feat/metrics-base-image\n    main: true\n")


def test_legacy_readme_without_main_only_warns(task):
    write(task, "README.md", README)
    t = loaded(task)
    assert not t.failures
    assert any("no main repo" in w for w in t.warnings)


def test_main_repo_must_be_one_and_name_the_parent_folder(tmp_path):
    root = tmp_path / "iac" / "2026-11-15-1430-metrics-base-image"
    write(root, "README.md", MAIN_README)
    assert not loaded(root).failures
    wrong = tmp_path / "other" / "2026-11-15-1430-metrics-base-image"
    write(wrong, "README.md", MAIN_README)
    assert any("main repo 'iac'" in f for f in loaded(wrong).failures)
    two = MAIN_README.replace("---\n\n#", "  - name: api\n    origin: ~/projects/api\n    worktree: null\n    main: true\n---\n\n#")
    write(root, "README.md", two)
    assert any("exactly one main repo" in f for f in loaded(root).failures)


def test_dated_folder_name_is_checked(tmp_path):
    root = tmp_path / "iac" / "metrics-base-image"
    write(root, "README.md", MAIN_README)
    assert any("YYYY-MM-DD-HHMM-<slug>" in f for f in loaded(root).failures)


# ---------------------------------------------------------------- stored status

def failures(root):
    return loaded(root).failures


def test_requirement_and_item_need_a_stored_status(task):
    write(task, "acs.yaml", ACS.replace("      status: decided\n", ""))
    assert any("AC-1.1: no status" in f for f in failures(task))
    write(task, "acs.yaml", ACS.replace("  status: decided\n  requirements", "  requirements"))
    assert any("AC-1: no status" in f for f in failures(task))


def test_stored_status_must_match_the_computed_one(task):
    write(task, "acs.yaml", ACS.replace("      status: decided", "      status: concluded"))
    fails = failures(task)
    assert any("AC-1.1: status is concluded but" in f and "decided" in f and "task.py sync" in f for f in fails)


def test_stored_item_status_follows_its_requirements(task):
    write(task, "acs.yaml", ACS.replace("  status: decided\n  requirements", "  status: built\n  requirements"))
    assert any("AC-1: status is built but" in f for f in failures(task))


def test_stored_status_must_be_a_known_one(task):
    write(task, "acs.yaml", ACS.replace("      status: decided", "      status: finished"))
    assert any("AC-1.1: status must be one of" in f for f in failures(task))


def test_dropped_item_needs_no_computed_status(task):
    write(task, "acs.yaml", ACS + "\n- id: X-1\n  text: extra\n  status: dropped\n  requirements: []\n")
    assert not failures(task)


def test_status_follows_the_decisions_in_the_stored_file(task):
    write(task, "decisions/D-02-name.yaml", D02)
    assert any("AC-1.1: status is decided but" in f and "deciding" in f for f in failures(task))


ROAD = """\
vision: x
milestones:
  - id: M1
    title: M
    status: {m}
    outcome: o
    features:
      - id: F1.1
        title: Template
        status: {f}
        goal: g
        done_when: d
        blocked_by: []
"""


def test_roadmap_status_must_match_the_features(task):
    write(task, ".specs/features/F1.1-template/feature.yaml", (FEATURE + "roadmap: F1.1\n").format(status="building"))
    write(task, ".specs/roadmap.yaml", ROAD.format(m="building", f="building"))
    assert not failures(task)
    write(task, ".specs/roadmap.yaml", ROAD.format(m="building", f="planned"))
    assert any("F1.1: roadmap status is planned but" in f and "building" in f for f in failures(task))
    write(task, ".specs/roadmap.yaml", ROAD.format(m="planned", f="building"))
    assert any("M1: roadmap status is planned but" in f and "building" in f for f in failures(task))


def test_roadmap_without_status_fails(task):
    write(task, ".specs/roadmap.yaml", ROAD.format(m="planned", f="planned").replace("    status: planned\n", "", 1))
    assert any("M1: no roadmap status" in f for f in failures(task))


# ------------------------------------------------------------ collect, --json, missing

def json_of(root, capsys):
    rc = run(root, "--json")
    return rc, json.loads(capsys.readouterr().out)


def req_of(data, rid):
    return next(r for r in data["requirements"] if r["id"] == rid)


def test_json_output_has_every_key_and_same_exit(task, capsys):
    rc, data = json_of(task, capsys)
    assert rc == 0
    assert set(data) == {"task", "step", "items", "requirements", "features", "roadmap",
                         "spikes", "agenda", "warnings", "failures"}
    assert data["items"][0]["id"] == "AC-1" and data["items"][0]["status"] == "decided"
    assert req_of(data, "AC-1.1")["status"] == "decided"
    write(task, "acs.yaml", ACS.replace("      status: decided\n", ""))
    rc, data = json_of(task, capsys)
    assert rc == 1
    assert any("AC-1.1: no status" in f for f in data["failures"])


def test_missing_names_what_blocks_each_status(task, capsys):
    # decided: D-01 needs code and no feature links it
    _, data = json_of(task, capsys)
    assert req_of(data, "AC-1.1")["missing"] == [
        {"kind": "feature", "id": None, "status": None, "who": [], "awaits": [], "text": "D-01 needs code and no feature links it"}]
    # decided: the linked feature is not done
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="building"))
    _, data = json_of(task, capsys)
    assert req_of(data, "AC-1.1")["missing"] == [
        {"kind": "feature", "id": "F1.1-template", "status": "building", "who": [], "awaits": [], "text": "F1.1-template is building"}]
    # built: the validation has not passed
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="done"))
    write(task, "acs.yaml", ACS.replace("status: decided", "status: built"))
    _, data = json_of(task, capsys)
    assert req_of(data, "AC-1.1")["missing"] == [
        {"kind": "validation", "id": "V-01", "status": "pending", "who": [], "awaits": [], "text": "V-01 is pending"}]
    # concluded: nothing
    write(task, "validations/V-01-published.yaml", V01.replace("status: pending", "status: passed"))
    write(task, "acs.yaml", ACS.replace("status: decided", "status: concluded"))
    _, data = json_of(task, capsys)
    assert req_of(data, "AC-1.1")["missing"] == []
    # deciding: the open child, with who decides and the spike it awaits
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    write(task, "acs.yaml", DECIDING)
    _, data = json_of(task, capsys)
    assert req_of(data, "AC-1.1")["missing"] == [
        {"kind": "decision", "id": "D-02", "status": "proposed", "who": ["team"], "awaits": ["V-02"],
         "text": "D-02 is proposed (team), awaiting spike V-02"}]
    # discovery: no validation
    write(task, "acs.yaml", DECIDING.replace("      validations: [V-01]\n", "").replace("status: deciding", "status: discovery"))
    _, data = json_of(task, capsys)
    assert {"kind": "validation", "id": None, "status": None, "who": [], "awaits": [], "text": "no validation"} \
        in req_of(data, "AC-1.1")["missing"]


def test_report_missing_column(task, capsys):
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="building"))
    run(task)
    out = capsys.readouterr().out
    assert "| Requirement | Status | Root | Children | Not decided | Validations | Missing |" in out
    assert "| AC-1.1 | decided | D-01 | - | - | V-01 (pending) | F1.1-template is building |" in out
    write(task, ".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="done"))
    write(task, "validations/V-01-published.yaml", V01.replace("status: pending", "status: passed"))
    write(task, "acs.yaml", ACS.replace("status: decided", "status: concluded"))
    run(task)
    assert "| AC-1.1 | concluded | D-01 | - | - | V-01 (passed) | - |" in capsys.readouterr().out


# ------------------------------------------------------------ step

BRIEF = "---\ncode: BRIEF\ntitle: b\ndate: {date}\n---\n\n# b\n"
README_WT = README.replace("name: iac", "name: skills").replace("worktree: repos/iac", "worktree: {wt}")


def stamp(root, date="2026-11-12", **groups):
    """Write a brief stamped with the task's current sources, a group overridden by a keyword."""
    digest = dict(status.sources_digest(str(root)), **groups)
    sources = "".join("  %s: \"%s\"\n" % (g, digest[g]) for g in status.SOURCE_GROUPS)
    write(root, "brief.md", BRIEF.format(date=date).replace("---\n\n#", "sources:\n%s---\n\n#" % sources))


def full_step(root):
    return loaded(root).step()


def step_of(root):
    """The step and its reason, as the CLI words them."""
    st = full_step(root)
    return {"step": st["step"], "reason": st["reason"]}


def blockers_of(root):
    return [(b["id"], b["kind"], b["state"]) for b in full_step(root)["blockers"]]


def at_build(task):
    """A task past consolidate and plan, with feature F1.1 building."""
    stamp(task)
    write(task, ".specs/roadmap.yaml", ROAD.format(m="building", f="building"))
    write(task, ".specs/features/F1.1-template/feature.yaml", (FEATURE + "roadmap: F1.1\nrepo: skills\n").format(status="building"))
    write(task, "README.md", README_WT.format(wt="repos/skills"))


def test_step_follows_the_resume_order(task):
    assert step_of(task) == {"step": "consolidate", "reason": "no brief.md"}
    assert blockers_of(task) == [("brief.md", "brief", "missing")]
    write(task, "brief.md", BRIEF.format(date="2026-11-12"))
    assert step_of(task) == {"step": "consolidate", "reason": "brief.md has no sources"}
    assert blockers_of(task) == [("brief.md", "brief", "no-sources")]
    stamp(task)
    assert step_of(task) == {"step": "plan", "reason": "no .specs/roadmap.yaml"}
    assert blockers_of(task) == [("roadmap.yaml", "roadmap", "missing")]
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "acs.yaml", DECIDING)
    assert step_of(task) == {"step": "decide", "reason": "D-02 is open"}
    assert blockers_of(task) == [("D-02", "decision", "open")]
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    write(task, ".specs/roadmap.yaml", ROADMAP)
    assert step_of(task) == {"step": "consolidate", "reason": "decisions changed after brief.md"}
    assert blockers_of(task) == [("decisions", "source", "changed")]
    stamp(task)
    assert step_of(task) == {"step": "spike", "reason": "V-02 blocks F1.2"}
    assert blockers_of(task) == [("V-02", "spike", "pending")]
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: dropped"))
    write(task, "validations/V-02-spike.yaml", SPIKE.replace("status: pending", "status: dropped"))
    write(task, "acs.yaml", ACS)
    at_build(task)
    assert step_of(task) == {"step": "build", "reason": "F1.1-template is building"}
    assert blockers_of(task) == [("F1.1-template", "feature", "building")]
    write(task, ".specs/features/F1.1-template/feature.yaml", (FEATURE + "roadmap: F1.1\nrepo: skills\n").format(status="done"))
    write(task, ".specs/roadmap.yaml", ROAD.format(m="done", f="done"))
    assert step_of(task) == {"step": "review", "reason": "AC-1 is built and has no pr_note"}
    assert blockers_of(task) == [("AC-1", "item", "built")]
    write(task, "validations/V-01-published.yaml", V01.replace("status: pending", "status: passed"))
    assert step_of(task) == {"step": "pr", "reason": "F1.1-template has no PR"}
    assert blockers_of(task) == [("F1.1-template", "feature", "no-pr")]
    write(task, ".specs/features/F1.1-template/feature.yaml",
          (FEATURE + "roadmap: F1.1\nrepo: skills\npr: https://example.org/pr/1\n").format(status="done"))
    assert step_of(task) == {"step": "finish", "reason": "every feature has a PR; worktrees remain: skills"}
    assert blockers_of(task) == [("skills", "repo", "worktree")]
    write(task, "README.md", README_WT.format(wt="null"))
    assert step_of(task) == {"step": "done", "reason": "no repo has a worktree"}
    assert full_step(task)["blockers"] == [] and turn_of(task) is False


def test_step_skips_decisions_waiting_on_others(task):
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "acs.yaml", DECIDING)
    stamp(task)
    write(task, "pending.yaml", "- id: P-1\n  with: [team]\n  action: Pick the prefix\n  refs: [D-02]\n  status: open\n")
    assert step_of(task)["step"] == "plan"
    write(task, "pending.yaml", "- id: P-1\n  with: [team]\n  action: Pick the prefix\n  refs: [D-02]\n  status: done\n")
    assert step_of(task)["step"] == "decide"
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    stamp(task)
    assert step_of(task)["step"] == "plan"


def waiting_of(root):
    return {b["id"]: b["waiting"] for b in full_step(root)["blockers"]}


def test_blocker_in_open_pending_refs_waits(task):
    at_build(task)
    assert waiting_of(task) == {"F1.1-template": False}
    write(task, "pending.yaml", "- id: P-1\n  with: [team]\n  action: Review it\n  refs: [F1.1-template]\n  status: open\n")
    assert waiting_of(task) == {"F1.1-template": True}
    for closed in ("done", "dropped"):
        write(task, "pending.yaml",
              "- id: P-1\n  with: [team]\n  action: Review it\n  refs: [F1.1-template]\n  status: %s\n" % closed)
        assert waiting_of(task) == {"F1.1-template": False}


def test_decision_proposed_to_others_waits(task):
    write(task, "acs.yaml", DECIDING)
    stamp(task)
    write(task, "decisions/D-02-name.yaml", D02)
    assert waiting_of(task) == {"D-02": False}
    proposed = D02.replace("status: open", "status: proposed")
    write(task, "decisions/D-02-name.yaml", proposed)
    assert waiting_of(task) == {"D-02": True}
    write(task, "decisions/D-02-name.yaml", proposed.replace("discuss_with: [team]", "discuss_with: [team, me]"))
    assert waiting_of(task) == {"D-02": False}
    write(task, "decisions/D-02-name.yaml", proposed.replace("discuss_with: [team]\n", ""))
    assert waiting_of(task) == {"D-02": False}


def pending_on(*refs):
    return "- id: P-1\n  with: [team]\n  action: Run it\n  refs: [%s]\n  status: open\n" % ", ".join(refs)


def test_item_waits_when_all_it_misses_waits(task):
    at_build(task)
    write(task, ".specs/features/F1.1-template/feature.yaml", (FEATURE + "roadmap: F1.1\nrepo: skills\n").format(status="done"))
    write(task, ".specs/roadmap.yaml", ROAD.format(m="done", f="done"))
    assert step_of(task)["step"] == "review"
    assert waiting_of(task) == {"AC-1": False}
    write(task, "pending.yaml", pending_on("V-01"))
    assert waiting_of(task) == {"AC-1": True}
    # a second validation the user still runs keeps the item the user's
    write(task, "acs.yaml", ACS.replace("validations: [V-01]", "validations: [V-01, V-03]"))
    write(task, "validations/V-03-other.yaml", V01.replace("id: V-01", "id: V-03"))
    stamp(task)
    assert step_of(task)["step"] == "review"
    assert waiting_of(task) == {"AC-1": False}
    write(task, "pending.yaml", pending_on("V-01", "V-03"))
    assert waiting_of(task) == {"AC-1": True}
    # below built: a child decision that sits with the team in a pending item
    write(task, "acs.yaml", ACS)
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "pending.yaml", pending_on("D-02"))
    stamp(task)
    assert full_step(task)["blockers"] == [{"id": "AC-1", "kind": "item", "state": "deciding", "waiting": True}]


def turn_of(root):
    """your_turn by the step's rules alone: the fixture's own check failures are cleared first."""
    t = loaded(root)
    t.failures = []
    return t.step()["your_turn"]


def at_done(task):
    """A task past finish: the feature done with its PR, V-01 passed, no worktree, every status written."""
    at_build(task)
    write(task, ".specs/features/F1.1-template/feature.yaml",
          (FEATURE + "roadmap: F1.1\nrepo: skills\npr: https://example.org/pr/1\n").format(status="done"))
    write(task, ".specs/roadmap.yaml", ROAD.format(m="done", f="done"))
    write(task, "validations/V-01-published.yaml", V01.replace("status: pending", "status: passed"))
    write(task, "acs.yaml", ACS.replace("status: decided", "status: concluded"))
    write(task, "README.md", README_WT.format(wt="null"))


def test_your_turn_by_step(task):
    # decide: a decision proposed to others only is not the user's; an open one is
    write(task, "acs.yaml", DECIDING)
    stamp(task)
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    assert step_of(task)["step"] == "decide" and turn_of(task) is False
    write(task, "decisions/D-02-name.yaml", D02)
    assert turn_of(task) is True
    # spike: a spike someone else runs is not the user's
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    write(task, ".specs/roadmap.yaml", ROADMAP)
    stamp(task)
    assert step_of(task)["step"] == "spike" and turn_of(task) is True
    write(task, "pending.yaml", pending_on("V-02"))
    assert turn_of(task) is False
    # build: always the user's, even with the feature in a pending item
    write(task, "pending.yaml", "[]\n")
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: dropped"))
    write(task, "validations/V-02-spike.yaml", SPIKE.replace("status: pending", "status: dropped"))
    write(task, "acs.yaml", ACS)
    at_build(task)
    write(task, "pending.yaml", pending_on("F1.1-template"))
    assert step_of(task)["step"] == "build" and full_step(task)["blockers"][0]["waiting"] is True
    assert turn_of(task) is True
    # review: the validation with the team is not the user's
    write(task, ".specs/features/F1.1-template/feature.yaml", (FEATURE + "roadmap: F1.1\nrepo: skills\n").format(status="done"))
    write(task, ".specs/roadmap.yaml", ROAD.format(m="done", f="done"))
    write(task, "pending.yaml", pending_on("V-01"))
    assert step_of(task)["step"] == "review" and turn_of(task) is False
    write(task, "pending.yaml", "[]\n")
    assert turn_of(task) is True
    # consolidate and plan: always the user's
    write(task, "context/now.md", CONTEXT)
    assert step_of(task)["step"] == "consolidate" and turn_of(task) is True


def test_failure_makes_it_your_turn(task):
    at_done(task)
    assert step_of(task)["step"] == "done" and turn_of(task) is False
    t = loaded(task)
    assert t.failures
    assert t.step()["your_turn"] is True


def test_item_with_nothing_to_wait_on_does_not_wait(task):
    everything = {"D-01", "D-02", "V-01"}
    write(task, "acs.yaml", ACS.replace("      validations: [V-01]\n", ""))
    t = loaded(task)
    assert [m["id"] for m in t.missing(t.items[0]["requirements"][0])] == [None]
    assert t.item_waits("AC-1", everything) is False
    write(task, "acs.yaml", "- id: AC-1\n  text: \"x\"\n  status: discovery\n  requirements: []\n")
    assert loaded(task).item_waits("AC-1", everything) is False


def test_report_first_line_is_the_step(task, capsys):
    run(task)
    assert capsys.readouterr().out.splitlines()[0] == "Step: consolidate - no brief.md"
    _, data = json_of(task, capsys)
    assert data["step"] == {"step": "consolidate", "reason": "no brief.md", "your_turn": True,
                            "blockers": [{"id": "brief.md", "kind": "brief", "state": "missing", "waiting": False}]}


def test_json_step_has_blockers_and_your_turn(task, capsys):
    at_build(task)
    run(task)
    assert capsys.readouterr().out.splitlines()[0] == "Step: build - F1.1-template is building"
    _, data = json_of(task, capsys)
    assert data["step"] == {"step": "build", "reason": "F1.1-template is building", "your_turn": True,
                            "blockers": [{"id": "F1.1-template", "kind": "feature", "state": "building",
                                          "waiting": False}]}


def test_step_blockers_for_an_undated_brief_and_an_unspecd_feature(task):
    write(task, "brief.md", BRIEF.format(date="null"))
    assert step_of(task) == {"step": "consolidate", "reason": "brief.md has no date"}
    assert blockers_of(task) == [("brief.md", "brief", "no-date")]
    stamp(task)
    write(task, ".specs/roadmap.yaml", ROAD.format(m="planned", f="planned"))
    assert step_of(task) == {"step": "build", "reason": "F1.1 is planned"}
    assert blockers_of(task) == [("F1.1", "feature", "planned")]


# ------------------------------------------------------------ sources digest

CONTEXT = "---\ncode: NOW\nread_on: 2026-11-12\n---\n\n## NOW-1 Today\n\nThe build makes it.\n"


def digest_task(task):
    write(task, "context/now.md", CONTEXT)
    return task


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def test_digest_has_one_short_hash_per_group(task):
    digest = status.sources_digest(str(digest_task(task)))
    assert list(digest) == ["context", "acs", "decisions"]
    assert all(len(h) == 12 and int(h, 16) >= 0 for h in digest.values())
    assert status.sources_digest(str(task)) == digest


def test_digest_ignores_what_the_scripts_write(task):
    digest_task(task)
    base = status.sources_digest(str(task))
    write(task, "acs.yaml", ACS.replace("status: decided", "status: concluded"))
    write(task, "decisions/D-01-source.yaml", replace_once(D01, "date: 2026-11-12", "date: 2026-11-20"))
    write(task, "context/now.md", replace_once(CONTEXT, "read_on: 2026-11-12", "read_on: 2026-11-20"))
    write(task, "context/archive/old.md", "frozen\n")
    assert status.sources_digest(str(task)) == base


def test_digest_follows_hand_edits_in_their_own_group_only(task):
    digest_task(task)
    base = status.sources_digest(str(task))
    original = {"context/now.md": CONTEXT, "acs.yaml": ACS, "decisions/D-01-source.yaml": D01}
    edits = [
        ("context/now.md", replace_once(CONTEXT, "The build makes it.", "A second build makes it."), ["context"]),
        ("acs.yaml", replace_once(ACS, "a separate template exists", "a template exists"), ["acs"]),
        ("acs.yaml", replace_once(ACS, "  status: decided\n  requirements", "  status: dropped\n  requirements"), ["acs"]),
        ("decisions/D-01-source.yaml", replace_once(D01, "- Simplest.", "- Cheapest."), ["decisions"]),
        ("decisions/D-01-source.yaml", replace_once(D01, "status: decided", "status: superseded"), ["decisions"]),
        ("decisions/D-01-source.yaml", replace_once(D01, "status: chosen", "status: alternative"), ["decisions"]),
    ]
    for rel, text, groups in edits:
        write(task, rel, text)
        now = status.sources_digest(str(task))
        assert [g for g in base if now[g] != base[g]] == groups, (rel, text)
        write(task, rel, original[rel])


def test_digest_is_stable_across_line_endings_and_yaml_layout(task):
    digest_task(task)
    base = status.sources_digest(str(task))
    for rel, text in [("context/now.md", CONTEXT), ("acs.yaml", ACS), ("decisions/D-01-source.yaml", D01)]:
        (task / rel).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert status.sources_digest(str(task)) == base
    reordered = (
        "options:\n  - status: chosen\n    name:   \"Base build\"\n"
        "why: |\n  - Simplest.\nquestion: |\n  Which build makes it?\ndecision: |\n  The base build.\n"
        "discuss_with: [PO]\nborn_from: []\ndate: 2026-11-12\nstatus: decided\n"
        "title: \"Where the template comes from\"\nid: D-01\n"
    )
    write(task, "decisions/D-01-source.yaml", reordered)
    assert status.sources_digest(str(task)) == base
    reordered_acs = (
        "- requirements:\n"
        "    - validations:   [V-01]\n"
        "      decision: D-01\n"
        "      text:   \"a separate template exists\"\n"
        "      status: decided\n"
        "      id: AC-1.1\n"
        "  status: decided\n"
        "  text:   \"The build produces a template.\"\n"
        "  id: AC-1\n"
    )
    write(task, "acs.yaml", reordered_acs)
    assert status.sources_digest(str(task)) == base


def test_digest_of_a_task_without_context_is_the_hash_of_nothing(task):
    assert status.sources_digest(str(task))["context"] == status._short_hash({})


# ------------------------------------------------------------ step: the brief's sources

def test_step_names_the_groups_that_changed(task):
    write(task, "context/now.md", CONTEXT)
    stamp(task)
    assert step_of(task)["step"] == "plan"
    write(task, "context/now.md", replace_once(CONTEXT, "The build makes it.", "A second build makes it."))
    assert step_of(task) == {"step": "consolidate", "reason": "context changed after brief.md"}
    write(task, "acs.yaml", replace_once(ACS, "a separate template exists", "a template exists"))
    assert step_of(task) == {"step": "consolidate", "reason": "context, acs changed after brief.md"}
    assert blockers_of(task) == [("context", "source", "changed"), ("acs", "source", "changed")]
    write(task, "decisions/D-01-source.yaml", replace_once(D01, "- Simplest.", "- Cheapest."))
    assert step_of(task) == {"step": "consolidate", "reason": "context, acs, decisions changed after brief.md"}
    write(task, "context/now.md", CONTEXT)
    write(task, "acs.yaml", ACS)
    assert step_of(task) == {"step": "consolidate", "reason": "decisions changed after brief.md"}
    stamp(task)
    assert step_of(task)["step"] == "plan"


def test_step_without_a_sources_map_or_group(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12"))
    assert step_of(task) == {"step": "consolidate", "reason": "brief.md has no sources"}
    write(task, "brief.md", BRIEF.format(date="2026-11-12").replace("---\n\n#", "sources: abc123abc123\n---\n\n#"))
    assert step_of(task) == {"step": "consolidate", "reason": "brief.md has no sources"}
    write(task, "brief.md", BRIEF.format(date="2026-11-12").replace("---\n\n#", "sources: {}\n---\n\n#"))
    assert step_of(task) == {"step": "consolidate", "reason": "brief.md has no sources"}
    digest = status.sources_digest(str(task))
    stamp(task)
    text = (task / "brief.md").read_text(encoding="utf-8")
    write(task, "brief.md", text.replace('  acs: "%s"\n' % digest["acs"], ""))
    assert step_of(task) == {"step": "consolidate", "reason": "acs changed after brief.md"}
    stamp(task, decisions="not-a-hash")
    assert step_of(task) == {"step": "consolidate", "reason": "decisions changed after brief.md"}


def test_a_later_decision_date_alone_does_not_decide_the_step(task):
    stamp(task, date="2026-11-11")
    assert step_of(task) == {"step": "plan", "reason": "no .specs/roadmap.yaml"}
    write(task, "decisions/D-01-source.yaml", replace_once(D01, "date: 2026-11-12", "date: 2026-11-20"))
    assert step_of(task)["step"] == "plan"


# ------------------------------------------------------------ obsolete ids in the brief

def superseded(ident, by, born_from="[D-01]"):
    return ("id: %s\ntitle: \"Old\"\nstatus: superseded\nborn_from: %s\nsuperseded_by: %s\n"
            "question: |\n  Which?\ndecision: |\n  Old.\n" % (ident, born_from, by))


def obsolete_task(task):
    """D-02 -> D-03 -> D-04 (active), D-05 dropped."""
    write(task, "decisions/D-02-old.yaml", superseded("D-02", "D-03"))
    write(task, "decisions/D-03-older.yaml", superseded("D-03", "D-04").replace("Old", "Older") + "supersedes: D-02\n")
    write(task, "decisions/D-04-name.yaml", D01.replace("D-01", "D-04").replace("born_from: []", "born_from: [D-01]")
          + "supersedes: D-03\n")
    write(task, "decisions/D-05-gone.yaml", D02.replace("D-02", "D-05").replace("status: open", "status: dropped"))
    return task


def open_items(body):
    return "\n## BRIEF-4 Open items\n\n<!-- task:generated open-items -->\n%s\n<!-- /task:generated -->\n" % body


def current_open_items(task):
    return open_items(status.open_items_block(status.Task(str(task))))


def requirements(body):
    return "\n## BRIEF-2 Target\n\n<!-- task:generated requirements -->\n%s\n<!-- /task:generated -->\n" % body


def current_requirements(task):
    return requirements(status.requirements_block(status.Task(str(task))))


def brief_citing(task, *ids):
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + "\nSee %s.\n" % ", ".join(ids)
          + current_requirements(task) + current_open_items(task))


def brief_failures(task):
    return [f for f in loaded(task).failures if f.startswith("brief.md:")]


def test_obsolete_superseded_decision_names_the_active_one(task):
    obsolete_task(task)
    brief_citing(task, "D-02", "D-03", "D-04")
    assert brief_failures(task) == ["brief.md: cites D-02, superseded by D-04",
                                    "brief.md: cites D-03, superseded by D-04"]


def test_obsolete_ids_outside_the_brief_pass(task):
    obsolete_task(task)
    brief_citing(task, "D-04")
    write(task, "journal.yaml", "- id: J-001\n  date: 2026-11-12\n  type: decision\n  text: D-02 and D-05 went away\n"
          "  refs: [D-02, D-03, D-05]\n")
    write(task, "context/now.md", "---\ncode: NOW\n---\n\n## NOW-1 History\n\nD-02 was superseded; D-05 dropped.\n")
    write(task, "README.md", "# x\n\nOnce D-03.\n")
    assert loaded(task).failures == []


def test_obsolete_check_keeps_the_nonexistent_failure(task):
    obsolete_task(task)
    brief_citing(task, "D-09")
    assert brief_failures(task) == ["brief.md: cites D-09, which does not exist"]


DROPPED_ITEM = ("\n- id: X-1\n  text: extra\n  status: dropped\n  requirements:\n"
                "    - id: X-1.1\n      text: gone\n      decision: D-05\n      validations: [V-01]\n")


def test_obsolete_dropped_decision_or_item(task):
    obsolete_task(task)
    write(task, "acs.yaml", ACS + DROPPED_ITEM)
    brief_citing(task, "D-05", "X-1", "AC-1")
    assert brief_failures(task) == ["brief.md: cites D-05, which is dropped",
                                    "brief.md: cites X-1, which is dropped"]


def test_obsolete_requirement_of_a_dropped_item(task):
    obsolete_task(task)
    write(task, "acs.yaml", ACS + DROPPED_ITEM)
    brief_citing(task, "X-1.1", "AC-1.1")
    assert brief_failures(task) == ["brief.md: cites X-1.1, whose item X-1 is dropped"]


def test_obsolete_superseded_names_no_dead_replacement(task):
    obsolete_task(task)
    write(task, "decisions/D-06-to-gone.yaml", superseded("D-06", "D-05"))
    write(task, "decisions/D-07-loop.yaml", superseded("D-07", "D-08"))
    write(task, "decisions/D-08-loop.yaml", superseded("D-08", "D-07"))
    write(task, "decisions/D-09-dangling.yaml", superseded("D-09", "D-99"))
    brief_citing(task, "D-06", "D-07", "D-09")
    assert brief_failures(task) == ["brief.md: cites D-06, superseded by D-05, which is dropped",
                                    "brief.md: cites D-07, which is superseded",
                                    "brief.md: cites D-09, which is superseded"]


def test_obsolete_leaves_dropped_validations_and_closed_pending_alone(task):
    obsolete_task(task)
    write(task, "validations/V-02-gone.yaml", V01.replace("V-01", "V-02").replace("status: pending", "status: dropped"))
    write(task, "pending.yaml", "- id: P-1\n  with: [PO]\n  action: Ask\n  status: done\n  closed: 2026-11-12\n")
    brief_citing(task, "V-02", "P-1")
    assert brief_failures(task) == []


# ------------------------------------------------------------ the open-items block of the brief

D03_SPIKED = ("id: D-03\ntitle: \"Lock\"\nstatus: proposed\nborn_from: [D-01]\ndiscuss_with: [me]\n"
              "question: |\n  Which lock?\ndecision: |\n  A file lock.\n")
V02_SPIKE = "id: V-02\ntitle: \"Lock holds\"\nstatus: pending\ndecides: [D-03]\nhow: |\n  Two clones.\n"
PENDING = ("- id: P-1\n  with: [PO, me]\n  action: Ask for the snapshot\n  status: open\n\n"
           "- id: P-2\n  with: [PO]\n  action: Old ask\n  status: done\n  closed: 2026-11-12\n")


def busy_task(task):
    write(task, "decisions/D-02-name.yaml", D02)
    write(task, "decisions/D-03-lock.yaml", D03_SPIKED)
    write(task, "validations/V-02-lock.yaml", V02_SPIKE)
    write(task, "pending.yaml", PENDING)
    return task


def test_open_items_block_groups_by_person(task):
    busy_task(task)
    assert status.open_items_block(status.Task(str(task))) == (
        "**PO**\n- P-1 (pending) Ask for the snapshot\n\n"
        "**me**\n- D-03 (proposed) Lock - awaiting spike V-02\n- P-1 (pending) Ask for the snapshot\n\n"
        "**team**\n- D-02 (open) Template name")


def test_open_items_block_when_nothing_is_open(task):
    assert status.open_items_block(status.Task(str(task))) == \
        "None: no decision is open or proposed and no pending item is open."
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + current_requirements(task) + open_items(
        "None: no decision is open or proposed and no pending item is open."))
    assert brief_failures(task) == []


def test_open_items_block_stale_or_missing_fails(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + current_requirements(task)
          + "\n## BRIEF-4 Open items\n\nBy hand.\n")
    assert brief_failures(task) == ["brief.md: no open-items block (run `task.py sync`)"]
    brief_citing(task)
    assert brief_failures(task) == []
    busy_task(task)
    assert brief_failures(task) == ["brief.md: block open-items is stale (run `task.py sync`)"]
    brief_citing(task)
    assert brief_failures(task) == []


def test_open_items_block_is_read_across_line_endings(task):
    busy_task(task)
    brief = BRIEF.format(date="2026-11-12") + current_requirements(task) + current_open_items(task)
    (task / "brief.md").write_bytes(brief.replace("\n", "\r\n").encode("utf-8"))
    assert brief_failures(task) == []


def test_open_items_without_brief_4_heading_fails(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + current_requirements(task) + "\n## BRIEF-3 Path\n")
    assert brief_failures(task) == ["brief.md: no BRIEF-4 heading to hold the open-items block"]
    (task / "brief.md").unlink()
    assert brief_failures(task) == []


def test_open_items_block_lists_a_pending_item_with_nobody_named(task):
    write(task, "pending.yaml", "- id: P-1\n  with: []\n  action: Ask\n  status: open\n")
    assert status.open_items_block(status.Task(str(task))) == "**(nobody named)**\n- P-1 (pending) Ask"


def test_open_items_markers_on_one_line_are_a_stale_block(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + current_requirements(task)
          + "\n## BRIEF-4 Open items\n\n<!-- task:generated open-items --><!-- /task:generated -->\n")
    assert brief_failures(task) == ["brief.md: block open-items is stale (run `task.py sync`)"]


ACS_TWO = ACS + """\
- id: X-1
  text: "Something beyond   the base text"
  status: decided
  requirements:
    - id: X-1.1
      text: "kept"
      status: decided
      decision: D-01
      validations: [V-01]
    - id: X-1.2
      text: "gone"
      status: dropped
      decision: D-01
      validations: [V-01]
- id: X-2
  text: "Dropped item"
  status: dropped
  requirements:
    - id: X-2.1
      text: "gone with its item"
      status: dropped
      decision: D-01
      validations: [V-01]
"""


def test_requirements_block_lists_items_in_acs_order(task):
    write(task, "acs.yaml", ACS_TWO)
    assert status.requirements_block(status.Task(str(task))) == (
        "- **AC-1** The build produces a template.\n"
        "  - AC-1.1 (D-01) a separate template exists\n"
        "- **X-1** Something beyond the base text\n"
        "  - X-1.1 (D-01) kept")


def root_line(task, decision):
    write(task, "acs.yaml", ACS.replace("decision: D-01", decision))
    return status.requirements_block(status.Task(str(task))).split("\n")[1]


def test_requirements_block_names_the_active_root(task):
    obsolete_task(task)
    assert root_line(task, "decision: D-02") == "  - AC-1.1 (D-04) a separate template exists"
    assert root_line(task, "decision: D-05") == "  - AC-1.1 (no active root) a separate template exists"
    write(task, "decisions/D-06-gone.yaml", superseded("D-06", "D-05"))
    assert root_line(task, "decision: D-06") == "  - AC-1.1 (no active root) a separate template exists"
    assert root_line(task, "validations: [V-01]") == "  - AC-1.1 (no active root) a separate template exists"


def test_requirements_block_when_acs_is_empty(task):
    write(task, "acs.yaml", "[]\n")
    assert status.requirements_block(status.Task(str(task))) == "None: acs.yaml has no requirements."
    write(task, "acs.yaml", "- id: X-2" + ACS_TWO.split("- id: X-2")[1])
    assert status.requirements_block(status.Task(str(task))) == "None: acs.yaml has no requirements."


def test_requirements_block_stale_or_missing_fails(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + "\n## BRIEF-2 Target\n\nBy hand.\n"
          + current_open_items(task))
    assert brief_failures(task) == ["brief.md: no requirements block (run `task.py sync`)"]
    brief_citing(task)
    assert brief_failures(task) == []
    write(task, "acs.yaml", ACS.replace("a separate template exists", "a template exists"))
    assert brief_failures(task) == ["brief.md: block requirements is stale (run `task.py sync`)"]
    brief_citing(task)
    assert brief_failures(task) == []


def test_requirements_without_brief_2_heading_fails(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12") + current_open_items(task))
    assert brief_failures(task) == ["brief.md: no BRIEF-2 heading to hold the requirements block"]


def test_requirements_block_without_its_end_marker_fails(task):
    write(task, "brief.md", BRIEF.format(date="2026-11-12")
          + "\n## BRIEF-2 Target\n\n<!-- task:generated requirements -->\nold\n\nBy hand.\n" + current_open_items(task))
    assert brief_failures(task) == ["brief.md: block requirements has no end marker (fix it by hand)"]


def test_requirements_block_with_a_list_as_decision(task):
    assert root_line(task, "decision: [D-01]") == "  - AC-1.1 (no active root) a separate template exists"


@pytest.mark.parametrize("rel,text,expected", [
    ("decisions/D-02-name.yaml", D02.replace("born_from: [D-01]", "born_from: D-01"),
     "D-02: born_from must be a list ([D-01])"),
    ("decisions/D-02-name.yaml", D02.replace("discuss_with: [team]", "discuss_with: team"),
     "D-02: discuss_with must be a list ([team])"),
    ("validations/V-01-published.yaml", V01 + "decides: D-01\n", "V-01: decides must be a list ([D-01])"),
    ("acs.yaml", ACS.replace("validations: [V-01]", "validations: V-01"),
     "acs.yaml: AC-1.1 validations must be a list ([V-01])"),
    ("pending.yaml", "- id: P-1\n  with: me\n  action: Ask\n  status: pending\n",
     "pending.yaml: P-1 with must be a list ([me])"),
    ("journal.yaml", "- id: J-001\n  date: 2026-11-12\n  type: decision\n  text: x\n  refs: D-01\n",
     "journal.yaml: J-001 refs must be a list ([D-01])"),
    (".specs/features/F1.1-template/feature.yaml", FEATURE.format(status="building").replace("[D-01]", "D-01"),
     "F1.1-template: story.decisions must be a list ([D-01])"),
])
def test_a_single_value_list_field_fails(task, rel, text, expected, capsys):
    write(task, rel, text)
    assert run(task) == 1
    assert expected in loaded(task).failures, loaded(task).failures


def test_absent_or_null_list_field_and_single_id_fields_pass(task):
    write(task, "decisions/D-01-source.yaml", D01.replace("born_from: []", "born_from:").replace("discuss_with: [PO]\n", ""))
    write(task, "decisions/D-02-name.yaml",
          D02.replace("status: open", "status: superseded\ndecision: x\nsuperseded_by: D-01"))
    t = loaded(task)
    assert not [f for f in t.failures if "must be a list" in f], t.failures
    assert t.req_status({"id": "AC-1.1", "decision": "D-01", "validations": ["V-01"]}) == "decided"
