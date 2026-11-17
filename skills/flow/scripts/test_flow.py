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
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    commit(repo, "b\n")
    assert run(repo, "set", "demo", "T2", "verifying") == 0
    text = feature(repo).read_text().replace("status: building", "status: done") + "review:\n  findings: []\n"
    code, out = check_output(repo, capsys, text)
    assert code == 1 and "check AC1 is pending" in out
    passed = text.replace("status: pending", "status: pass").replace("status: verifying", "status: done")
    code, out = check_output(repo, capsys, passed)
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


def test_set_verifying_records_head_keeps_comments_and_moves_to_building(repo):
    sha = commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    text = feature(repo).read_text()
    d = yaml.safe_load(text)
    t1 = d["tasks"][0]
    assert t1["status"] == "verifying" and str(t1["sha"]) == sha
    assert t1["commit"] == "feat: do the first thing"
    assert d["status"] == "building"
    assert "status: building   # keep this comment" in text
    assert "status: verifying   # task comment" in text
    assert d["tasks"][1]["status"] == "todo"
    assert run(repo, "check", "demo") == 0


def test_set_verifying_quotes_the_sha_so_yaml_keeps_it_a_string(repo):
    sha = commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    assert '    sha: "%s"\n' % sha in feature(repo).read_text()


def test_set_verifying_refuses_uncommitted_code(repo):
    (repo / "code.txt").write_text("dirty\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 1
    assert data(repo)["tasks"][0]["status"] == "todo"


@pytest.mark.parametrize("state", ["doing", "verifying"])
def test_set_task_refuses_blocked_task(repo, state):
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T2", state) == 1


def test_set_verifying_refuses_same_commit_twice(repo):
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    assert run(repo, "set", "demo", "T2", "verifying") == 1


@pytest.mark.parametrize("state", ["doing", "verifying"])
def test_set_task_refuses_before_approval(repo, state):
    feature(repo).write_text(DRAFT_M)
    commit(repo, "v2\n")
    assert run(repo, "set", "demo", "T1", state) == 1


def test_set_verifying_with_explicit_commit_for_resume(repo):
    sha = commit(repo, "v2\n")
    commit(repo, "v3\n")
    assert run(repo, "set", "demo", "T1", "verifying", "--commit", sha) == 0
    assert str(data(repo)["tasks"][0]["sha"]) == sha


def test_set_rejects_unknown_target_or_value(repo):
    assert run(repo, "set", "demo", "T9", "verifying") == 1
    assert run(repo, "set", "demo", "T1", "pass") == 1
    assert run(repo, "set", "demo", "AC1", "done") == 1
    assert run(repo, "set", "demo", "T1", "done") == 1      # done is reached by the checks, not set


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
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    text = feature(repo).read_text().replace(
        "    covers: [AC2]\n", "    covers: [AC2]\n    repo: %s\n" % other, 1)
    feature(repo).write_text(text)
    assert run(repo, "set", "demo", "T2", "verifying", "--commit", other_sha) == 0
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
    assert run(root, "set", "demo", "T1", "verifying") == 0
    commit(root, "b\n")
    assert run(root, "set", "demo", "T2", "verifying") == 0


def test_set_check_pass_and_fail(repo):
    build_all(repo)
    assert run(repo, "set", "demo", "AC1", "pass") == 0
    assert run(repo, "set", "demo", "AC2", "fail") == 0
    d = data(repo)
    assert [c["status"] for c in d["checks"]] == ["pass", "fail"]
    assert [t["status"] for t in d["tasks"]] == ["done", "verifying"]
    assert run(repo, "check", "demo") == 0


def test_set_check_refuses_while_covering_task_is_open(repo):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    assert run(repo, "set", "demo", "AC2", "pass") == 1         # T2 covers AC2 and is open
    assert run(repo, "set", "demo", "AC1", "pass") == 0


# ---------------------------------------------------------------- review and finish

def test_review_needs_every_task_verified(repo):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    assert run(repo, "review", "demo") == 1       # T2 is still todo
    commit(repo, "b\n")
    assert run(repo, "set", "demo", "T2", "verifying") == 0
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
    assert "review.yaml" in capsys.readouterr().out
    review_file(repo).write_text("findings: []\n")
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
    assert run_split(code, specs, "set", "demo", "T1", "verifying") == 0
    d = yaml.safe_load((specs / "features" / "demo" / "feature.yaml").read_text())
    assert str(d["tasks"][0]["sha"]) == sha
    assert run_split(code, specs, "check", "demo") == 0


def test_specs_outside_root_still_refuses_uncommitted_code(split):
    code, specs = split
    (code / "code.txt").write_text("dirty\n")
    assert run_split(code, specs, "set", "demo", "T1", "verifying") == 1


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
    assert run_split(tmp_path, specs, "set", "demo", "T1", "verifying") == 0


@pytest.fixture
def home(tmp_path):
    """A repo holding several task folders, each with its own .specs."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    for name in ("tasks/mine/notes.md", "tasks/other/notes.md", "todo.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("v1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    specs = tmp_path / "tasks" / "mine" / ".specs"
    write_feature(specs / "features" / "demo")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "specs")
    commit_in(tmp_path, "tasks/mine/notes.md", "v2\n")
    return tmp_path, specs


def test_dirty_files_of_other_tasks_do_not_block_verifying(home):
    root, specs = home
    (root / "tasks" / "other" / "notes.md").write_text("dirty\n")
    (root / "todo.md").write_text("dirty\n")
    (root / "tasks" / "other" / "new.md").write_text("untracked\n")
    assert run_split(root, specs, "set", "demo", "T1", "verifying") == 0


def test_dirty_files_of_its_own_task_folder_still_block_verifying(home):
    root, specs = home
    (root / "tasks" / "mine" / "notes.md").write_text("dirty\n")
    assert run_split(root, specs, "set", "demo", "T1", "verifying") == 1


# ---------------------------------------------------------------- new and roadmap --approve

def test_new_writes_a_draft_skeleton_and_the_spec(repo):
    assert run(repo, "new", "F1.1-csv", "--title", "CSV export", "--size", "M", "--repo", "ponto-api",
               "--decisions", "D-23,D-24", "--validations", "V-01", "--test", "npm test") == 0
    folder = repo / ".specs" / "features" / "F1.1-csv"
    d = yaml.safe_load((folder / "feature.yaml").read_text())
    assert (d["id"], d["title"], d["size"], d["status"], d["repo"], d["test"]) == \
        ("F1.1-csv", "CSV export", "M", "draft", "ponto-api", "npm test")
    assert d["story"] == {"decisions": ["D-23", "D-24"], "validations": ["V-01"]}
    assert d["approved"] == {"spec": None, "tasks": None} and d["base"] is None
    assert (folder / "spec.md").read_text().startswith("# CSV export\n")


def test_new_refuses_to_overwrite_a_feature(repo, capsys):
    assert run(repo, "new", "demo", "--title", "Again", "--size", "S") == 1
    assert "already exists" in capsys.readouterr().out
    assert data(repo)["title"] == "Demo feature"


def test_new_links_a_roadmap_feature_and_rejects_an_unknown_one(repo, capsys):
    write_roadmap(repo)
    assert run(repo, "new", "F1.1-csv", "--title", "CSV", "--size", "M", "--roadmap", "F1.1") == 0
    path = repo / ".specs" / "features" / "F1.1-csv" / "feature.yaml"
    assert yaml.safe_load(path.read_text())["roadmap"] == "F1.1"
    assert run(repo, "new", "F9.9-x", "--title", "X", "--size", "M", "--roadmap", "F9.9") == 1
    assert "F9.9 is not a feature" in capsys.readouterr().out
    assert not (repo / ".specs" / "features" / "F9.9-x").exists()


def test_roadmap_approve_stamps_today_and_keeps_the_rest(repo):
    write_roadmap(repo, ROADMAP.replace("approved: 2026-11-10\n", ""))
    assert run(repo, "roadmap", "--approve") == 0
    text = (repo / ".specs" / "roadmap.yaml").read_text()
    assert yaml.safe_load(text)["approved"] == datetime.date.today()
    unchanged = "".join(l for l in text.splitlines(True) if not l.lstrip().startswith("status:"))
    assert unchanged == ROADMAP.replace("approved: 2026-11-10", "approved: %s" % datetime.date.today().isoformat())


def test_roadmap_approve_refuses_an_invalid_roadmap(repo):
    broken = ROADMAP.replace("approved: 2026-11-10\n", "").replace("blocked_by: [F1.1]", "blocked_by: [F9.9]")
    write_roadmap(repo, broken)
    assert run(repo, "roadmap", "--approve") == 1
    assert (repo / ".specs" / "roadmap.yaml").read_text() == broken


# ---------------------------------------------------------------- finding

def findings(root):
    return review(root)["findings"] if review_file(root).exists() else None


def test_finding_creates_review_yaml_with_stamps(repo):
    assert run(repo, "finding", "demo", "--text", "AC2 test misses a quote", "--source", "spec-review") == 0
    doc = review(repo)
    assert str(doc["base"]) == "abc1234"
    assert str(doc["head"]) == head(repo)
    assert doc["created"] == datetime.date.today()
    assert doc["findings"] == [{"id": "R-1", "text": "AC2 test misses a quote", "source": "spec-review"}]
    assert run(repo, "check", "demo") == 0


def test_finding_appends_next_id_with_details(repo):
    assert run(repo, "finding", "demo", "--text", "a: b", "--source", "user") == 0
    assert run(repo, "finding", "demo", "--text", "Off by one", "--source", "correctness-review",
               "--severity", "should-fix", "--confidence", "high", "--file", "src/x.py", "--line", "12",
               "--hunk", "for i in range(n + 1):", "--fix", "Use range(n)") == 0
    assert run(repo, "finding", "demo", "--text", "Rename", "--source", "standards-review",
               "--action", "fix", "--task", "T2") == 0
    assert findings(repo) == [
        {"id": "R-1", "text": "a: b", "source": "user"},
        {"id": "R-2", "text": "Off by one", "source": "correctness-review", "severity": "should-fix",
         "confidence": "high", "file": "src/x.py", "line": 12, "hunk": "for i in range(n + 1):",
         "fix": "Use range(n)"},
        {"id": "R-3", "text": "Rename", "source": "standards-review", "action": "fix", "task": "T2"}]
    assert run(repo, "check", "demo") == 0


@pytest.mark.parametrize("extra", [
    ["--source", "user", "--action", "fix"],
    ["--source", "user", "--action", "fix", "--task", "T9"],
    ["--source", "user", "--action", "wontfix"],
    ["--source", "pr-comment"],
    ["--source", "user", "--comment-id", "7"],
    ["--source", "user", "--line", "0"],
    [],
])
def test_new_finding_rejects_bad_input_unchanged(repo, extra):
    assert run(repo, "finding", "demo", "--text", "first", "--source", "user") == 0
    before = review_file(repo).read_text()
    assert run(repo, "finding", "demo", "--text", "x", *extra) == 1
    assert review_file(repo).read_text() == before


@pytest.mark.parametrize("bad", [["--severity", "huge"], ["--confidence", "sure"], ["--source", "gossip"]])
def test_new_finding_rejects_unknown_choices(repo, bad):
    with pytest.raises(SystemExit):
        run(repo, "finding", "demo", "--text", "x", "--source", "user", *bad)
    assert findings(repo) is None


def test_finding_never_writes_feature_yaml(repo):
    before = feature(repo).read_text()
    assert run(repo, "finding", "demo", "--text", "x", "--source", "user") == 0
    assert run(repo, "finding", "demo", "--text", "y", "--source", "user", "--action", "wontfix", "--reason", "r") == 0
    assert feature(repo).read_text() == before


def test_finding_refuses_a_legacy_block(repo, capsys):
    feature(repo).write_text(FEATURE + "review:\n  findings: []\n")
    capsys.readouterr()
    assert run(repo, "finding", "demo", "--text", "x", "--source", "user") == 1
    assert "review.yaml" in capsys.readouterr().out
    assert not review_file(repo).exists()


def test_finding_sets_and_changes_the_outcome(repo, capsys):
    assert run(repo, "finding", "demo", "--text", "a", "--source", "spec-review", "--severity", "nit") == 0
    assert run(repo, "finding", "demo", "--text", "b", "--source", "user") == 0
    capsys.readouterr()
    assert run(repo, "finding", "demo", "R-1", "--action", "fix", "--task", "T2") == 0
    out = capsys.readouterr().out
    assert "R-1" in out and "no action -> fix T2" in out
    assert findings(repo)[0] == {"id": "R-1", "text": "a", "source": "spec-review", "severity": "nit",
                                 "action": "fix", "task": "T2"}
    assert run(repo, "finding", "demo", "R-1", "--action", "wontfix", "--reason", "too small") == 0
    assert "fix T2 -> wontfix" in capsys.readouterr().out
    assert findings(repo) == [
        {"id": "R-1", "text": "a", "source": "spec-review", "severity": "nit", "action": "wontfix", "reason": "too small"},
        {"id": "R-2", "text": "b", "source": "user"}]
    assert run(repo, "check", "demo") == 0


@pytest.mark.parametrize("args", [
    ["R-9", "--action", "wontfix", "--reason", "r"],
    ["R-1", "--action", "fix", "--task", "T9"],
    ["R-1", "--action", "fix"],
    ["R-1", "--action", "wontfix"],
    ["R-1"],
    ["R-1", "--action", "wontfix", "--reason", "r", "--text", "new text"],
    ["R-1", "--none"],
])
def test_finding_outcome_rejects_unknown_id_or_task(repo, args):
    assert run(repo, "finding", "demo", "--text", "a", "--source", "user") == 0
    before = review_file(repo).read_text()
    assert run(repo, "finding", "demo", *args) == 1
    assert review_file(repo).read_text() == before


def test_finding_outcome_needs_review_yaml(repo):
    assert run(repo, "finding", "demo", "R-1", "--action", "wontfix", "--reason", "r") == 1
    assert not review_file(repo).exists()


def test_finding_none_writes_a_clean_review_yaml(repo):
    assert run(repo, "finding", "demo", "--none") == 0
    assert findings(repo) == []
    assert run(repo, "check", "demo") == 0


def test_finding_none_is_refused_when_findings_exist(repo):
    run(repo, "finding", "demo", "--text", "x", "--action", "wontfix", "--reason", "y", "--source", "user")
    assert run(repo, "finding", "demo", "--none") == 1
    assert len(findings(repo)) == 1


@pytest.mark.parametrize("extra", [["--action", "fix"], ["--action", "wontfix"]])
def test_finding_needs_its_task_or_reason(repo, extra):
    assert run(repo, "finding", "demo", "--text", "x", "--source", "user", *extra) == 1
    assert findings(repo) is None


def test_finding_appends_to_an_empty_list(repo):
    run(repo, "finding", "demo", "--none")
    assert run(repo, "finding", "demo", "--text", "x", "--action", "wontfix", "--reason", "y", "--source", "user") == 0
    assert len(findings(repo)) == 1


def wontfix(repo, *extra):
    return run(repo, "finding", "demo", "--text", "x", "--action", "wontfix", "--reason", "y", *extra)


def test_finding_records_the_pr_comment_and_its_id(repo):
    assert wontfix(repo, "--source", "pr-comment", "--comment-id", "2201") == 0
    assert findings(repo) == [{"id": "R-1", "text": "x", "source": "pr-comment", "comment_id": 2201,
                               "action": "wontfix", "reason": "y"}]


def test_finding_needs_a_known_source(repo):
    assert wontfix(repo) == 1
    with pytest.raises(SystemExit):
        wontfix(repo, "--source", "gossip")
    assert findings(repo) is None


@pytest.mark.parametrize("source", ["correctness-review", "tests-review", "security-review"])
def test_finding_accepts_each_review_source(repo, source):
    assert wontfix(repo, "--source", source) == 0
    assert findings(repo) == [{"id": "R-1", "text": "x", "source": source, "action": "wontfix", "reason": "y"}]


def test_finding_pr_comment_needs_its_id_and_only_it(repo):
    assert wontfix(repo, "--source", "pr-comment") == 1
    assert wontfix(repo, "--source", "user", "--comment-id", "7") == 1
    assert findings(repo) is None


def test_finding_refuses_a_comment_already_recorded(repo):
    assert wontfix(repo, "--source", "pr-comment", "--comment-id", "2201") == 0
    assert wontfix(repo, "--source", "pr-comment", "--comment-id", "2201") == 1
    assert len(findings(repo)) == 1


REVIEWED = FEATURE + "review:\n  findings:\n%s"


def test_check_warns_on_a_finding_without_source_and_accepts_it(repo, capsys):
    code, out = check_output(repo, capsys, REVIEWED % "    - text: a\n      action: wontfix\n      reason: r\n")
    assert code == 0 and "source" in out


@pytest.mark.parametrize("source", ["correctness-review", "tests-review", "security-review"])
def test_check_accepts_a_finding_with_a_new_source(repo, capsys, source):
    code, out = check_output(repo, capsys, REVIEWED % ("    - {text: a, action: wontfix, reason: r, source: %s}\n" % source))
    assert code == 0 and "source must be one of" not in out


def test_check_rejects_a_bad_source_and_a_pr_comment_without_id(repo, capsys):
    code, out = check_output(repo, capsys, REVIEWED % (
        "    - {text: a, action: wontfix, reason: r, source: gossip}\n"
        "    - {text: b, action: wontfix, reason: r, source: pr-comment}\n"))
    assert code == 1
    assert "source must be one of" in out
    assert "pr-comment without a 'comment_id'" in out


def test_check_rejects_the_same_comment_twice(repo, capsys):
    code, out = check_output(repo, capsys, REVIEWED % (
        "    - {text: a, action: wontfix, reason: r, source: pr-comment, comment_id: 5}\n"
        "    - {text: b, action: wontfix, reason: r, source: pr-comment, comment_id: 5}\n"))
    assert code == 1 and "comment_id 5 is recorded twice" in out


# ---------------------------------------------------------------- pr

def test_pr_records_the_url_and_replaces_it(repo):
    assert run(repo, "pr", "demo", "--url", "https://github.com/o/r/pull/1") == 0
    assert run(repo, "pr", "demo", "--url", "https://github.com/o/r/pull/2") == 0
    assert data(repo)["pr"] == "https://github.com/o/r/pull/2"
    assert "status: approved   # keep this comment" in feature(repo).read_text()


def test_pr_refuses_what_is_not_a_url(repo):
    assert run(repo, "pr", "demo", "--url", "pull 1") == 1
    assert "pr" not in data(repo)


def test_check_rejects_a_pr_that_is_not_a_url(repo, capsys):
    code, out = check_output(repo, capsys, FEATURE + "pr: pull 1\n")
    assert code == 1 and "'pr' must be a URL" in out


# ---------------------------------------------------------------- task state machine

def test_set_done_is_refused_and_explains(repo, capsys):
    commit(repo, "v2\n")
    capsys.readouterr()
    assert run(repo, "set", "demo", "T1", "done") == 1
    assert "AC<n> pass" in capsys.readouterr().out
    assert data(repo)["tasks"][0]["status"] == "todo"


def test_checks_passing_promote_the_task_to_done(repo):
    build_all(repo)
    assert run(repo, "set", "demo", "AC1", "pass") == 0
    assert [t["status"] for t in data(repo)["tasks"]] == ["done", "verifying"]
    assert "status: done" in feature(repo).read_text()
    assert run(repo, "set", "demo", "AC2", "pass") == 0
    assert [t["status"] for t in data(repo)["tasks"]] == ["done", "done"]
    assert run(repo, "check", "demo") == 0


def test_task_covering_two_criteria_waits_for_both(repo):
    feature(repo).write_text(FEATURE.replace("covers: [AC1]", "covers: [AC1, AC2]", 1)
                             .replace("covers: [AC2]", "covers: [AC2]"))
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    commit(repo, "b\n")
    assert run(repo, "set", "demo", "T2", "verifying") == 0
    assert run(repo, "set", "demo", "AC1", "pass") == 0
    assert data(repo)["tasks"][0]["status"] == "verifying"
    assert run(repo, "set", "demo", "AC2", "pass") == 0
    assert [t["status"] for t in data(repo)["tasks"]] == ["done", "done"]


def test_a_failing_check_sends_a_done_task_back_to_verifying(repo):
    build_all(repo)
    assert run(repo, "set", "demo", "AC1", "pass") == 0
    assert run(repo, "set", "demo", "AC1", "fail") == 0
    assert data(repo)["tasks"][0]["status"] == "verifying"
    assert run(repo, "check", "demo") == 0


def test_set_check_refuses_while_covering_task_is_only_started(repo):
    assert run(repo, "set", "demo", "T1", "doing") == 0
    assert run(repo, "set", "demo", "AC1", "pass") == 1


def test_a_verifying_task_cannot_go_back_to_doing(repo):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    assert run(repo, "set", "demo", "T1", "doing") == 1


def test_verifying_releases_the_dependent_task(repo):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    assert run(repo, "set", "demo", "T2", "doing") == 0


def test_check_rejects_verifying_without_sha_and_done_with_pending_check(repo, capsys):
    code, out = check_output(repo, capsys, FEATURE.replace("status: todo   # task comment", "status: verifying"))
    assert code == 1 and "T1 is verifying without a 'sha'" in out
    sha = commit(repo, "a\n")
    text = FEATURE.replace("status: todo   # task comment", "status: done\n    sha: %s" % sha)
    code, out = check_output(repo, capsys, text)
    assert code == 1 and "T1 is done but check AC1 is pending" in out


def test_check_rejects_a_started_task_whose_blocker_is_still_todo(repo, capsys):
    code, out = check_output(repo, capsys, FEATURE.replace("status: todo\n", "status: doing\n"))
    assert code == 1 and "T2 is doing but its blocker T1" in out


def test_status_does_not_list_a_verifying_task_as_ready(repo, capsys):
    commit(repo, "a\n")
    assert run(repo, "set", "demo", "T1", "verifying") == 0
    capsys.readouterr()
    assert run(repo, "status", "demo") == 0
    out = capsys.readouterr().out
    assert "verifying T1" in out and "ready    T2" in out and "ready    T1" not in out


# ---------------------------------------------------------------- roadmap status written

def test_roadmap_writes_the_status_of_features_and_milestones(repo):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="building")
    assert run(repo, "roadmap") == 0
    road = yaml.safe_load((repo / ".specs" / "roadmap.yaml").read_text())
    m1, m2 = road["milestones"]
    assert [f["status"] for f in m1["features"]] == ["building", "planned"]
    assert (m1["status"], m2["status"]) == ("building", "planned")
    assert "approved: 2026-11-10" in (repo / ".specs" / "roadmap.yaml").read_text()


def test_roadmap_status_follows_the_feature_commands(repo):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="approved")
    assert run(repo, "set", "demo", "T1", "doing") == 0
    road = yaml.safe_load((repo / ".specs" / "roadmap.yaml").read_text())
    assert road["milestones"][0]["features"][0]["status"] == "building"
    assert road["milestones"][0]["status"] == "building"


def test_roadmap_rewrites_a_status_edited_by_hand(repo):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="approved")
    assert run(repo, "roadmap") == 0
    path = repo / ".specs" / "roadmap.yaml"
    path.write_text(path.read_text().replace("status: approved", "status: done", 1))
    assert run(repo, "roadmap") == 0
    assert yaml.safe_load(path.read_text())["milestones"][0]["features"][0]["status"] == "approved"


def test_milestone_is_done_when_all_its_features_are(repo):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="done")
    assert run(repo, "roadmap") == 0
    road = yaml.safe_load((repo / ".specs" / "roadmap.yaml").read_text())
    assert road["milestones"][0]["status"] == "building"      # F1.2 still planned


# ---------------------------------------------------------------- review.yaml

def review_file(root):
    return root / ".specs" / "features" / "demo" / "review.yaml"


def review(root):
    return yaml.safe_load(review_file(root).read_text())


def finish_ready(root):
    build_all(root)
    assert run(root, "review", "demo") == 0
    assert run(root, "set", "demo", "AC1", "pass") == 0
    assert run(root, "set", "demo", "AC2", "pass") == 0


def test_finish_needs_review_yaml_with_every_outcome(repo, capsys):
    finish_ready(repo)
    capsys.readouterr()
    assert run(repo, "finish", "demo") == 1
    assert "needs review.yaml" in capsys.readouterr().out
    review_file(repo).write_text("findings:\n  - {id: R-1, text: a, source: user}\n"
                                 "  - {id: R-2, text: b, source: user, action: wontfix, reason: r}\n")
    assert run(repo, "finish", "demo") == 1
    out = capsys.readouterr().out
    assert "R-1 has no action" in out and "R-2" not in out
    review_file(repo).write_text("findings:\n  - {id: R-1, text: a, source: user, action: wontfix, reason: r}\n")
    assert run(repo, "finish", "demo") == 0
    assert data(repo)["status"] == "done"


def test_check_reports_review_yaml_errors(repo, capsys):
    review_file(repo).write_text(
        "findings:\n"
        "  - {id: R-1, text: a, source: gossip}\n"
        "  - {id: R-1, text: b, source: user, severity: huge, confidence: sure}\n"
        "  - {id: X9, text: c, source: user, action: fix, task: T9}\n"
        "  - {id: R-4, text: d, source: user, action: wontfix}\n"
        "  - {id: R-5, text: e, source: pr-comment}\n"
        "  - {id: R-6, text: f, source: pr-comment, comment_id: 7}\n"
        "  - {id: R-7, text: g, source: pr-comment, comment_id: 7}\n"
        "  - {id: R-8, text: h, source: user, action: maybe}\n")
    code, out = check_output(repo, capsys)
    assert code == 1
    for expected in ["R-1 source must be one of", "id R-1 is duplicated", "severity must be one of",
                     "confidence must be one of", "id X9 must be R-<n>", "fix without an existing 'task'",
                     "R-4 is a wontfix without a 'reason'", "R-5 is a pr-comment without a 'comment_id'",
                     "comment_id 7 is recorded twice", "R-8 action must be one of"]:
        assert expected in out, (expected, out)


@pytest.mark.parametrize("body", ["findings: oops\n", "base: abc1234\n"])
def test_check_rejects_review_yaml_without_a_findings_list(repo, capsys, body):
    review_file(repo).write_text(body)
    code, out = check_output(repo, capsys)
    assert code == 1 and "findings must be a list" in out
    capsys.readouterr()
    assert run(repo, "finding", "demo", "--none") == 1
    assert run(repo, "finding", "demo", "--text", "x", "--source", "user") == 1
    assert review_file(repo).read_text() == body


def test_check_reports_the_id_of_a_finding_without_text(repo, capsys):
    review_file(repo).write_text("findings:\n  - {id: R-1, text: a, source: user}\n  - {id: R-1, source: user}\n")
    code, out = check_output(repo, capsys)
    assert code == 1 and "id R-1 is duplicated" in out and "needs 'text'" in out


def test_check_accepts_a_review_yaml_with_open_findings(repo, capsys):
    review_file(repo).write_text("base: abc1234\nhead: abc1234\ncreated: 2026-11-17\nfindings:\n"
                                 "  - {id: R-1, text: a, source: spec-review, severity: nit, confidence: low}\n")
    code, out = check_output(repo, capsys)
    assert code == 0, out


def test_legacy_review_block_is_read_with_a_warning(repo, capsys):
    legacy = FEATURE + "review:\n  findings:\n    - {text: a, action: wontfix, reason: r, source: user}\n"
    code, out = check_output(repo, capsys, legacy)
    assert code == 0 and "legacy" in out
    assert run(repo, "status", "demo") == 0
    out = capsys.readouterr().out
    assert "Review findings: 1" in out and "legacy" in out
    review_file(repo).write_text("findings: []\n")
    code, out = check_output(repo, capsys)
    assert code == 1 and "both" in out


def test_finish_reads_a_legacy_review_block(repo):
    finish_ready(repo)
    feature(repo).write_text(feature(repo).read_text() + "review:\n  findings: []\n")
    assert run(repo, "finish", "demo") == 0
