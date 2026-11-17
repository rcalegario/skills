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


def pending(tmp_path, capsys, monkeypatch, current=None, cmd="pending", all_=False):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
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
    return pending(tmp_path, capsys, monkeypatch, cmd="due")


def test_due_at_threshold(tmp_path, capsys, monkeypatch):
    config(tmp_path, threshold=2)
    session_log(tmp_path / "home", "-work-repo", "s-1", 100)
    assert due(tmp_path, capsys, monkeypatch) == (0, "", "")
    session_log(tmp_path / "home", "-work-repo", "s-2", 200)
    assert due(tmp_path, capsys, monkeypatch) == (0, "2\n", "")


def test_due_threshold_missing_or_wrong(tmp_path, capsys, monkeypatch):
    for value, problem in ((None, "missing"), (0, "must be a positive whole number")):
        path = config(tmp_path, threshold=value)
        assert due(tmp_path, capsys, monkeypatch) == (1, "", f"{path}: threshold: {problem}; see config.example.yaml\n")


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


def test_triage_null_cost_and_absent_rule(tmp_path, capsys):
    limits = {k: v for k, v in LIMITS.items() if k != "repeats"}
    triage_config(tmp_path, triage={"min_calls": 10, "limits": limits})
    s = session_file(tmp_path, cost_usd=None, repeats=[{}, {}, {}])
    assert triage(tmp_path, capsys, s) == (0, "s-1 skip\n", "")


def test_triage_day_file_replaces_entry(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")          # UTC+14: 10:01Z on the 14th is the 15th locally
    import time
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
    config(tmp_path, threshold=2)
    home = tmp_path / "home"
    logs = {sid: session_log(home, "-work-repo", sid, 100 + n) for n, sid in enumerate(["a", "b", "c", "d"])}
    verdicts(tmp_path, a="skip", b="worth")
    verdicts(tmp_path, "2026-11-15", c="skip")
    return logs


def test_pending_leaves_out_skipped(tmp_path, capsys, monkeypatch):
    logs = judged_logs(tmp_path)
    assert pending(tmp_path, capsys, monkeypatch) == (0, f"{logs['b']}\n{logs['d']}\n", "")
    assert pending(tmp_path, capsys, monkeypatch, cmd="due") == (0, "2\n", "")


def test_pending_all_lists_skipped(tmp_path, capsys, monkeypatch):
    logs = judged_logs(tmp_path)
    assert pending(tmp_path, capsys, monkeypatch, all_=True) == (
        0, "".join(f"{logs[s]}\n" for s in "abcd"), "")


def test_broken_day_file_stops_pending_and_due(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    session_log(tmp_path / "home", "-work-repo", "a", 100)
    day = verdicts(tmp_path)
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
    for cmd in ("pending", "due"):
        code, out, err = pending(tmp_path, capsys, monkeypatch, cmd=cmd)
        assert (code, out) == (1, ""), cmd
        lines = err.splitlines()
        assert len(lines) == 2 and lines[0].startswith(f"{broken}: not valid YAML")
        assert lines[1].startswith(f"{unreadable}: cannot read: ")
    assert pending(tmp_path, capsys, monkeypatch, all_=True)[0] == 0


def test_odd_session_ids_in_a_day_file(tmp_path, capsys, monkeypatch):
    config(tmp_path)
    log = session_log(tmp_path / "home", "-work-repo", "123", 100)
    path = tmp_path / "retros" / "triage" / "2026-11-14-triage.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("- {session: [a], verdict: skip}\n- {session: 123, verdict: skip}\n- {verdict: skip}\n")
    assert pending(tmp_path, capsys, monkeypatch) == (0, f"{log}\n", "")
