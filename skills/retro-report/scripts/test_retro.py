"""Tests for retro.py. Run: python -m pytest <skill-dir>/scripts -q"""
import datetime
import json
import os
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
    folder = retro_folder(tmp_path, drop=["title"], date="soon", summary=3, decisions="none",
                          findings=[finding(1), finding(1, what=""), finding(None), finding(2, sessions="s-1")])
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
