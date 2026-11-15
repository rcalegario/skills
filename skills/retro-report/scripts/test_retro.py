"""Tests for retro.py. Run: python -m pytest <skill-dir>/scripts -q"""
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
    return yaml.safe_load(out)


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
