"""Tests for retro.py. Run: python -m pytest <skill-dir>/scripts -q"""
import datetime
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retro  # noqa: E402

SID = "s-1"


class Log:
    """Builds a Claude Code session log, one tool call at a time."""

    def __init__(self, cwd="/work/repo"):
        self.cwd = cwd
        self.records = []
        self.n = 0
        self.minute = 0

    def _ts(self):
        self.minute += 1
        return f"2026-11-14T10:{self.minute:02d}:00.000Z"

    def prompt(self, text="do it"):
        self.records.append({"type": "user", "sessionId": SID, "cwd": self.cwd, "timestamp": self._ts(),
                             "message": {"role": "user", "content": text}})
        return self

    def call(self, tool, inp, result="ok", is_error=False, msg_id=None, usage=None):
        self.n += 1
        tid = f"toolu_{self.n}"
        message = {"id": msg_id or f"msg_{self.n}", "role": "assistant",
                   "content": [{"type": "tool_use", "id": tid, "name": tool, "input": inp}]}
        if usage:
            message["usage"] = usage
        self.records.append({"type": "assistant", "sessionId": SID, "cwd": self.cwd,
                             "timestamp": self._ts(), "message": message})
        self.records.append({"type": "user", "sessionId": SID, "cwd": self.cwd, "timestamp": self._ts(),
                             "message": {"role": "user", "content": [
                                 {"type": "tool_result", "tool_use_id": tid, "content": result,
                                  "is_error": is_error}]}})
        return self

    def bash(self, command, result="ok", **kw):
        return self.call("Bash", {"command": command}, result, **kw)

    def write(self, path):
        path.write_text("".join(json.dumps(r) + "\n" for r in self.records))
        return path


def run(capsys, *argv):
    code = retro.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def digest(tmp_path, log, capsys):
    path = log.write(tmp_path / f"{SID}.jsonl")
    code, out, err = run(capsys, "digest", str(path))
    assert code == 0, err
    return yaml.safe_load(out)[0]


def test_digest_session_and_calls_per_tool(tmp_path, capsys):
    log = Log().prompt().bash("ls").bash("git status").call("Read", {"file_path": "/work/repo/a.py"})
    d = digest(tmp_path, log, capsys)
    assert d["session"] == SID
    assert d["project"] == "/work/repo"
    assert d["start"] == "2026-11-14T10:01:00Z"
    assert d["end"] == "2026-11-14T10:07:00Z"
    assert d["duration_s"] == 360
    assert d["calls"] == {"total": 3, "by_tool": {"Bash": 2, "Read": 1}}


def test_not_a_session_log(tmp_path, capsys):
    missing = tmp_path / "nope.jsonl"
    code, out, err = run(capsys, "digest", str(missing))
    assert code == 1
    assert err.strip() == f"{missing} is not a Claude Code session log"

    other = tmp_path / "other.jsonl"
    other.write_text('{"type": "summary", "text": "x"}\nnot json\n')
    code, out, err = run(capsys, "digest", str(other))
    assert code == 1
    assert err.strip() == f"{other} is not a Claude Code session log"


def test_failure_classes_read_from_text(tmp_path, capsys):
    long_tail = "x" * 300
    log = (Log().prompt()
           .bash("cat <<EOF | python", result="line one\n(eval):27: command not found: python")
           .bash("python -c 'import yaml'", result="ModuleNotFoundError: No module named 'yaml'", is_error=True)
           .call("Read", {"file_path": "/nope"}, result="File does not exist.", is_error=True)
           .bash("cat /nope", result=f"cat: /nope: No such file or directory {long_tail}")
           .bash("touch /etc/x", result="touch: /etc/x: Permission denied")
           .bash("ls", result="fine"))
    f = digest(tmp_path, log, capsys)["failures"]
    assert f["command_missing"] == [{"call": 1, "tool": "Bash", "line": "(eval):27: command not found: python"}]
    assert f["module_missing"] == [{"call": 2, "tool": "Bash",
                                    "line": "ModuleNotFoundError: No module named 'yaml'"}]
    assert [e["call"] for e in f["file_missing"]] == [3, 4]
    assert len(f["file_missing"][1]["line"]) == 200
    assert f["permission_denied"] == [{"call": 5, "tool": "Bash", "line": "touch: /etc/x: Permission denied"}]
    assert "other" not in f


def test_unmatched_error_is_other(tmp_path, capsys):
    log = Log().prompt().bash("make", result="Exit code 2\nbuild broke", is_error=True).bash("echo", result="ok")
    f = digest(tmp_path, log, capsys)["failures"]
    assert f == {"other": [{"call": 1, "tool": "Bash", "line": "Exit code 2"}]}


def test_file_contents_are_not_failures(tmp_path, capsys):
    log = Log().prompt().call("Read", {"file_path": "retro.md"}, result="Finding: command not found: python")
    assert digest(tmp_path, log, capsys)["failures"] == {}


def test_identical_calls_are_repeats(tmp_path, capsys):
    long_cmd = "echo " + "y" * 200
    log = (Log().prompt().bash("git status").bash("ls").bash("git status").bash(long_cmd).bash(long_cmd)
           .call("Read", {"file_path": "a.py"}).call("Read", {"file_path": "a.py", "offset": 10})
           .bash("git status"))
    repeats = digest(tmp_path, log, capsys)["repeats"]
    assert repeats == [{"tool": "Bash", "input": "git status", "count": 3},
                       {"tool": "Bash", "input": long_cmd[:120], "count": 2}]


def test_search_streak_of_three(tmp_path, capsys):
    log = (Log().prompt()
           .bash("cd /work; grep -rn NOW-5 tasks | head")            # 1 search
           .bash("for d in */; do echo $d; grep -c x $d/a; done")    # 2 search: loop words and echo are neutral
           .call("Grep", {"pattern": "NOW-5"})                       # 3 search
           .call("Read", {"file_path": "now.md"})                    # 4 search
           .bash("python3 status.py .")                              # 5 not a search: breaks the run
           .bash("cat a").bash("ls b")                               # 6, 7: only two in a row
           .call("Edit", {"file_path": "a"}))
    streaks = digest(tmp_path, log, capsys)["search_streaks"]
    assert streaks == [{"calls": [1, 2, 3, 4], "commands": [
        "cd /work; grep -rn NOW-5 tasks | head",
        "for d in */; do echo $d; grep -c x $d/a; done",
        "Grep NOW-5",
        "Read now.md"]}]


def usage(i, o, cr, cw):
    return {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}


def test_tokens_once_per_message_and_cost(tmp_path, capsys):
    log = (Log().prompt()
           .bash("ls", msg_id="m1", usage=usage(1, 10, 100, 1000))
           .bash("pwd", msg_id="m1", usage=usage(1, 10, 100, 1000))     # same message, second block
           .bash("git status", msg_id="m2", usage=usage(2, 20, 200, 2000)))
    d = digest(tmp_path, log, capsys)
    assert d["tokens"] == {"input": 3, "output": 30, "cache_read": 300, "cache_write": 3000}
    assert d["cost_usd"] is None

    log.records.append({"type": "cost-state", "totalCostUSD": 1.2647382999999996})
    assert digest(tmp_path, log, capsys)["cost_usd"] == 1.2647382999999996


def test_subagents_apart(tmp_path, capsys):
    sub_dir = tmp_path / SID / "subagents"
    sub_dir.mkdir(parents=True)
    Log().prompt().bash("ls", usage=usage(1, 2, 3, 4)).bash("pwd").write(sub_dir / "agent-a1.jsonl")
    (sub_dir / "agent-a1.meta.json").write_text('{"agentType": "general-purpose", "description": "Standards review"}')
    d = digest(tmp_path, Log().prompt().call("Agent", {"prompt": "review"}), capsys)
    assert d["calls"] == {"total": 1, "by_tool": {"Agent": 1}}
    assert d["subagents"] == [{"id": "a1", "description": "Standards review", "calls": 2,
                               "tokens": {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4}}]


def test_loop_bodies_and_writes_are_not_searches(tmp_path, capsys):
    log = (Log().prompt()
           .bash("for f in *; do rm $f; done; ls")
           .bash("if x; then git push; fi; cat a")
           .bash("sed -i '' s/a/b/ f")
           .bash("cat > f <<EOF")
           .bash("find . -name '*.tmp' -delete")
           .bash("grep a b").bash("ls").bash("for d in */; do grep -c x $d/a; done"))
    assert digest(tmp_path, log, capsys)["search_streaks"] == [{"calls": [6, 7, 8], "commands": [
        "grep a b", "ls", "for d in */; do grep -c x $d/a; done"]}]


def test_http_not_found_is_not_command_missing(tmp_path, capsys):
    log = (Log().prompt()
           .bash("curl x", result="HTTP/1.1 404: Not Found")
           .bash("sh -c foo", result="sh: 1: foo: not found"))
    assert digest(tmp_path, log, capsys)["failures"] == {
        "command_missing": [{"call": 2, "tool": "Bash", "line": "sh: 1: foo: not found"}]}


def test_last_usage_of_a_message_wins(tmp_path, capsys):
    log = (Log().prompt()
           .bash("ls", msg_id="m1", usage=usage(1, 5, 0, 0))
           .bash("pwd", msg_id="m1", usage=usage(1, 40, 0, 0)))
    assert digest(tmp_path, log, capsys)["tokens"]["output"] == 40


def test_subagent_without_meta_and_parent_tokens_apart(tmp_path, capsys):
    sub_dir = tmp_path / SID / "subagents"
    sub_dir.mkdir(parents=True)
    Log().prompt().bash("ls", usage=usage(7, 7, 7, 7)).write(sub_dir / "agent-b2.jsonl")
    d = digest(tmp_path, Log().prompt().call("Agent", {"prompt": "x"}, usage=usage(1, 1, 1, 1)), capsys)
    assert d["subagents"][0]["description"] is None
    assert d["tokens"] == {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}


def test_digest_many_logs_as_list(tmp_path, capsys):
    a = Log(cwd="/work/a").prompt().bash("ls").write(tmp_path / "a.jsonl")
    b = Log(cwd="/work/b").prompt().bash("ls").bash("pwd").write(tmp_path / "b.jsonl")
    code, out, err = run(capsys, "digest", str(b), str(a))
    assert code == 0, err
    assert [(d["project"], d["calls"]["total"]) for d in yaml.safe_load(out)] == [("/work/b", 2), ("/work/a", 1)]


def finding(id=1, **kw):
    return {"id": id, "category": "automated-checks", "what": "python is missing", "fix": "a hook runs it",
            **kw}


def retro_folder(tmp_path, drop=(), **retro):
    """A retro folder whose retro.yaml is a valid one changed by retro, minus the fields in drop."""
    data = {"date": datetime.date(2026, 11, 14), "title": "checkers on commit", "summary": "Built a hook.\n",
            "sources": {"sessions": [SID]}, "findings": [finding(feature="F1.1")],
            "decisions": ["Hooks live in .githooks/."], **retro}
    for key in drop:
        data.pop(key)
    folder = tmp_path / "2026-11-14-checkers"
    folder.mkdir(exist_ok=True)
    (folder / "retro.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    (folder / "sessions.yaml").write_text(yaml.safe_dump(SESSIONS, sort_keys=False))
    return folder


SESSIONS = [{"session": SID, "project": "/work/repo", "duration_s": 754, "calls": {"total": 32},
             "failures": {"command_missing": [{"call": 20}], "other": [{"call": 3}, {"call": 9}]},
             "search_streaks": [{"calls": [1, 2, 3]}], "cost_usd": 1.2647382999999996}]


def test_validate_ok(tmp_path, capsys):
    folder = retro_folder(tmp_path)
    assert run(capsys, "validate", str(folder)) == (0, f"{folder} OK\n", "")


def test_validate_missing_and_wrong_types(tmp_path, capsys):
    folder = retro_folder(tmp_path, drop=["title"], date=datetime.datetime(2026, 11, 14, 10, 30), summary=3, decisions="none",
                          findings=[finding(1), finding(1, what=""), finding(None), finding(2, sessions="s-1"),
                                    finding(3, sessions=[SID, "zzz"])])
    code, out, err = run(capsys, "validate", str(folder))
    assert code == 1
    assert err.splitlines() == [
        "retro.yaml: date: must be a date (YYYY-MM-DD)",
        "retro.yaml: title: missing",
        "retro.yaml: summary: must be text",
        "retro.yaml: decisions: must be a list of text",
        "retro.yaml: findings[1].id: used twice",
        "retro.yaml: findings[1].what: must be text",
        "retro.yaml: findings[#3].id: must be an integer",
        "retro.yaml: findings[2].sessions: must be a list of text",
        "retro.yaml: findings[3].sessions: zzz is not in sources.sessions",
    ]

    (folder / "retro.yaml").unlink()
    assert run(capsys, "validate", str(folder))[2] == "retro.yaml: missing\n"


def test_validate_unknown_category(tmp_path, capsys):
    folder = retro_folder(tmp_path, findings=[finding(4, category="speed")])
    code, out, err = run(capsys, "validate", str(folder))
    assert code == 1
    assert err == ("retro.yaml: findings[4].category: 'speed' is not one of navigation, automated-checks, "
                   "coding-standards, global-agents-md, tool-economy, no-ops, information-access\n")


def test_validate_feature_and_wontfix_exclusive(tmp_path, capsys):
    folder = retro_folder(tmp_path, findings=[finding(2, feature="F1.2", wontfix="not worth it"),
                                              finding(3, wontfix="rare")])
    code, out, err = run(capsys, "validate", str(folder))
    assert code == 1
    assert err == "retro.yaml: findings[2]: feature and wontfix are exclusive\n"


def test_validate_sessions_match(tmp_path, capsys):
    folder = retro_folder(tmp_path, sources={"sessions": [SID, "s-2"]})
    (folder / "sessions.yaml").write_text(yaml.safe_dump(SESSIONS + [{"session": "s-3"}]))
    code, out, err = run(capsys, "validate", str(folder))
    assert code == 1
    assert err.splitlines() == ["sessions.yaml: s-2: named in sources.sessions but not digested",
                                "sessions.yaml: s-3: digested but not in sources.sessions"]

    folder = retro_folder(tmp_path, sources={"sessions": [SID, SID]})
    (folder / "sessions.yaml").write_text(yaml.safe_dump(SESSIONS + SESSIONS))
    assert run(capsys, "validate", str(folder))[2].splitlines() == [
        "retro.yaml: sources.sessions: s-1 named twice", "sessions.yaml: s-1: digested twice"]

    folder = retro_folder(tmp_path, drop=["title"])
    (folder / "sessions.yaml").write_text("session: s-1\n")
    assert run(capsys, "validate", str(folder))[2].splitlines() == [
        "retro.yaml: title: missing", "sessions.yaml: must be a list of digests"]
    (folder / "sessions.yaml").unlink()
    assert run(capsys, "validate", str(folder))[2] == "retro.yaml: title: missing\nsessions.yaml: missing\n"


def test_render_writes_report(tmp_path, capsys):
    folder = retro_folder(tmp_path, outcome="Roadmap complete.\n", sources={"sessions": [SID, "0123456789"]},
                          findings=[finding(1, what="`python` | missing,\nso it failed.", feature="F1.1"),
                                    finding(2, category="global-agents-md", wontfix="rare"),
                                    finding(3, category="tool-economy")])
    (folder / "sessions.yaml").write_text(yaml.safe_dump(
        SESSIONS + [{"session": "0123456789", "project": None, "duration_s": 29, "calls": {"total": 0},
                     "failures": {}, "search_streaks": [], "cost_usd": None}]))
    (folder / "roadmap.yaml").write_text("milestones: [{id: M1, features: [{id: F1.1}]}]\n")
    (folder / "features" / "F1.1-hook").mkdir(parents=True)
    (folder / "features" / "F1.1-hook" / "feature.yaml").write_text("roadmap: F1.1\nstatus: done\n")
    assert run(capsys, "render", str(folder)) == (0, f"wrote {folder / 'retro.md'}\n", "")
    assert (folder / "retro.md").read_text() == """\
<!-- Generated by retro.py render from retro.yaml and sessions.yaml: edit those, then render again. -->
# Retro 2026-11-14: checkers on commit

Source: Built a hook.

## Findings

| # | Category | What happened | Fix | Status |
|---|---|---|---|---|
| 1 | Automated checks | `python` \\| missing, so it failed. | a hook runs it (F1.1) | fixed |
| 2 | Global AGENTS.md | python is missing | a hook runs it. Won't fix: rare | wontfix |
| 3 | Tool economy | python is missing | a hook runs it | open |

## Decisions

- Hooks live in .githooks/.

## Sessions

| Session | Project | Minutes | Calls | Failures | Search streaks | Cost |
|---|---|---|---|---|---|---|
| s-1 | repo | 13 | 32 | 3 | 1 | $1.26 |
| 01234567 | - | 0 | 0 | 0 | 0 | - |

## Outcome

Roadmap complete.
"""


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


def config(tmp_path, **cfg):
    """A config.yaml with a retros folder and one project, changed by cfg (None drops a key)."""
    data = {"retros": str(tmp_path / "retros"), "projects": ["/work/repo"], "threshold": 10, **cfg}
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


def pending(tmp_path, capsys, monkeypatch, current=None):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    if current:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", current)
    else:
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return run(capsys, "--config", str(tmp_path / "config.yaml"), "pending")


def test_pending_lists_project_sessions(tmp_path, capsys, monkeypatch):
    config(tmp_path, projects=["/work/repo", "~/notes"])
    home = tmp_path / "home"
    a = session_log(home, "-work-repo", "a", 300)
    b = session_log(home, "-work-repo", "b", 100)
    c = session_log(home, "-work-repo-tasks-x-repos-y", "c", 200)
    d = session_log(home, re.sub(r"[^A-Za-z0-9]", "-", str(home / "notes")), "d", 400)  # Claude Code's naming
    session_log(home, "-work-repository", "e", 50)
    session_log(home, "-work-other", "f", 50)
    session_log(home, "-work-repo/a/subagents", "agent-1", 50)
    assert pending(tmp_path, capsys, monkeypatch) == (0, f"{b}\n{c}\n{a}\n{d}\n", "")


def test_pending_leaves_out_used_and_current(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    retro_folder(tmp_path / "retros")                       # its sources name s-1
    home = tmp_path / "home"
    for n, sid in enumerate(["s-1", "s-2", "s-3"]):
        session_log(home, "-work-repo", sid, 100 + n)
    assert pending(tmp_path, capsys, monkeypatch, current="s-3") == (
        0, f"{home / '.claude/projects/-work-repo/s-2.jsonl'}\n", "")


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
3 to do; 1 fixed, 1 won't fix
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
3 to do; 1 fixed, 1 won't fix
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
3 to do; 1 fixed, 1 won't fix
""", "")
    assert run(capsys, "check", str(other))[0] == 1


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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    return run(capsys, "--config", str(tmp_path / "config.yaml"), "due")


def test_due_at_threshold(tmp_path, capsys, monkeypatch):
    config(tmp_path, threshold=2)
    session_log(tmp_path / "home", "-work-repo", "s-1", 100)
    assert due(tmp_path, capsys, monkeypatch) == (0, "", "")
    session_log(tmp_path / "home", "-work-repo", "s-2", 200)
    assert due(tmp_path, capsys, monkeypatch) == (0, "2\n", "")


def test_due_threshold_default_and_wrong(tmp_path, capsys, monkeypatch):
    config(tmp_path, threshold=None)
    for n in range(10):
        session_log(tmp_path / "home", "-work-repo", f"s-{n}", 100 + n)
    assert due(tmp_path, capsys, monkeypatch) == (0, "10\n", "")
    path = config(tmp_path, threshold=0)
    assert due(tmp_path, capsys, monkeypatch) == (
        1, "", f"{path}: threshold: must be a positive whole number; see config.example.yaml\n")
