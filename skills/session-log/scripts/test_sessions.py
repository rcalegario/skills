"""Tests for sessions.py. Run: python -m pytest <skill-dir>/scripts -q"""
import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sessions  # noqa: E402

SID = "s-1"


class Log:
    """Builds a Claude Code session log, one tool call at a time."""

    def __init__(self, cwd="/work/repo", sid=SID):
        self.cwd = cwd
        self.sid = sid
        self.records = []
        self.n = 0
        self.minute = 0

    def _ts(self):
        self.minute += 1
        return f"2026-11-14T10:{self.minute:02d}:00.000Z"

    def prompt(self, text="do it"):
        self.records.append({"type": "user", "sessionId": self.sid, "cwd": self.cwd, "timestamp": self._ts(),
                             "message": {"role": "user", "content": text}})
        return self

    def call(self, tool, inp, result="ok", is_error=False, msg_id=None, usage=None):
        self.n += 1
        tid = f"toolu_{self.n}"
        message = {"id": msg_id or f"msg_{self.n}", "role": "assistant",
                   "content": [{"type": "tool_use", "id": tid, "name": tool, "input": inp}]}
        if usage:
            message["usage"] = usage
        self.records.append({"type": "assistant", "sessionId": self.sid, "cwd": self.cwd,
                             "timestamp": self._ts(), "message": message})
        self.records.append({"type": "user", "sessionId": self.sid, "cwd": self.cwd, "timestamp": self._ts(),
                             "message": {"role": "user", "content": [
                                 {"type": "tool_result", "tool_use_id": tid, "content": result,
                                  "is_error": is_error}]}})
        return self

    def bash(self, command, result="ok", **kw):
        return self.call("Bash", {"command": command}, result, **kw)

    def write(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in self.records))
        return path


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    """Local time is UTC, so a session's date folder is the date of its timestamps."""
    monkeypatch.setenv("TZ", "UTC")
    import time
    time.tzset()


def config(tmp_path, **cfg):
    data = {"out": str(tmp_path / "out"), **cfg}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({k: v for k, v in data.items() if v is not None}))
    return path


def run(capsys, *argv):
    code = sessions.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def extract(tmp_path, capsys, *logs):
    return run(capsys, "--config", str(config(tmp_path)), "extract", *map(str, logs))


def digest(tmp_path, log, capsys):
    path = log.write(tmp_path / f"{log.sid}.jsonl")
    code, out, err = extract(tmp_path, capsys, path)
    assert code == 0, err
    return yaml.safe_load((tmp_path / "out" / "2026-11-14" / f"{log.sid}.yaml").read_text())


def test_file_matches_digest(tmp_path, capsys):
    log = Log().prompt().bash("ls").bash("git status").call("Read", {"file_path": "/work/repo/a.py"})
    d = digest(tmp_path, log, capsys)
    assert list(d) == ["session", "project", "start", "end", "duration_s", "calls", "failures", "repeats",
                       "search_streaks", "tokens", "cost_usd", "subagents"]
    assert d["session"] == SID
    assert d["project"] == "/work/repo"
    assert d["start"] == "2026-11-14T10:01:00Z"
    assert d["end"] == "2026-11-14T10:07:00Z"
    assert d["duration_s"] == 360
    assert d["calls"] == {"total": 3, "by_tool": {"Bash": 2, "Read": 1}}


def test_named_logs_always_written(tmp_path, capsys):
    a = Log(sid="a").prompt().bash("ls").write(tmp_path / "logs" / "a.jsonl")
    b = Log(sid="b").prompt().bash("ls").bash("pwd").write(tmp_path / "logs" / "b.jsonl")
    assert extract(tmp_path, capsys, a, b) == (0, "2 written, 0 up to date, 0 not session logs\n", "")
    out = tmp_path / "out" / "2026-11-14"
    os.utime(a, (1, 1))                                     # log older than its file: still rewritten
    (out / "a.yaml").write_text("stale\n")
    assert extract(tmp_path, capsys, a)[1] == "1 written, 0 up to date, 0 not session logs\n"
    assert yaml.safe_load((out / "a.yaml").read_text())["calls"]["total"] == 1
    assert yaml.safe_load((out / "b.yaml").read_text())["calls"]["total"] == 2


def test_named_non_session_logs_are_counted(tmp_path, capsys):
    other = tmp_path / "other.jsonl"
    other.write_text('{"type": "summary", "text": "x"}\nnot json\n')
    assert extract(tmp_path, capsys, tmp_path / "nope.jsonl", other) == (
        0, "0 written, 0 up to date, 2 not session logs\n", "")


def test_config_missing_or_without_out(tmp_path, capsys):
    missing = tmp_path / "none.yaml"
    assert run(capsys, "--config", str(missing), "extract") == (
        1, "", f"{missing}: missing; see config.example.yaml\n")
    path = config(tmp_path, out=None)
    assert run(capsys, "--config", str(path), "extract") == (
        1, "", f"{path}: out: must be a path; see config.example.yaml\n")


def scan(tmp_path, capsys):
    return run(capsys, "--config", str(config(tmp_path)), "extract", "--projects", str(tmp_path / "projects"))


def project_log(tmp_path, sid, folder="-work-repo", mtime=None):
    path = Log(sid=sid).prompt().bash("ls").write(tmp_path / "projects" / folder / f"{sid}.jsonl")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def test_scan_writes_missing_files_by_local_date(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")          # UTC+14: 10:01Z on the 14th is the 15th locally
    import time
    time.tzset()
    project_log(tmp_path, "a")
    project_log(tmp_path, "b", folder="-work-other")
    Log(sid="sub").prompt().write(tmp_path / "projects" / "-work-repo" / "a" / "subagents" / "agent-x.jsonl")
    assert scan(tmp_path, capsys) == (0, "2 written, 0 up to date, 0 not session logs\n", "")
    assert sorted(p.name for p in (tmp_path / "out" / "2026-11-15").iterdir()) == ["a.yaml", "b.yaml"]


def test_scan_rewrites_stale_file(tmp_path, capsys):
    log = project_log(tmp_path, "a")
    stale = tmp_path / "out" / "2026-11-14" / "a.yaml"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n")
    os.utime(stale, (1000, 1000))
    os.utime(log, (2000, 2000))
    assert scan(tmp_path, capsys)[1] == "1 written, 0 up to date, 0 not session logs\n"
    assert yaml.safe_load(stale.read_text())["session"] == "a"


def test_scan_leaves_fresh_file(tmp_path, capsys):
    project_log(tmp_path, "a", mtime=1000)
    fresh = tmp_path / "out" / "2026-11-14" / "a.yaml"
    fresh.parent.mkdir(parents=True)
    fresh.write_text("kept\n")
    os.utime(fresh, (2000, 2000))
    assert scan(tmp_path, capsys)[1] == "0 written, 1 up to date, 0 not session logs\n"
    assert fresh.read_text() == "kept\n"


def test_scan_skips_non_session_logs(tmp_path, capsys):
    project_log(tmp_path, "a")
    other = tmp_path / "projects" / "-work-repo" / "other.jsonl"
    other.write_text('{"type": "summary"}\n')
    assert scan(tmp_path, capsys) == (0, "1 written, 0 up to date, 1 not session logs\n", "")
    assert scan(tmp_path, capsys)[1] == "0 written, 1 up to date, 1 not session logs\n"


def test_session_logs_in_two_folders_merge(tmp_path, capsys):
    old = Log(cwd="/old/repo", sid="a").prompt().bash("ls")
    new = Log(cwd="/new/repo", sid="a")
    new.minute = 30
    new.prompt().bash("pwd").bash("git status")
    old.write(tmp_path / "projects" / "-old-repo" / "a.jsonl")
    named = new.write(tmp_path / "projects" / "-new-repo" / "a.jsonl")
    stub = tmp_path / "projects" / "-stub" / "a.jsonl"         # metadata only, as a moved project leaves
    stub.parent.mkdir()
    stub.write_text('{"type": "last-prompt", "sessionId": "a"}\n')
    file = tmp_path / "out" / "2026-11-14" / "a.yaml"
    for extract_run in (lambda: scan(tmp_path, capsys),
                        lambda: run(capsys, "--config", str(config(tmp_path)), "extract",
                                    "--projects", str(tmp_path / "projects"), str(named))):
        file.unlink(missing_ok=True)
        assert extract_run()[1] == "1 written, 0 up to date, 0 not session logs\n"
        d = yaml.safe_load(file.read_text())
        assert (d["start"], d["end"]) == ("2026-11-14T10:01:00Z", "2026-11-14T10:35:00Z")
        assert d["calls"] == {"total": 3, "by_tool": {"Bash": 3}}


# Digest tests, copied from retro-report's test_retro.py with the file as the output.

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
