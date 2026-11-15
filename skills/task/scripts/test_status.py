"""Tests for status.py. Run: python -m pytest <skill-dir>/scripts -q"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ACS = """\
- id: AC-1
  text: "The build produces a template."
  requirements:
    - id: AC-1.1
      text: "a separate template exists"
      decision: D-01
      validations: [V-01]
"""

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
    outcome: o
    features:
      - id: F1.2
        title: Name step
        goal: g
        done_when: d
        decisions: [D-02]
        blocked_by: []
"""


def test_spike_proves_no_requirement_and_raises_no_warning(task):
    write(task, "decisions/D-02-name.yaml", D02.replace("status: open", "status: proposed"))
    write(task, "validations/V-02-spike.yaml", SPIKE)
    t = loaded(task)
    assert not t.failures
    assert not any("V-02" in w for w in t.warnings)
    write(task, "acs.yaml", ACS.replace("validations: [V-01]", "validations: [V-01, V-02]"))
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
    assert run(task, "--gate", "spec", "--feature", "F1.2") == 1
    assert "F1.2 waits for spike V-02, which decides D-02" in capsys.readouterr().out
    write(task, "validations/V-02-spike.yaml",
          SPIKE.replace("status: pending", "status: passed\ndate: 2026-11-13\nevidence: |\n  Path A works."))
    write(task, "decisions/D-02-name.yaml",
          D02.replace("status: open", "status: decided") + "decision: |\n  A.\nwhy: |\n  V-02 passed.\n")
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
    assert capsys.readouterr().out.strip() == "acs.yaml:4"


def test_find_unknown_id_fails(task, capsys):
    assert run(task, "--find", "D-99") == 1
    assert "D-99 is not defined" in capsys.readouterr().out
