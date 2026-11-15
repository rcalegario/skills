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
