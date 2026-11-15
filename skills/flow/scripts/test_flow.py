"""Tests for flow.py. Run: python -m pytest <skill-dir>/scripts -q"""
import os
import subprocess
import sys

import datetime

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flow  # noqa: E402

FEATURE = """\
id: demo
title: Demo feature
size: M
status: approved   # keep this comment
approved:
  spec: 2026-11-10
  tasks: 2026-11-10
base: abc1234
test: echo suite
acceptance:
  - id: AC1
    text: WHEN X THEN Y happens.
  - id: AC2
    text: WHEN Z THEN W happens.
tasks:
  - id: T1
    title: First
    covers: [AC1]
    blocked_by: []
    verify: echo ok
    commit: "feat: do the first thing"
    status: todo   # task comment
  - id: T2
    title: Second
    covers: [AC2]
    blocked_by: [T1]
    verify: echo ok
    commit: "feat: do the second thing"
    status: todo
checks:
  - ac: AC1
    test: "test_demo.py > first"
    status: pending
  - ac: AC2
    manual: "Click the button and read the message"
    status: pending
"""

SPEC = "# Demo feature\n\n## Problem\n\nSomething hurts.\n"


def git(root, *args):
    subprocess.run(["git"] + list(args), cwd=str(root), check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def write_feature(folder, text=FEATURE, spec=SPEC):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "feature.yaml").write_text(text)
    if spec is not None:
        (folder / "spec.md").write_text(spec)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text(".specs/\n")
    (tmp_path / "code.txt").write_text("v1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    write_feature(tmp_path / ".specs" / "features" / "demo")
    return tmp_path


def commit(root, content):
    (root / "code.txt").write_text(content)
    git(root, "commit", "-qam", "change %s" % content.strip())
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                          stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()


def run(root, *args):
    return flow.main(["--root", str(root)] + list(args))


def feature(root):
    return root / ".specs" / "features" / "demo" / "feature.yaml"


def data(root):
    return yaml.safe_load(feature(root).read_text())


def check_output(root, capsys, text=None):
    if text is not None:
        feature(root).write_text(text)
    capsys.readouterr()
    code = run(root, "check", "demo")
    return code, capsys.readouterr().out


# ---------------------------------------------------------------- check

def test_valid_feature_passes(repo):
    assert run(repo, "check", "demo") == 0


@pytest.mark.parametrize("old,new,expected", [
    ("covers: [AC2]", "covers: [AC1]", "criterion AC2 is not covered"),
    ("blocked_by: [T1]", "blocked_by: [T9]", "unknown task T9"),
    ("blocked_by: []", "blocked_by: [T2]", "cycle"),
    ("status: todo   # task comment", "status: done", "T1 is done without a 'sha'"),
    ("status: todo   # task comment", "status: done\n    sha: deadbee", "not in this repository"),
    ("  spec: 2026-11-10\n", "", "needs approved.spec"),
    ("base: abc1234\n", "", "needs 'base'"),
    ("covers: [AC1]", "covers: [AC7]", "unknown criterion AC7"),
    ("size: M", "size: XL", "'size' must be"),
    ("  - id: AC2\n    text: WHEN Z THEN W happens.", "  - id: AC1\n    text: dup", "acceptance id AC1 is duplicated"),
    ('    commit: "feat: do the first thing"\n', "", "T1 needs a 'commit' message"),
    ("status: todo   # task comment", "status: started", "T1 status must be one of"),
    ("  - ac: AC2\n    manual: \"Click the button and read the message\"\n    status: pending\n", "",
     "criterion AC2 has no check"),
    ("  - ac: AC2\n", "  - ac: AC9\n", "check for unknown criterion AC9"),
    ('    manual: "Click', '    test: "x > y"\n    manual: "Click', "exactly one of 'test' or 'manual'"),
    ("    status: pending\n  - ac: AC2", "    status: ok\n  - ac: AC2", "check AC1 status must be one of"),
    ("test: echo suite\n", "", "'test' (the suite command) is required"),
])
def test_check_rejects(repo, capsys, old, new, expected):
    assert FEATURE.count(old) == 1, old
    code, out = check_output(repo, capsys, FEATURE.replace(old, new))
    assert code == 1
    assert expected in out, out


def test_check_allows_all_manual_checks_without_suite(repo):
    text = FEATURE.replace("test: echo suite\n", "").replace('test: "test_demo.py > first"', 'manual: "Look"')
    feature(repo).write_text(text)
    assert run(repo, "check", "demo") == 0


def test_check_needs_spec_md_once_approved(repo, capsys):
    (feature(repo).parent / "spec.md").unlink()
    code, out = check_output(repo, capsys)
    assert code == 1 and "spec.md" in out


def test_check_rejects_todo_left_in_spec_md(repo, capsys):
    (feature(repo).parent / "spec.md").write_text(SPEC + "\n## Out of scope\n\n- TODO: fill\n")
    code, out = check_output(repo, capsys)
    assert code == 1 and "TODO" in out


def test_check_rejects_finding_without_task_or_reason(repo, capsys):
    text = FEATURE + "review:\n  findings:\n    - text: a\n      action: fix\n    - text: b\n      action: wontfix\n"
    code, out = check_output(repo, capsys, text)
    assert "fix without an existing 'task'" in out
    assert "wontfix without a 'reason'" in out


def test_done_status_needs_every_check_passed(repo, capsys):
    sha1 = commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "done") == 0
    commit(repo, "b\n")
    assert run(repo, "set", "demo", "T2", "done") == 0
    text = feature(repo).read_text().replace("status: building", "status: done") + "review:\n  findings: []\n"
    code, out = check_output(repo, capsys, text)
    assert code == 1 and "check AC1 is pending" in out
    code, out = check_output(repo, capsys, text.replace("status: pending", "status: pass"))
    assert code == 0, out
    assert sha1


# ---------------------------------------------------------------- approve

DRAFT_M = FEATURE.replace("status: approved   # keep this comment", "status: draft   # keep this comment").replace(
    "approved:\n  spec: 2026-11-10\n  tasks: 2026-11-10\nbase: abc1234\n", "")


def head(root):
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                          stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()


def test_approve_m_spec_approves_both_and_records_base(repo):
    feature(repo).write_text(DRAFT_M)
    assert run(repo, "approve", "demo", "spec") == 0
    d = data(repo)
    today = datetime.date.today()
    assert d["approved"] == {"spec": today, "tasks": today}
    assert d["status"] == "approved"
    assert str(d["base"]) == head(repo)
    assert "status: approved   # keep this comment" in feature(repo).read_text()
    assert run(repo, "check", "demo") == 0


def test_approve_m_refuses_tasks_step(repo):
    feature(repo).write_text(DRAFT_M)
    assert run(repo, "approve", "demo", "tasks") == 1
    assert data(repo)["status"] == "draft"


def test_approve_l_in_two_steps(repo):
    draft = DRAFT_M.replace("size: M", "size: L")
    spec_only = draft[:draft.index("tasks:\n")]
    feature(repo).write_text(spec_only)
    assert run(repo, "approve", "demo", "tasks") == 1          # spec first
    assert run(repo, "approve", "demo", "spec") == 0
    d = data(repo)
    assert d["approved"]["spec"] == datetime.date.today() and not d["approved"].get("tasks")
    assert d["status"] == "draft"
    feature(repo).write_text(feature(repo).read_text() + draft[draft.index("tasks:\n"):])
    assert run(repo, "approve", "demo", "tasks") == 0
    d = data(repo)
    assert d["approved"]["tasks"] == datetime.date.today() and d["status"] == "approved"
    assert str(d["base"]) == head(repo)


def test_approve_refuses_when_check_fails(repo, capsys):
    feature(repo).write_text(DRAFT_M.replace("covers: [AC2]", "covers: [AC1]"))
    assert run(repo, "approve", "demo", "spec") == 1
    assert "AC2 is not covered" in capsys.readouterr().out
    assert data(repo)["status"] == "draft"


# ---------------------------------------------------------------- set task

def test_set_doing_moves_feature_to_building(repo):
    assert run(repo, "set", "demo", "T1", "doing") == 0
    d = data(repo)
    assert d["tasks"][0]["status"] == "doing" and d["status"] == "building"
    assert "status: doing   # task comment" in feature(repo).read_text()
    assert run(repo, "check", "demo") == 0


def test_set_done_records_head_keeps_comments_and_moves_to_building(repo):
    sha = commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", "done") == 0
    text = feature(repo).read_text()
    d = yaml.safe_load(text)
    t1 = d["tasks"][0]
    assert t1["status"] == "done" and str(t1["sha"]) == sha
    assert t1["commit"] == "feat: do the first thing"
    assert d["status"] == "building"
    assert "status: building   # keep this comment" in text
    assert "status: done   # task comment" in text
    assert d["tasks"][1]["status"] == "todo"
    assert run(repo, "check", "demo") == 0


def test_set_done_refuses_uncommitted_code(repo):
    (repo / "code.txt").write_text("dirty\n")
    assert run(repo, "set", "demo", "T1", "done") == 1
    assert data(repo)["tasks"][0]["status"] == "todo"


@pytest.mark.parametrize("state", ["doing", "done"])
def test_set_task_refuses_blocked_task(repo, state):
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T2", state) == 1


def test_set_done_refuses_same_commit_twice(repo):
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", "done") == 0
    assert run(repo, "set", "demo", "T2", "done") == 1


@pytest.mark.parametrize("state", ["doing", "done"])
def test_set_task_refuses_before_approval(repo, state):
    feature(repo).write_text(DRAFT_M)
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", state) == 1


def test_set_done_with_explicit_commit_for_resume(repo):
    sha = commit(repo, "v2\n")
    commit(repo, "v3\n")
    assert run(repo, "set", "demo", "T1", "done", "--commit", sha) == 0
    assert str(data(repo)["tasks"][0]["sha"]) == sha


def test_set_rejects_unknown_target_or_value(repo):
    assert run(repo, "set", "demo", "T9", "done") == 1
    assert run(repo, "set", "demo", "T1", "pass") == 1
    assert run(repo, "set", "demo", "AC1", "done") == 1


def test_task_repo_records_and_validates_the_commit_in_that_repo(repo, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    git(other, "init", "-q")
    git(other, "config", "user.email", "t@example.com")
    git(other, "config", "user.name", "t")
    (other / "f.txt").write_text("v1\n")
    git(other, "add", ".")
    git(other, "commit", "-qm", "other init")
    other_sha = commit_in(other, "f.txt", "v2\n")
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", "done") == 0
    text = feature(repo).read_text().replace(
        "    covers: [AC2]\n", "    covers: [AC2]\n    repo: %s\n" % other, 1)
    feature(repo).write_text(text)
    assert run(repo, "set", "demo", "T2", "done", "--commit", other_sha) == 0
    assert str(data(repo)["tasks"][1]["sha"]) == other_sha
    assert run(repo, "check", "demo") == 0


def commit_in(root, name, content):
    (root / name).write_text(content)
    git(root, "commit", "-qam", "change")
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                          stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()


# ---------------------------------------------------------------- set check

def build_all(root):
    commit(root, "a\n")
    assert run(root, "set", "demo", "T1", "done") == 0
    commit(root, "b\n")
    assert run(root, "set", "demo", "T2", "done") == 0


def test_set_check_pass_and_fail(repo):
    build_all(repo)
    assert run(repo, "set", "demo", "AC1", "pass") == 0
    assert run(repo, "set", "demo", "AC2", "fail") == 0
    checks = data(repo)["checks"]
    assert [c["status"] for c in checks] == ["pass", "fail"]
    assert run(repo, "check", "demo") == 0


def test_set_check_refuses_while_covering_task_is_open(repo):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "done") == 0
    assert run(repo, "set", "demo", "AC2", "pass") == 1         # T2 covers AC2 and is open
    assert run(repo, "set", "demo", "AC1", "pass") == 0


# ---------------------------------------------------------------- review and finish

def test_review_needs_every_task_done(repo):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "done") == 0
    assert run(repo, "review", "demo") == 1
    commit(repo, "b\n")
    assert run(repo, "set", "demo", "T2", "done") == 0
    assert run(repo, "review", "demo") == 0
    assert data(repo)["status"] == "review"


def test_finish_refuses_until_checks_pass_and_review_recorded(repo, capsys):
    build_all(repo)
    assert run(repo, "review", "demo") == 0
    assert run(repo, "set", "demo", "AC1", "pass") == 0
    assert run(repo, "finish", "demo") == 1
    assert "AC2" in capsys.readouterr().out
    assert run(repo, "set", "demo", "AC2", "pass") == 0
    assert run(repo, "finish", "demo") == 1
    assert "review.findings" in capsys.readouterr().out
    feature(repo).write_text(feature(repo).read_text() + "review:\n  findings: []\n")
    assert run(repo, "finish", "demo") == 0
    assert data(repo)["status"] == "done"
    assert run(repo, "check", "demo") == 0


def test_finish_refuses_before_review(repo):
    build_all(repo)
    assert run(repo, "finish", "demo") == 1


# ---------------------------------------------------------------- roadmap

ROADMAP = """\
vision: |
  Make reports portable.
approved: 2026-11-10
milestones:
  - id: M1
    title: Export
    outcome: Users get reports out of the app.
    features:
      - id: F1.1
        title: CSV export
        goal: Export the report as CSV.
        done_when: The report downloads as CSV.
        blocked_by: []
      - id: F1.2
        title: Scheduled export
        goal: Email the CSV weekly.
        done_when: A weekly email carries the CSV.
        blocked_by: [F1.1]
  - id: M2
    title: Share
    outcome: Users share reports.
    features:
      - id: F2.1
        title: Share link
        goal: Share a read-only link.
        done_when: A link opens the report read-only.
        blocked_by: [M1]
"""


def write_roadmap(root, text=ROADMAP):
    (root / ".specs" / "roadmap.yaml").write_text(text)


def link_feature(root, rid, status="approved"):
    feature(root).write_text(FEATURE.replace("status: approved", "status: %s" % status)
                             + "roadmap: %s\n" % rid)


def test_roadmap_derives_status_and_frontier(repo, capsys):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="building")
    assert run(repo, "roadmap") == 0
    out = capsys.readouterr().out
    assert "building  F1.1" in out and "[demo]" in out
    assert "M1 - Export: 0/2 done" in out
    assert "Ready to start" not in out  # F1.2 waits on F1.1, F2.1 on all of M1


def test_roadmap_frontier_opens_when_blocker_is_done(repo, capsys):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="done")
    assert run(repo, "roadmap") == 0
    out = capsys.readouterr().out
    assert "M1 - Export: 1/2 done" in out
    assert "Ready to start: F1.2 Scheduled export" in out
    assert "F2.1 Share link" not in out.split("Ready to start:")[1]


@pytest.mark.parametrize("old,new,expected", [
    ("blocked_by: [F1.1]", "blocked_by: [F9.9]", "unknown id F9.9"),
    ("        blocked_by: []\n      - id: F1.2", "        blocked_by: [F1.2]\n      - id: F1.2", "cycle"),
    ("      - id: F2.1", "      - id: F1.1", "id F1.1 is duplicated"),
    ("        done_when: A link opens the report read-only.\n", "", "F2.1 needs 'done_when'"),
    ("vision: |\n  Make reports portable.\n", "", "'vision' is required"),
])
def test_roadmap_rejects(repo, capsys, old, new, expected):
    assert ROADMAP.count(old) == 1, old
    write_roadmap(repo, ROADMAP.replace(old, new))
    assert run(repo, "roadmap") == 1
    assert expected in capsys.readouterr().out


def test_roadmap_rejects_two_features_on_one_entry(repo, capsys):
    write_roadmap(repo)
    link_feature(repo, "F1.1")
    other = repo / ".specs" / "features" / "other"
    other.mkdir()
    (other / "feature.yaml").write_text(feature(repo).read_text())
    assert run(repo, "roadmap") == 1
    assert "linked by several features" in capsys.readouterr().out


def test_feature_check_rejects_unknown_roadmap_link(repo, capsys):
    write_roadmap(repo)
    link_feature(repo, "F7.7")
    assert run(repo, "check", "demo") == 1
    assert "roadmap: F7.7 is not a feature" in capsys.readouterr().out
    link_feature(repo, "F1.1")
    assert run(repo, "check", "demo") == 0


def test_feature_check_rejects_link_without_roadmap(repo, capsys):
    link_feature(repo, "F1.1")
    assert run(repo, "check", "demo") == 1
    assert "does not exist" in capsys.readouterr().out


def test_status_lists_frontier(repo, capsys):
    assert run(repo, "status", "demo") == 0
    out = capsys.readouterr().out
    assert "ready    T1" in out
    assert "blocked  T2  Second (by T1)" in out


@pytest.fixture
def split(tmp_path):
    """A git repo for the code and a specs folder outside it."""
    code = tmp_path / "code"
    code.mkdir()
    git(code, "init", "-q")
    git(code, "config", "user.email", "t@example.com")
    git(code, "config", "user.name", "t")
    (code / "code.txt").write_text("v1\n")
    git(code, "add", ".")
    git(code, "commit", "-qm", "init")
    specs = tmp_path / "task" / ".specs"
    write_feature(specs / "features" / "demo")
    return code, specs


def run_split(code, specs, *args):
    return flow.main(["--root", str(code), "--specs", str(specs)] + list(args))


def test_specs_outside_root_records_commit_from_root(split):
    code, specs = split
    sha = commit(code, "v2\n")
    assert run_split(code, specs, "set", "demo", "T1", "done") == 0
    d = yaml.safe_load((specs / "features" / "demo" / "feature.yaml").read_text())
    assert str(d["tasks"][0]["sha"]) == sha
    assert run_split(code, specs, "check", "demo") == 0


def test_specs_outside_root_still_refuses_uncommitted_code(split):
    code, specs = split
    (code / "code.txt").write_text("dirty\n")
    assert run_split(code, specs, "set", "demo", "T1", "done") == 1


def test_specs_outside_root_reads_its_roadmap(split, capsys):
    code, specs = split
    (specs / "roadmap.yaml").write_text(ROADMAP)
    feature_path = specs / "features" / "demo" / "feature.yaml"
    feature_path.write_text(FEATURE.replace("status: approved", "status: done") + "roadmap: F1.1\n")
    assert run_split(code, specs, "roadmap") == 0
    assert "done      F1.1" in capsys.readouterr().out


def test_untracked_specs_inside_root_do_not_block_done(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "code.txt").write_text("v1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    specs = tmp_path / "notes" / "specs"
    write_feature(specs / "features" / "demo")
    commit(tmp_path, "v2\n")
    assert run_split(tmp_path, specs, "set", "demo", "T1", "done") == 0
