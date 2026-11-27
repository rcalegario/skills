"""Tests for retro.py. Run: python -m pytest <skill-dir>/scripts -q"""
import datetime
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retro  # noqa: E402

SID = "s-1"
TODAY = f"{datetime.date.today():%Y-%m-%d}"


def run(capsys, *argv):
    code = retro.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


EVIDENCE = [{"call": 20, "excerpt": "python: command not found"}]


def finding(id=1, **kw):
    """A valid finding: accepted, or wontfix when given a wontfix reason."""
    return {"id": id, "category": "automated-checks", "severity": "high",
            "status": "wontfix" if "wontfix" in kw else "accepted", "what": "python is missing",
            "evidence": EVIDENCE, "fix": "a hook runs it", "lands_in": ".githooks/pre-commit", **kw}


def finding_without(*keys, **kw):
    """A finding with the keys dropped."""
    f = finding(**kw)
    for key in keys:
        f.pop(key)
    return f


def validate_errors(tmp_path, capsys, *findings):
    """validate's error lines for a retro holding findings, after checking it exits 1."""
    folder = retro_folder(tmp_path, findings=list(findings))
    code, out, err = run(capsys, "validate", str(folder))
    assert (code, out) == (1, "")
    return err.splitlines()


def retro_folder(tmp_path, drop=(), **retro):
    """A retro folder whose retro.yaml is a valid one changed by retro, minus the fields in drop."""
    data = {"created": datetime.datetime(2026, 11, 14, 8, 39, tzinfo=datetime.timezone(datetime.timedelta(hours=-3))), "title": "checkers on commit", "summary": "Built a hook.\n",
            "session": SID, "findings": [finding(feature="F1.1")],
            "decisions": ["Hooks live in .githooks/."], **retro}
    for key in drop:
        data.pop(key)
    folder = tmp_path / "2026-11-14-checkers"
    folder.mkdir(exist_ok=True)
    (folder / "retro.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    return folder


SESSIONS = [{"session": SID, "project": "/work/repo", "start": "2026-11-14T09:00:00Z", "end": "2026-11-14T09:12:34Z",
             "duration_s": 754, "calls": {"total": 32},
             "failures": {"command_missing": [{"call": 20}], "other": [{"call": 3}, {"call": 9}]},
             "search_streaks": [{"calls": [1, 2, 3]}], "cost_usd": 1.2647382999999996}]


def test_validate_ok(tmp_path, capsys):
    folder = retro_folder(tmp_path)
    assert run(capsys, "validate", str(folder)) == (0, f"{folder} OK\n", "")


def test_validate_missing_and_wrong_types(tmp_path, capsys):
    folder = retro_folder(tmp_path, drop=["title"], created=datetime.datetime(2026, 11, 14, 10, 30), summary=3,
                          decisions="none",
                          findings=[finding(1), finding(1, what=""), finding(None)])
    code, out, err = run(capsys, "validate", str(folder))
    assert code == 1
    assert err.splitlines() == [
        "retro.yaml: created: must be a date-time with a timezone (2026-11-14T08:39:00-03:00)",
        "retro.yaml: title: missing",
        "retro.yaml: summary: must be text",
        "retro.yaml: decisions: must be a list of text",
        "retro.yaml: findings[1].id: used twice",
        "retro.yaml: findings[1].what: must be text",
        "retro.yaml: findings[#3].id: must be an integer",
    ]

    (folder / "retro.yaml").unlink()
    assert run(capsys, "validate", str(folder))[2] == "retro.yaml: missing\n"


def test_evidence_missing_or_empty(tmp_path, capsys):
    assert validate_errors(tmp_path, capsys, finding_without("evidence"), finding(2, evidence=[]),
                           finding(3, evidence={"call": 1})) == [
        "retro.yaml: findings[1].evidence: missing",
        "retro.yaml: findings[2].evidence: must be a non-empty list",
        "retro.yaml: findings[3].evidence: must be a non-empty list",
    ]


def test_evidence_call_xor_at(tmp_path, capsys):
    both = {"call": 3, "at": "2026-11-14T10:00:00Z", "excerpt": "x"}
    assert validate_errors(tmp_path, capsys, finding(evidence=[EVIDENCE[0], both, {"excerpt": "x"}, "call 3"])) == [
        "retro.yaml: findings[1].evidence[#2]: needs call or at, not both",
        "retro.yaml: findings[1].evidence[#3]: needs call or at, not both",
        "retro.yaml: findings[1].evidence[#4]: must be a mapping",
    ]


def test_evidence_call_form(tmp_path, capsys):
    items = [{"call": v, "excerpt": "x"} for v in (0, -2, "12", True, 1.5)]
    assert validate_errors(tmp_path, capsys, finding(evidence=items)) == [
        f"retro.yaml: findings[1].evidence[#{k}].call: must be a positive whole number" for k in range(1, 6)]


def test_evidence_at_form(tmp_path, capsys):
    items = [{"at": v, "excerpt": "x"} for v in (datetime.datetime(2026, 11, 14, 10), "2026-11-14T10:00:00",
                                                   "13:12:42", datetime.date(2026, 11, 14), "not a time")]
    assert validate_errors(tmp_path, capsys, finding(evidence=items)) == [
        f"retro.yaml: findings[1].evidence[#{k}].at: must be a timestamp with a timezone (2026-11-17T13:12:42Z)"
        for k in range(1, 6)]


def test_evidence_excerpt_limits(tmp_path, capsys):
    items = [{"call": 1}, {"call": 2, "excerpt": 7}, {"call": 3, "excerpt": " "},
             {"call": 4, "excerpt": "a\nb\nc\nd\n"}, {"call": 5, "excerpt": "x" * 301},
             {"call": 6, "excerpt": ("y" * 100 + "\n") * 4},
             {"call": 7, "excerpt": "a\nb\nc\n"}, {"call": 8, "excerpt": "  " + "z" * 300 + "\n"}]
    assert validate_errors(tmp_path, capsys, finding(evidence=items)) == [
        "retro.yaml: findings[1].evidence[#1].excerpt: missing",
        "retro.yaml: findings[1].evidence[#2].excerpt: must be text",
        "retro.yaml: findings[1].evidence[#3].excerpt: must be text",
        "retro.yaml: findings[1].evidence[#4].excerpt: 4 lines, at most 3",
        "retro.yaml: findings[1].evidence[#5].excerpt: 301 characters, at most 300",
        "retro.yaml: findings[1].evidence[#6].excerpt: 4 lines, at most 3",
        "retro.yaml: findings[1].evidence[#6].excerpt: 403 characters, at most 300",
    ]


def test_evidence_call_past_session(tmp_path, capsys):
    folder = retro_folder(tmp_path, findings=[finding(evidence=[{"call": 32, "excerpt": "x"},
                                                                {"call": 33, "excerpt": "x"}])])
    for cmd in ("validate", "render"):
        assert run(capsys, cmd, str(folder)) == (
            1, "", "retro.yaml: findings[1].evidence[#2].call: 33 is past the session's 32 calls\n")
    assert not (folder / "retro.md").exists()


def test_evidence_at_outside_session(tmp_path, capsys):
    at = ["2026-11-14T08:59:59Z", "2026-11-14T11:12:35+02:00", "2026-11-14T09:12:34Z", "2026-11-14T10:00:00+01:00"]
    folder = retro_folder(tmp_path, findings=[finding(evidence=[{"at": a, "excerpt": "x"} for a in at])])
    span = "(2026-11-14T09:00:00Z to 2026-11-14T09:12:34Z)"
    for cmd in ("validate", "render"):
        assert run(capsys, cmd, str(folder)) == (1, "", f"""\
retro.yaml: findings[1].evidence[#1].at: 2026-11-14T08:59:59Z is outside the session {span}
retro.yaml: findings[1].evidence[#2].at: 2026-11-14T09:12:35Z is outside the session {span}
""")


def test_evidence_at_without_session_span(tmp_path, capsys, monkeypatch):
    fake_session_log(tmp_path, monkeypatch, {**SESSIONS[0], "start": None})
    folder = retro_folder(tmp_path, findings=[finding(evidence=[{"at": "2026-11-14T09:05:00Z", "excerpt": "x"}])])
    assert run(capsys, "validate", str(folder)) == (1, "", "retro.yaml: findings[1].evidence[#1].at: "
        "2026-11-14T09:05:00Z is outside the session (the session-log file has no start and end)\n")


def test_evidence_valid(tmp_path, capsys):
    items = [{"call": 1, "excerpt": "a\nb\nc\n"}, {"call": 32, "excerpt": "x" * 300},
             {"at": datetime.datetime(2026, 11, 14, 9, 5, tzinfo=datetime.timezone.utc), "excerpt": "unquoted"},
             {"at": "2026-11-14T09:00:00Z", "excerpt": "quoted"}]
    folder = retro_folder(tmp_path, findings=[finding(evidence=items)])
    assert "  - at: 2026-11-14 09:05:00+00:00\n" in (folder / "retro.yaml").read_text()
    assert run(capsys, "validate", str(folder)) == (0, f"{folder} OK\n", "")


def test_check_evidence_shape_without_session_log(tmp_path, capsys, session_log_metrics):
    planned_retro(tmp_path, [finding_without("evidence", feature="F1.1"), finding(2, evidence=[{"call": 0}])])
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check") == (1, "", """\
2026-11-14-checkers: retro.yaml: findings[1].evidence: missing
2026-11-14-checkers: retro.yaml: findings[2].evidence[#1].call: must be a positive whole number
2026-11-14-checkers: retro.yaml: findings[2].evidence[#1].excerpt: missing
""")
    assert asked(session_log_metrics) == []


def test_validate_unknown_category(tmp_path, capsys):
    folder = retro_folder(tmp_path, findings=[finding(4, category="speed")])
    code, out, err = run(capsys, "validate", str(folder))
    assert code == 1
    assert err == ("retro.yaml: findings[4].category: 'speed' is not one of navigation, automated-checks, "
                   "coding-standards, global-agents-md, tool-economy, no-ops, information-access\n")


def test_validate_wontfix_and_feature_follow_status(tmp_path, capsys):
    assert validate_errors(tmp_path, capsys, finding(1, status="wontfix"),
                           finding(2, wontfix="rare", status="accepted"),
                           finding(3, wontfix="rare", feature="F1.2"),
                           finding(4, status="reviewing", feature="F1.2"),
                           finding(5, status="reviewing"), finding(6, wontfix="rare")) == [
        "retro.yaml: findings[1].wontfix: missing (the reason, as status is wontfix)",
        "retro.yaml: findings[2].wontfix: only on a finding whose status is wontfix",
        "retro.yaml: findings[3].feature: only on an accepted finding",
        "retro.yaml: findings[4].feature: only on an accepted finding",
    ]


def test_validate_created(tmp_path, capsys):
    for created in ("2026-11-14T08:39:00-03:00", "2026-11-14T11:39:00Z"):
        folder = retro_folder(tmp_path, created=created)
        assert run(capsys, "validate", str(folder))[0] == 0
    for created in (datetime.date(2026, 11, 14), "2026-11-14 08:39", "today"):
        folder = retro_folder(tmp_path, created=created)
        assert run(capsys, "validate", str(folder))[2] == (
            "retro.yaml: created: must be a date-time with a timezone (2026-11-14T08:39:00-03:00)\n")
    folder = retro_folder(tmp_path, drop=["created"], date=datetime.date(2026, 11, 14))
    assert run(capsys, "validate", str(folder))[2].splitlines() == [
        "retro.yaml: created: missing", "retro.yaml: date: replaced by created, a date-time with its timezone"]


def test_validate_severity_lands_in_status(tmp_path, capsys):
    assert validate_errors(tmp_path, capsys, finding_without("severity", "status", "lands_in"),
                           finding(2, severity="critical", status="done", lands_in="")) == [
        "retro.yaml: findings[1].severity: missing",
        "retro.yaml: findings[1].status: missing",
        "retro.yaml: findings[1].lands_in: missing",
        "retro.yaml: findings[2].severity: must be one of high, medium, low",
        "retro.yaml: findings[2].status: must be one of reviewing, accepted, wontfix",
        "retro.yaml: findings[2].lands_in: must be text",
    ]


def test_validate_reads_the_session_through_session_log(tmp_path, capsys, session_log_metrics):
    folder = retro_folder(tmp_path)
    assert not (folder / "sessions.yaml").exists()
    assert run(capsys, "validate", str(folder))[0] == 0
    assert asked(session_log_metrics) == [SID]


def test_validate_session_missing_or_wrong(tmp_path, capsys, session_log_metrics):
    assert run(capsys, "validate", str(retro_folder(tmp_path, drop=["session"]))) == (
        1, "", "retro.yaml: session: missing\n")
    for wrong in (["s-1"], 7, " "):
        assert run(capsys, "validate", str(retro_folder(tmp_path, session=wrong))) == (
            1, "", "retro.yaml: session: must be a session id\n")
    assert asked(session_log_metrics) == []                    # a broken retro.yaml never reaches session-log


def test_validate_session_prefix(tmp_path, capsys):
    folder = retro_folder(tmp_path, session="s-")
    assert run(capsys, "validate", str(folder)) == (
        1, "", "retro.yaml: session: s- is not a full session id (session-log has s-1)\n")


def test_validate_session_log_error(tmp_path, capsys):
    for cmd in ("validate", "render"):
        folder = retro_folder(tmp_path, session="zzz")
        assert run(capsys, cmd, str(folder)) == (1, "", "retro.yaml: session: no session log matches zzz\n")
        assert not (folder / "retro.md").exists()


def test_validate_old_keys(tmp_path, capsys):
    folder = retro_folder(tmp_path, sources={"sessions": [SID]}, findings=[finding(1), finding(2, sessions=[SID])])
    assert run(capsys, "validate", str(folder))[2].splitlines() == [
        "retro.yaml: sources: replaced by session (a retro reads one session)",
        "retro.yaml: findings[2].sessions: not used (a retro reads one session)"]


def test_render_writes_report(tmp_path, capsys):
    folder = retro_folder(tmp_path, outcome="Roadmap complete.\n",
                          findings=[finding(1, what="`python` | missing,\nso it failed.", feature="F1.1"),
                                    finding(2, category="global-agents-md", wontfix="rare"),
                                    finding(3, category="tool-economy")])
    (folder / "roadmap.yaml").write_text("milestones: [{id: M1, features: [{id: F1.1}]}]\n")
    (folder / "features" / "F1.1-hook").mkdir(parents=True)
    (folder / "features" / "F1.1-hook" / "feature.yaml").write_text("roadmap: F1.1\nstatus: done\n")
    assert run(capsys, "render", str(folder)) == (0, f"wrote {folder / 'retro.md'}\n", "")
    assert (folder / "retro.md").read_text() == """\
<!-- Generated by retro.py render from retro.yaml and its session's session-log file: edit retro.yaml, then render again. -->
# Retro 2026-11-14 08:39: checkers on commit

Source: Built a hook.

## Findings

| # | Category | Severity | What happened | Evidence | Fix | Lands in | Status |
|---|---|---|---|---|---|---|---|
| 1 | Automated checks | high | `python` \\| missing, so it failed. | #20 | a hook runs it (F1.1) | .githooks/pre-commit | fixed |
| 2 | Global AGENTS.md | high | python is missing | #20 | a hook runs it. Won't fix: rare | .githooks/pre-commit | wontfix |
| 3 | Tool economy | high | python is missing | #20 | a hook runs it | .githooks/pre-commit | open |

## Decisions

- Hooks live in .githooks/.

## Sessions

| Session | Project | Minutes | Calls | Failures | Search streaks | Cost |
|---|---|---|---|---|---|---|
| s-1 | repo | 13 | 32 | 3 | 1 | $1.26 |

## Outcome

Roadmap complete.
"""


def test_render_evidence_column(tmp_path, capsys):
    items = [{"call": 12, "excerpt": "x"}, {"call": 3, "excerpt": "x"},
             {"at": "2026-11-14T10:05:09+01:00", "excerpt": "x"}]
    folder = retro_folder(tmp_path, findings=[finding(evidence=items, feature="F1.1")])
    (folder / "roadmap.yaml").write_text("milestones: [{id: M1, features: [{id: F1.1}]}]\n")
    assert run(capsys, "render", str(folder))[0] == 0
    assert ("| 1 | Automated checks | high | python is missing | #12, #3, 09:05:09 | a hook runs it (F1.1) "
            "| .githooks/pre-commit | planned |\n") in (folder / "retro.md").read_text()


def test_render_severity_and_lands_in(tmp_path, capsys):
    folder = retro_folder(tmp_path, findings=[finding(1, severity="low", lands_in="~/.claude/AGENTS.md"),
                                              finding(2, severity="medium", status="reviewing")])
    assert run(capsys, "render", str(folder))[0] == 0
    text = (folder / "retro.md").read_text()
    assert text.splitlines()[1] == "# Retro 2026-11-14 08:39: checkers on commit"
    assert ("| # | Category | Severity | What happened | Evidence | Fix | Lands in | Status |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 1 | Automated checks | low | python is missing | #20 | a hook runs it | ~/.claude/AGENTS.md | open |\n"
            "| 2 | Automated checks | medium | python is missing | #20 | a hook runs it | .githooks/pre-commit "
            "| reviewing |\n") in text


def test_render_session_without_project_or_cost(tmp_path, capsys, monkeypatch):
    fake_session_log(tmp_path, monkeypatch, {"session": SID, "project": None, "duration_s": 29,
                                             "calls": {"total": 20}, "failures": {}, "cost_usd": None})
    folder = retro_folder(tmp_path)
    (folder / "roadmap.yaml").write_text("milestones: [{id: M1, features: [{id: F1.1}]}]\n")
    assert run(capsys, "render", str(folder))[0] == 0
    assert (folder / "retro.md").read_text().endswith("|---|---|---|---|---|---|---|\n| s-1 | - | 0 | 20 | 0 | 0 | - |\n")


def test_render_refuses_invalid(tmp_path, capsys):
    folder = retro_folder(tmp_path, drop=["title"])
    (folder / "retro.md").write_text("hand-written\n")
    assert run(capsys, "render", str(folder)) == (1, "", "retro.yaml: title: missing\n")
    assert (folder / "retro.md").read_text() == "hand-written\n"


def test_render_leaves_out_empty_decisions(tmp_path, capsys):
    folder = retro_folder(tmp_path, decisions=[], findings=[finding(1)])
    assert run(capsys, "render", str(folder))[0] == 0
    assert "## Decisions" not in (folder / "retro.md").read_text()


def test_render_strips_folded_decisions(tmp_path, capsys):
    folder = retro_folder(tmp_path, decisions=["First, folded.\n", "Second."], findings=[finding(1)])
    assert run(capsys, "render", str(folder))[0] == 0
    assert "- First, folded.\n- Second.\n" in (folder / "retro.md").read_text()


def commands(script):
    """The subcommands a script's --help lists in its usage line, {a,b,...}."""
    done = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, encoding="utf-8")
    return set(re.search(r"\{([\w,]+)\}", done.stdout).group(1).split(","))


def test_skill_md_names_real_commands():
    scripts = Path(__file__).parent
    text = (scripts.parent / "SKILL.md").read_text(encoding="utf-8")
    for script in (scripts / "retro.py", scripts.parents[1] / "session-log" / "scripts" / "sessions.py"):
        named = set(re.findall(rf"{script.name} (\w+)", text))
        assert named, script.name
        assert named <= commands(script), (script.name, named - commands(script))
    assert "digest" not in text, "SKILL.md still names the removed digest command"


def config(tmp_path, **cfg):
    """A config.yaml with a retros folder and one project, changed by cfg (None drops a key)."""
    data = {"retros": str(tmp_path / "retros"), "projects": ["/work/repo"], **cfg}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({k: v for k, v in data.items() if v is not None}))
    (tmp_path / "retros").mkdir(exist_ok=True)
    return path


def test_config_missing_or_wrong(tmp_path, capsys):
    missing = tmp_path / "none.yaml"
    for cmd in ("pending", "check"):
        assert run(capsys, "--config", str(missing), cmd) == (1, "", f"{missing}: missing; see config.example.yaml\n")
    path = config(tmp_path, retros=None, projects="/work/repo")
    assert run(capsys, "--config", str(path), "pending")[2].splitlines() == [
        f"{path}: retros: missing; see config.example.yaml",
        f"{path}: projects: must be a list of paths; see config.example.yaml"]
    assert run(capsys, "--config", str(config(tmp_path)), "check")[0] == 0


def session_log(home, folder, sid, mtime):
    path = home / ".claude" / "projects" / folder / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n")
    os.utime(path, (mtime, mtime))
    return path


def pending(tmp_path, capsys, monkeypatch, current=None, cmd="pending", all_=False):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))  # Path.home() on Windows
    if current:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", current)
    else:
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return run(capsys, "--config", str(tmp_path / "config.yaml"), cmd, *(["--all"] if all_ else []))


def test_pending_lists_project_sessions(tmp_path, capsys, monkeypatch):
    config(tmp_path, projects=["/work/repo", "~/notes"])
    home = tmp_path / "home"
    a = session_log(home, "-work-repo", "a", 300)
    b = session_log(home, "-work-repo", "b", 100)
    c = session_log(home, "-work-repo-tasks-x-repos-y", "c", 200)
    notes = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(home / "notes")) / "d.jsonl"
    if os.name == "nt" and len(str(notes)) >= 260:
        pytest.skip("the temporary home is too deep for a project folder named after it (Windows MAX_PATH)")
    d = session_log(home, re.sub(r"[^A-Za-z0-9]", "-", str(home / "notes")), "d", 400)  # Claude Code's naming
    session_log(home, "-work-repository", "e", 50)
    session_log(home, "-work-other", "f", 50)
    session_log(home, "-work-repo/a/subagents", "agent-1", 50)
    assert pending(tmp_path, capsys, monkeypatch) == (0, f"{b}\n{c}\n{a}\n{d}\n", "")


def test_pending_leaves_out_used_and_current(tmp_path, capsys, monkeypatch, session_log_metrics):
    config(tmp_path)
    retro_folder(tmp_path / "retros")                       # its session is s-1
    home = tmp_path / "home"
    for n, sid in enumerate(["s-1", "s-2", "s-3"]):
        session_log(home, "-work-repo", sid, 100 + n)
    assert pending(tmp_path, capsys, monkeypatch, current="s-3") == (
        0, f"{home / '.claude/projects/-work-repo/s-2.jsonl'}\n", "")
    assert pending(tmp_path, capsys, monkeypatch, cmd="due")[0] == 0
    pending(tmp_path, capsys, monkeypatch, cmd="check")         # fails on the roadmap, after reading retro.yaml
    assert asked(session_log_metrics) == []                    # pending, due and check never run session-log


def test_broken_retro_stops_pending_and_check(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    retro_folder(tmp_path / "retros", drop=["title"])
    session_log(tmp_path / "home", "-work-repo", "s-2", 100)
    assert pending(tmp_path, capsys, monkeypatch) == (1, "", "2026-11-14-checkers: retro.yaml: title: missing\n")
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check") == (
        1, "", "2026-11-14-checkers: retro.yaml: title: missing\n")


def planned_retro(tmp_path, findings):
    """A retro under retros with a roadmap of F1.1 (done), F1.2 (building) and F1.3 (no feature.yaml yet)."""
    config(tmp_path)
    folder = retro_folder(tmp_path / "retros", findings=findings)
    (folder / "roadmap.yaml").write_text(yaml.safe_dump(
        {"milestones": [{"id": "M1", "features": [{"id": "F1.1"}, {"id": "F1.2"}, {"id": "F1.3"}]}]}))
    for fid, status in (("F1.1", "done"), ("F1.2", "building")):
        feature = folder / "features" / f"{fid}-x" / "feature.yaml"
        feature.parent.mkdir(parents=True)
        feature.write_text(yaml.safe_dump({"roadmap": fid, "status": status}))
    return folder


FIVE = [finding(1, feature="F1.1"), finding(2, feature="F1.2"), finding(3, feature="F1.3"), finding(4),
        finding(5, wontfix="rare")]


def test_finding_status_from_roadmap(tmp_path, capsys):
    planned_retro(tmp_path, FIVE)
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check", "--all") == (0, """\
2026-11-14-checkers #1 fixed: a hook runs it (F1.1)
2026-11-14-checkers #2 planned: a hook runs it (F1.2)
2026-11-14-checkers #3 planned: a hook runs it (F1.3)
2026-11-14-checkers #4 open: a hook runs it
2026-11-14-checkers #5 wontfix: a hook runs it. Won't fix: rare
3 to do; 0 reviewing, 1 fixed, 1 won't fix
""", "")


def test_finding_feature_not_in_roadmap(tmp_path, capsys):
    planned_retro(tmp_path, [finding(1, feature="F9.9")])
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check") == (
        1, "", "2026-11-14-checkers: findings[1]: F9.9 is not in roadmap.yaml\n")


def test_check_lists_to_do(tmp_path, capsys):
    planned_retro(tmp_path, FIVE)
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check") == (0, """\
2026-11-14-checkers #2 planned: a hook runs it (F1.2)
2026-11-14-checkers #3 planned: a hook runs it (F1.3)
2026-11-14-checkers #4 open: a hook runs it
3 to do; 0 reviewing, 1 fixed, 1 won't fix
""", "")


def test_check_one_retro(tmp_path, capsys):
    folder = planned_retro(tmp_path, FIVE)
    other = tmp_path / "retros" / "2026-11-20-other"
    other.mkdir()
    (other / "retro.yaml").write_text("broken: [")          # another retro, even a broken one, stays out
    assert run(capsys, "check", str(folder)) == (0, """\
2026-11-14-checkers #2 planned: a hook runs it (F1.2)
2026-11-14-checkers #3 planned: a hook runs it (F1.3)
2026-11-14-checkers #4 open: a hook runs it
3 to do; 0 reviewing, 1 fixed, 1 won't fix
""", "")
    assert run(capsys, "check", str(other))[0] == 1


def test_check_reviewing_is_not_to_do(tmp_path, capsys):
    planned_retro(tmp_path, [finding(1, status="reviewing"), finding(2, status="reviewing", severity="low"),
                             finding(3, fix="a hook\nruns it\n"), finding(4, feature="F1.1")])
    cfg = str(tmp_path / "config.yaml")
    assert run(capsys, "--config", cfg, "check") == (0, """\
2026-11-14-checkers #3 open: a hook runs it
1 to do; 2 reviewing, 1 fixed, 0 won't fix
""", "")
    assert run(capsys, "--config", cfg, "check", "--all")[1].splitlines()[:2] == [
        "2026-11-14-checkers #1 reviewing: a hook runs it", "2026-11-14-checkers #2 reviewing: a hook runs it"]


def test_render_refuses_feature_not_in_roadmap(tmp_path, capsys):
    folder = retro_folder(tmp_path)                         # its finding names F1.1, and it has no roadmap
    assert run(capsys, "render", str(folder)) == (1, "", "findings[1]: F1.1 is not in roadmap.yaml\n")
    assert not (folder / "retro.md").exists()


def test_feature_done_but_not_in_roadmap(tmp_path, capsys):
    folder = planned_retro(tmp_path, [finding(1, feature="F9.9")])
    (folder / "features" / "F9.9-x").mkdir()
    (folder / "features" / "F9.9-x" / "feature.yaml").write_text("roadmap: F9.9\nstatus: done\n")
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check")[2] == (
        "2026-11-14-checkers: findings[1]: F9.9 is not in roadmap.yaml\n")


def test_broken_roadmap_files_are_errors(tmp_path, capsys):
    folder = planned_retro(tmp_path, FIVE)
    (folder / "features" / "F1.2-x" / "feature.yaml").write_text("roadmap: [\n")
    code, out, err = run(capsys, "--config", str(tmp_path / "config.yaml"), "check")
    assert code == 1 and err.startswith("2026-11-14-checkers: features/F1.2-x/feature.yaml: not valid YAML")

    (folder / "features" / "F1.2-x" / "feature.yaml").write_text("roadmap: F1.2\n")
    (folder / "roadmap.yaml").write_text("- F1.1\n")
    assert run(capsys, "--config", str(tmp_path / "config.yaml"), "check") == (
        1, "", "2026-11-14-checkers: roadmap.yaml: must be a mapping with milestones\n")


def test_config_retros_must_exist(tmp_path, capsys):
    path = config(tmp_path, retros=str(tmp_path / "typo"))
    assert run(capsys, "--config", str(path), "pending") == (
        1, "", f"{path}: retros: {tmp_path / 'typo'} is not a folder; see config.example.yaml\n")


def due(tmp_path, capsys, monkeypatch):
    return pending(tmp_path, capsys, monkeypatch, cmd="due")


def test_due_counts_today_unread_worth(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    verdicts(tmp_path, TODAY, b="worth", a="worth", c="worth")
    assert due(tmp_path, capsys, monkeypatch) == (0, "3 b\n", "")


def test_due_leaves_out_skip_read_current_and_other_days(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    retro_folder(tmp_path / "retros", session="b")
    verdicts(tmp_path, TODAY, a="skip", b="worth", cur="worth", d="worth", e="worth")
    verdicts(tmp_path, "2020-01-01", old="worth")
    assert pending(tmp_path, capsys, monkeypatch, current="cur", cmd="due") == (0, "2 d\n", "")


def test_due_nothing_today(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    verdicts(tmp_path, "2020-01-01", old="worth")
    assert due(tmp_path, capsys, monkeypatch) == (0, "", "")
    verdicts(tmp_path, TODAY, a="skip")
    assert due(tmp_path, capsys, monkeypatch) == (0, "", "")


def test_due_ignores_broken_other_day(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    verdicts(tmp_path, "2020-01-01").write_text("[")
    verdicts(tmp_path, TODAY, a="worth")
    assert due(tmp_path, capsys, monkeypatch) == (0, "1 a\n", "")


def test_due_threshold_not_needed(tmp_path, capsys, monkeypatch):
    for value in (None, 10, "ten"):
        config(tmp_path, threshold=value)
        verdicts(tmp_path, TODAY, a="worth")
        assert due(tmp_path, capsys, monkeypatch) == (0, "1 a\n", ""), value


LIMITS = {"failures": 4, "repeats": 1, "search_streaks": 2, "compactions": 1, "interruptions": 1,
          "denials": 1, "api_errors": 1, "active_s": 3600, "cost_usd": 10}


def triage_config(tmp_path, triage="default", **cfg):
    """A config.yaml whose triage block is the decided one, or the one given (None drops it)."""
    if triage == "default":
        triage = {"min_calls": 10, "limits": dict(LIMITS)}
    return config(tmp_path, **({"triage": triage} if triage is not None else {}), **cfg)


def session_file(tmp_path, sid="s-1", project="/work/repo", **fields):
    """A session-log file: a clean 20-call session, changed by fields."""
    data = {"session": sid, "project": project, "start": "2026-11-14T10:01:00Z", "title": "Do it",
            "calls": {"total": 20, "by_tool": {"Bash": 20}}, "failures": {}, "repeats": [], "search_streaks": [],
            "compactions": [], "interruptions": 0, "denials": {}, "api_errors": {}, "active_s": 600,
            "cost_usd": 1.5, **fields}
    path = tmp_path / "sessions" / f"{sid}.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(data))
    return path


def day_file(tmp_path, day="2026-11-14"):
    path = tmp_path / "retros" / "triage" / f"{day}-triage.yaml"
    return yaml.safe_load(path.read_text()) if path.is_file() else None


def triage(tmp_path, capsys, *paths):
    return run(capsys, "--config", str(tmp_path / "config.yaml"), "triage", *map(str, paths))


def test_triage_worth_names_each_rule(tmp_path, capsys):
    triage_config(tmp_path)
    s = session_file(tmp_path, failures={"other": [{"call": 1}] * 3, "file_missing": [{"call": 2}] * 2},
                     search_streaks=[{}, {}], compactions=[{}], interruptions=1, denials={"rule": 1},
                     api_errors={"overloaded": 1}, repeats=[{}], active_s=3600, cost_usd=12.5)
    code, out, err = triage(tmp_path, capsys, s)
    reasons = ["failures 5 >= 4", "repeats 1 >= 1", "search_streaks 2 >= 2", "compactions 1 >= 1",
               "interruptions 1 >= 1", "denials 1 >= 1", "api_errors 1 >= 1", "active_s 3600 >= 3600",
               "cost_usd 12.5 >= 10"]
    assert (code, err) == (0, "")
    assert out == f"s-1 worth: {'; '.join(reasons)}\n"
    assert day_file(tmp_path)[0]["reasons"] == reasons
    assert day_file(tmp_path)[0]["verdict"] == "worth"


def test_triage_reads_and_writes_utf8(tmp_path, capsys):
    """Session files and day files are UTF-8 whatever the locale: under cp1252, "Á" (bytes C3 81) failed to
    read, and "ã" came back as "Ã£"."""
    triage_config(tmp_path)
    s = session_file(tmp_path, title="Do it")
    s.write_bytes(s.read_bytes().replace(b"Do it", "Árvore de sessão".encode("utf-8")))
    code, out, err = triage(tmp_path, capsys, s)
    assert (code, err) == (0, "")
    path = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml"
    assert yaml.safe_load(path.read_bytes().decode("utf-8"))[0]["title"] == "Árvore de sessão"


def test_triage_skip_clean_and_small(tmp_path, capsys):
    triage_config(tmp_path)
    clean = session_file(tmp_path, "clean", failures={"other": [{}] * 3}, search_streaks=[{}], cost_usd=9.99)
    small = session_file(tmp_path, "small", calls={"total": 9}, failures={"other": [{}] * 9}, repeats=[{}])
    code, out, err = triage(tmp_path, capsys, clean, small)
    assert (code, err) == (0, "")
    assert out == "clean skip\nsmall skip: calls 9 < 10\n"
    assert [(e["session"], e["verdict"], e["reasons"]) for e in day_file(tmp_path)] == [
        ("clean", "skip", []), ("small", "skip", ["calls 9 < 10"])]


def test_triage_skips_retro_session(tmp_path, capsys):
    triage_config(tmp_path)
    retro_run = session_file(tmp_path, "retro", start_skill={"name": "retro-report", "args": "abc"},
                             failures={"other": [{}] * 9}, compactions=[{}] * 3)
    small = session_file(tmp_path, "small", start_skill={"name": "retro-report"}, calls={"total": 2})
    later = session_file(tmp_path, "later", start_skill={"name": "task"}, skills={"retro-report": 1},
                         compactions=[{}] * 3)
    assert triage(tmp_path, capsys, retro_run, small, later)[1] == (
        "retro skip: retro session\nsmall skip: retro session\nlater worth: compactions 3 >= 1\n")


def test_triage_null_cost_and_absent_rule(tmp_path, capsys):
    limits = {k: v for k, v in LIMITS.items() if k != "repeats"}
    triage_config(tmp_path, triage={"min_calls": 10, "limits": limits})
    s = session_file(tmp_path, cost_usd=None, repeats=[{}, {}, {}])
    assert triage(tmp_path, capsys, s) == (0, "s-1 skip\n", "")


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="the local time zone cannot be changed here (Windows)")
def test_triage_day_file_replaces_entry(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")          # UTC+14: 10:01Z on the 14th is the 15th locally
    time.tzset()
    triage_config(tmp_path)
    a = session_file(tmp_path, "a")
    b = session_file(tmp_path, "b", repeats=[{}])
    triage(tmp_path, capsys, a, b)
    session_file(tmp_path, "a", compactions=[{}])
    assert triage(tmp_path, capsys, a)[0] == 0
    local_day = datetime.datetime.fromisoformat("2026-11-14T10:01:00+00:00").astimezone().date()
    entries = day_file(tmp_path, local_day.isoformat())          # 2026-11-15 wherever tzset applies the TZ
    assert [(e["session"], e["verdict"]) for e in entries] == [("b", "worth"), ("a", "worth")]
    assert entries[1] == {"session": "a", "project": "/work/repo", "title": "Do it", "verdict": "worth",
                          "reasons": ["compactions 1 >= 1"], "judged": datetime.date.today().isoformat()}


def test_triage_outside_projects(tmp_path, capsys):
    triage_config(tmp_path)
    inside = session_file(tmp_path, "in", project="/work/repo/tasks/x/repos/y")
    outside = session_file(tmp_path, "out", project="/work/repository")
    code, out, err = triage(tmp_path, capsys, inside, outside)
    assert (code, out) == (0, "in skip\nout not judged: /work/repository is not in projects\n")
    assert [e["session"] for e in day_file(tmp_path)] == ["in"]


def test_triage_config_block(tmp_path, capsys, monkeypatch):
    s = session_file(tmp_path)
    path = triage_config(tmp_path, triage=None)
    assert triage(tmp_path, capsys, s) == (1, "", f"{path}: triage: missing; see config.example.yaml\n")
    path = triage_config(tmp_path, triage={"min_calls": 0, "limits": {"failures": "many", "typo": 1}})
    assert triage(tmp_path, capsys, s)[2].splitlines() == [
        f"{path}: triage.min_calls: must be a positive whole number; see config.example.yaml",
        f"{path}: triage.limits.failures: must be a positive number; see config.example.yaml",
        f"{path}: triage.limits.typo: not a rule (failures, repeats, search_streaks, compactions, interruptions, "
        "denials, api_errors, active_s, cost_usd); see config.example.yaml"]
    triage_config(tmp_path, triage=None)
    assert pending(tmp_path, capsys, monkeypatch)[0] == 0
    assert run(capsys, "--config", str(path), "check")[0] == 0


def test_triage_bad_session_file(tmp_path, capsys):
    triage_config(tmp_path)
    broken = tmp_path / "broken.yaml"
    broken.write_text("session: [")
    code, out, err = triage(tmp_path, capsys, broken, tmp_path / "gone.yaml")
    assert code == 1 and day_file(tmp_path) is None
    assert len(err.splitlines()) == 2


def test_example_config_limits(tmp_path):
    example = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                               "config.example.yaml")))
    assert example["triage"] == {"min_calls": 10, "limits": LIMITS}


def test_triage_lock_held_leaves_file(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(retro, "LOCK_WAIT_S", 0.2)
    triage_config(tmp_path)
    a = session_file(tmp_path, "a")
    assert triage(tmp_path, capsys, a)[0] == 0
    day = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml"
    before = day.read_text()
    lock = day.with_name(day.name + ".lock")
    lock.write_text("")                                      # another writer holds it
    code, out, err = triage(tmp_path, capsys, session_file(tmp_path, "b", repeats=[{}]))
    assert (code, out) == (1, "")
    assert len(err.splitlines()) == 1 and "locked" in err
    assert day.read_text() == before and lock.exists()
    lock.unlink()
    assert triage(tmp_path, capsys, tmp_path / "sessions" / "b.yaml")[0] == 0
    assert [e["session"] for e in day_file(tmp_path)] == ["a", "b"] and not lock.exists()


def test_triage_takes_a_stale_lock(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(retro, "LOCK_WAIT_S", 0.2)
    triage_config(tmp_path)
    lock = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    os.utime(lock, (1, 1))                                   # left behind by a writer that died
    assert triage(tmp_path, capsys, session_file(tmp_path))[0] == 0
    assert [e["session"] for e in day_file(tmp_path)] == ["s-1"] and not lock.exists()


def hook(tmp_path, capsys, monkeypatch, stdin, cfg=None):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return run(capsys, "--config", str(cfg or tmp_path / "config.yaml"), "triage", "--hook")


def test_triage_hook_reads_path_never_fails(tmp_path, capsys, monkeypatch):
    triage_config(tmp_path)
    s = session_file(tmp_path, repeats=[{}])
    assert hook(tmp_path, capsys, monkeypatch, f"{s}\n") == (0, "s-1 worth: repeats 1 >= 1\n", "")
    assert day_file(tmp_path)[0]["verdict"] == "worth"
    assert hook(tmp_path, capsys, monkeypatch, "") == (0, "", "")              # session-log wrote nothing
    outside = session_file(tmp_path, "out", project="/elsewhere")
    assert hook(tmp_path, capsys, monkeypatch, str(outside))[::2] == (0, "")
    broken = tmp_path / "broken.yaml"
    broken.write_text("session: [")
    for stdin, cfg in [(str(tmp_path / "gone.yaml"), None), (str(broken), None),
                       (str(s), tmp_path / "none.yaml"), (str(s), triage_config(tmp_path / "sessions", triage=None))]:
        code, out, err = hook(tmp_path, capsys, monkeypatch, stdin, cfg)
        assert code == 0, stdin
        assert len(err.strip().splitlines()) == 1, (stdin, err)
    monkeypatch.setattr(retro, "judge", lambda session, triage: 1 / 0)
    code, out, err = hook(tmp_path, capsys, monkeypatch, str(s))
    assert code == 0 and "ZeroDivisionError" in err


def test_triage_hook_without_pyyaml_exits_0():
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retro.py")
    code = ("import runpy, sys; sys.modules['yaml'] = None; "
            f"sys.argv = [{script!r}, 'triage', '--hook']; runpy.run_path({script!r}, run_name='__main__')")
    done = subprocess.run([sys.executable, "-c", code], input="", capture_output=True, text=True)
    assert done.returncode == 0
    assert len(done.stderr.strip().splitlines()) == 1 and "PyYAML" in done.stderr


def test_triage_hook_takes_no_files(tmp_path, capsys):
    import pytest
    for argv in (["triage", "--hook", "a.yaml"], ["triage"]):
        with pytest.raises(SystemExit) as exc:
            retro.main(["--config", str(tmp_path / "config.yaml"), *argv])
        assert exc.value.code == 2


def test_malformed_triage_block_leaves_pending_due_and_check(tmp_path, capsys, monkeypatch):
    path = triage_config(tmp_path, triage={"min_calls": "ten"})
    for cmd in ("pending", "due"):
        assert pending(tmp_path, capsys, monkeypatch, cmd=cmd)[::2] == (0, "")
    assert run(capsys, "--config", str(path), "check")[0] == 0
    assert triage(tmp_path, capsys, session_file(tmp_path))[0] == 1


def test_triage_block_shapes(tmp_path, capsys):
    s = session_file(tmp_path)
    for block, problems in [
            ("all", ["triage: must be a mapping with min_calls and limits"]),
            ({"min_calls": True, "limits": 5}, ["triage.min_calls: must be a positive whole number",
                                                 "triage.limits: must be a mapping of rule to limit"]),
            ({"min_calls": 3}, ["triage.limits: must be a mapping of rule to limit"]),
            ({"min_calls": 3, "limits": {"failures": -1, "repeats": True, "cost_usd": 0.5}},
             ["triage.limits.failures: must be a positive number", "triage.limits.repeats: must be a positive number"])]:
        path = triage_config(tmp_path, triage=block)
        assert triage(tmp_path, capsys, s) == (1, "", "".join(
            f"{path}: {p}; see config.example.yaml\n" for p in problems)), block


def test_triage_broken_day_file(tmp_path, capsys):
    triage_config(tmp_path)
    day = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml"
    day.parent.mkdir(parents=True)
    for text, problem in [("session: a\n", "not a list of triage entries"), ("- a\n", "not a list of triage entries"),
                          ("[", "not valid YAML")]:
        day.write_text(text)
        code, out, err = triage(tmp_path, capsys, session_file(tmp_path), session_file(tmp_path, "b"))
        assert (code, out) == (1, ""), text
        assert err.splitlines() == [f"{day}: {problem}" if problem.startswith("not a list") else err.splitlines()[0]] * 2
        assert problem in err and day.read_text() == text
        assert not day.with_name(day.name + ".lock").exists()


def test_triage_bad_session_files_one_line_each(tmp_path, capsys):
    triage_config(tmp_path)
    cases = {"list": "- a\n", "no_project": "session: x\ncalls: {total: 20}\nstart: '2026-11-14T10:01:00Z'\n",
             "no_calls": "session: x\nproject: /work/repo\nstart: '2026-11-14T10:01:00Z'\n",
             "bad_start": "session: x\nproject: /work/repo\ncalls: {total: 20}\nstart: 5\n"}
    paths = []
    for name, text in cases.items():
        paths.append(tmp_path / f"{name}.yaml")
        paths[-1].write_text(text)
    good = session_file(tmp_path)
    code, out, err = triage(tmp_path, capsys, *paths, good)
    assert (code, out) == (1, "s-1 skip\n")
    lines = err.splitlines()
    assert len(lines) == 4 and all(f"{p}: not a session-log file (" in line for p, line in zip(paths, lines))


def test_triage_write_failure_is_one_line(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(retro, "LOCK_WAIT_S", 0.2)
    triage_config(tmp_path)
    monkeypatch.setattr(retro.os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("in use")))
    code, out, err = triage(tmp_path, capsys, session_file(tmp_path), session_file(tmp_path, "b"))
    assert (code, out) == (1, "")
    assert len(err.splitlines()) == 2 and "cannot write: in use" in err
    assert not list((tmp_path / "retros" / "triage").glob("*.tmp"))


def test_triage_lock_taken_away_still_records(tmp_path, capsys, monkeypatch):
    triage_config(tmp_path)
    replace = os.replace

    def stale_takeover(a, b):                                  # another writer took the lock as stale meanwhile
        os.remove(str(b) + ".lock")
        replace(a, b)
    monkeypatch.setattr(retro.os, "replace", stale_takeover)
    assert triage(tmp_path, capsys, session_file(tmp_path)) == (0, "s-1 skip\n", "")


def test_triage_lock_released_mid_wait(tmp_path, capsys, monkeypatch):
    import threading
    monkeypatch.setattr(retro, "LOCK_WAIT_S", 3)
    triage_config(tmp_path)
    lock = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    threading.Timer(0.3, lock.unlink).start()
    assert triage(tmp_path, capsys, session_file(tmp_path)) == (0, "s-1 skip\n", "")


def test_triage_concurrent_writers_keep_every_verdict(tmp_path):
    import threading
    cfg, errors = retro.load_triage_config(triage_config(tmp_path))
    paths = [session_file(tmp_path, f"s{i}") for i in range(8)]
    threads = [threading.Thread(target=retro.triage_session, args=(cfg, p)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(e["session"] for e in day_file(tmp_path)) == [f"s{i}" for i in range(8)]


def test_triage_hook_messages_and_several_paths(tmp_path, capsys, monkeypatch):
    triage_config(tmp_path)
    good = session_file(tmp_path, repeats=[{}])
    gone = tmp_path / "gone.yaml"
    code, out, err = hook(tmp_path, capsys, monkeypatch, f"{gone}\n{good}\n")
    assert (code, out) == (0, "s-1 worth: repeats 1 >= 1\n")
    assert err.splitlines() == [err.splitlines()[0]] and f"{gone}: not a session-log file" in err
    path = triage_config(tmp_path, triage=None)
    assert hook(tmp_path, capsys, monkeypatch, str(good)) == (
        0, "", f"retro-report triage hook: {path}: triage: missing; see config.example.yaml\n")
    outside = session_file(tmp_path, "out", project="/elsewhere")
    triage_config(tmp_path)
    assert hook(tmp_path, capsys, monkeypatch, str(outside)) == (0, "out not judged: /elsewhere is not in projects\n", "")
    assert "out" not in [e["session"] for e in day_file(tmp_path)]


def test_triage_at_min_calls_is_judged(tmp_path, capsys):
    triage_config(tmp_path)
    assert triage(tmp_path, capsys, session_file(tmp_path, calls={"total": 10}, repeats=[{}]))[1] == (
        "s-1 worth: repeats 1 >= 1\n")


def verdicts(tmp_path, day="2026-11-14", **by_session):
    """A day file under retros/triage with one entry per session: verdict."""
    path = tmp_path / "retros" / "triage" / f"{day}-triage.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump([{"session": s, "verdict": v, "reasons": []} for s, v in by_session.items()]))
    return path


def judged_logs(tmp_path):
    config(tmp_path)
    home = tmp_path / "home"
    logs = {sid: session_log(home, "-work-repo", sid, 100 + n) for n, sid in enumerate(["a", "b", "c", "d"])}
    verdicts(tmp_path, a="skip", b="worth")
    verdicts(tmp_path, "2026-11-15", c="skip")
    return logs


def test_pending_leaves_out_skipped(tmp_path, capsys, monkeypatch):
    logs = judged_logs(tmp_path)
    assert pending(tmp_path, capsys, monkeypatch) == (0, f"{logs['b']}\n{logs['d']}\n", "")


def test_pending_all_lists_skipped(tmp_path, capsys, monkeypatch):
    logs = judged_logs(tmp_path)
    assert pending(tmp_path, capsys, monkeypatch, all_=True) == (
        0, "".join(f"{logs[s]}\n" for s in "abcd"), "")


def test_broken_day_file_stops_pending_and_due(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    session_log(tmp_path / "home", "-work-repo", "a", 100)
    day = verdicts(tmp_path, TODAY)
    for text, problem in [("[", "not valid YAML"), ("session: a\n", "not a list of triage entries")]:
        day.write_text(text)
        for cmd in ("pending", "due"):
            code, out, err = pending(tmp_path, capsys, monkeypatch, cmd=cmd)
            assert (code, out) == (1, ""), (text, cmd)
            assert err.startswith(f"{day}: {problem}") and len(err.splitlines()) == 1


def test_record_retries_replace_while_read(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(retro, "LOCK_WAIT_S", 0.5)
    triage_config(tmp_path)
    replace, refusals = os.replace, [PermissionError("a reader has it open")] * 2

    def held_by_a_reader(a, b):                                # Windows: a reader still has the day file open
        if refusals:
            raise refusals.pop()
        replace(a, b)
    monkeypatch.setattr(retro.os, "replace", held_by_a_reader)
    assert triage(tmp_path, capsys, session_file(tmp_path)) == (0, "s-1 skip\n", "")
    assert [e["session"] for e in day_file(tmp_path)] == ["s-1"]


def test_unreadable_and_several_broken_day_files(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    session_log(tmp_path / "home", "-work-repo", "a", 100)
    broken = verdicts(tmp_path)
    broken.write_text("[")
    unreadable = tmp_path / "retros" / "triage" / "2026-11-15-triage.yaml"
    unreadable.mkdir()                                          # reading it raises an OSError
    code, out, err = pending(tmp_path, capsys, monkeypatch)
    assert (code, out) == (1, "")
    lines = err.splitlines()
    assert len(lines) == 2 and lines[0].startswith(f"{broken}: not valid YAML")
    assert lines[1].startswith(f"{unreadable}: cannot read: ")
    assert pending(tmp_path, capsys, monkeypatch, all_=True)[0] == 0
    assert due(tmp_path, capsys, monkeypatch) == (0, "", "")    # neither is today's
    today = tmp_path / "retros" / "triage" / f"{TODAY}-triage.yaml"
    today.mkdir()
    code, out, err = due(tmp_path, capsys, monkeypatch)
    assert (code, out) == (1, "") and err.startswith(f"{today}: cannot read: ") and len(err.splitlines()) == 1


FAKE_SESSIONS_PY = '''import sys
from pathlib import Path
out = Path(__file__).parent / "out"
name = sys.argv[2]
if sys.argv[1] == "transcript":
    if name.startswith("bad"):
        sys.exit(print("cannot read the log of " + name, file=sys.stderr) or 1)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(print("#1 Bash: ls (" + name + ") relatório"))
assert sys.argv[1] == "extract" and sys.argv[3:] == ["--print-path"], sys.argv
(out.parent / "calls.txt").open("a").write(name + "\\n")
ids = sorted(p.stem for p in out.glob(name + "*.yaml"))
if not ids:
    sys.exit(print("no session log matches " + name, file=sys.stderr) or 1)
if len(ids) > 1:
    sys.exit(print("ambiguous " + name + ": " + ", ".join(ids), file=sys.stderr) or 1)
print(out / (ids[0] + ".yaml"))
'''


def fake_session_log(tmp_path, monkeypatch, *metrics):
    """Stands in for session-log's sessions.py: extract <id-or-prefix> --print-path resolves among the metrics
    files written here, prints the path or session-log's error line, and logs each name it was asked for."""
    root = tmp_path / "session-log"
    (root / "out").mkdir(parents=True, exist_ok=True)
    for m in metrics:
        (root / "out" / f"{m['session']}.yaml").write_text(yaml.safe_dump(m, sort_keys=False))
    script = root / "sessions.py"
    script.write_text(FAKE_SESSIONS_PY, encoding="utf-8")
    monkeypatch.setattr(retro, "SESSION_LOG", script)
    return root


@pytest.fixture(autouse=True)
def session_log_metrics(tmp_path, monkeypatch):
    """Every test reaches a fake session-log that knows the session of SESSIONS."""
    return fake_session_log(tmp_path, monkeypatch, *SESSIONS)


def asked(root):
    """The names the fake session-log was asked for, in order."""
    calls = root / "calls.txt"
    return calls.read_text().split() if calls.is_file() else []


def session(tmp_path, capsys, *argv):
    return run(capsys, "--config", str(config(tmp_path)), "session", *argv)


def test_session_current(tmp_path, capsys, monkeypatch):
    root = fake_session_log(tmp_path, monkeypatch, *SESSIONS)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SID)
    folder = tmp_path / "retros" / f"{TODAY}-s-1"
    assert session(tmp_path, capsys) == (0, f"{root / 'out' / 's-1.yaml'}\n{folder}\n", "")
    assert asked(root) == [SID]


def test_session_named_id_or_prefix(tmp_path, capsys, monkeypatch):
    root = fake_session_log(tmp_path, monkeypatch, {"session": "abc-123"}, {"session": "def-456"})
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "def-456")
    for name in ("abc-123", "abc"):
        assert session(tmp_path, capsys, name)[1].splitlines()[0] == str(root / "out" / "abc-123.yaml")


def test_session_none_outside_claude(tmp_path, capsys, monkeypatch):
    root = fake_session_log(tmp_path, monkeypatch, *SESSIONS)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert session(tmp_path, capsys) == (1, "", "no session: name one, or run inside a Claude Code session\n")
    assert asked(root) == []


def test_session_log_error_passes_through(tmp_path, capsys, monkeypatch):
    fake_session_log(tmp_path, monkeypatch, {"session": "abc-1"}, {"session": "abc-2"})
    assert session(tmp_path, capsys, "zzz") == (1, "", "no session log matches zzz\n")
    assert session(tmp_path, capsys, "abc") == (1, "", "ambiguous abc: abc-1, abc-2\n")
    assert list((tmp_path / "retros").iterdir()) == []


def test_session_opens_folder_with_transcript(tmp_path, capsys, monkeypatch):
    fake_session_log(tmp_path, monkeypatch, {"session": "abc-123456789", "title": "Retro-report com relatório YAML"},
                     {"session": "bad-1", "title": "x"})
    retros = tmp_path / "retros"
    folder = retros / f"{TODAY}-retro-report-com-relatorio-yaml"
    code, out, err = session(tmp_path, capsys, "abc")
    assert (code, out.splitlines()[1], err) == (0, str(folder), "")
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "#1 Bash: ls (abc-123456789) relatório\n"
    assert session(tmp_path, capsys, "abc")[1].splitlines()[1] == str(folder)      # run again: the same folder

    named = retro_folder(retros, session="abc-123456789")            # a retro naming the session is reused
    (folder / "transcript.txt").unlink()
    assert session(tmp_path, capsys, "abc")[1].splitlines()[1] == str(named)
    assert (named / "transcript.txt").is_file()

    assert session(tmp_path, capsys, "bad") == (1, "", "cannot read the log of bad-1\n")
    assert not (retros / f"{TODAY}-x").exists()


def test_session_refuses_retro_session(tmp_path, capsys, monkeypatch):
    fake_session_log(tmp_path, monkeypatch,
                     {"session": "rr-1", "title": "Retro", "start_skill": {"name": "retro-report"}})
    assert session(tmp_path, capsys, "rr") == (
        1, "", "rr-1 started with /retro-report: a retro session; run again with --anyway to read it\n")
    assert list((tmp_path / "retros").iterdir()) == []
    code, out, err = session(tmp_path, capsys, "rr", "--anyway")
    assert (code, out.splitlines()[1], err) == (0, str(tmp_path / "retros" / f"{TODAY}-retro"), "")
    assert (tmp_path / "retros" / f"{TODAY}-retro" / "transcript.txt").is_file()


def test_session_needs_config(tmp_path, capsys, monkeypatch):
    path = config(tmp_path, retros=None)
    assert run(capsys, "--config", str(path), "session", SID) == (
        1, "", f"{path}: retros: missing; see config.example.yaml\n")


def test_slug():
    assert retro.slug("Retro-report com relatório YAML") == "retro-report-com-relatorio-yaml"
    assert retro.slug("  ") == "" and retro.slug(None) == ""
    assert retro.slug("word " * 30) == "-".join(["word"] * 10)
    assert retro.slug("a" * 80) == "a" * 50


def test_no_digest_left(capsys):
    for name in ("digest", "read_records", "calls", "failures", "repeats", "search_streaks", "tokens", "cost_usd",
                 "subagents", "NotASessionLog"):
        assert not hasattr(retro, name), name
    code, out, err = run_exit(capsys, "digest", "x.jsonl")
    assert code == 2 and "invalid choice: 'digest'" in err


def run_exit(capsys, *argv):
    """run for a command argparse refuses: its exit code and output."""
    try:
        retro.main(list(argv))
    except SystemExit as e:
        out, err = capsys.readouterr()
        return e.code, out, err
    raise AssertionError("argparse accepted " + " ".join(argv))


def test_odd_session_ids_in_a_day_file(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    log = session_log(tmp_path / "home", "-work-repo", "123", 100)
    path = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("- {session: [a], verdict: skip}\n- {session: 123, verdict: skip}\n- {verdict: skip}\n")
    assert pending(tmp_path, capsys, monkeypatch) == (0, f"{log}\n", "")
