"""Tests for sessions.py. Run: python -m pytest <skill-dir>/scripts -q"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

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

    def user(self, content, **fields):
        self.records.append({"type": "user", "sessionId": self.sid, "cwd": self.cwd, "timestamp": self._ts(),
                             "message": {"role": "user", "content": content}, **fields})
        return self

    def command(self, name, args="", skill=False):
        """A typed /command; a skill command is followed by the skill's body as a meta record."""
        self.user(f"<command-name>/{name}</command-name>\n<command-message>{name}</command-message>\n"
                  f"<command-args>{args}</command-args>")
        if skill:
            self.user([{"type": "text", "text": f"Base directory for this skill: /skills/{name}\n\n# {name}"}],
                      isMeta=True)
        return self

    def record(self, **fields):
        self.records.append({"sessionId": self.sid, "timestamp": self._ts(), **fields})
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
    if hasattr(time, "tzset"):      # Windows has none: there the local date of these 10:xx UTC times is the same
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
    assert list(d)[:12] == ["session", "project", "start", "end", "duration_s", "calls", "failures", "repeats",
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
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset, which Windows lacks")
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


@pytest.mark.skipif(sys.platform != "win32", reason="the 260-character path limit is Windows only")
def test_scan_reaches_logs_past_the_windows_path_limit(tmp_path, capsys):
    """A project folder name can push a log's path past 260 characters (a desktop scratch workspace): it is
    written like any other, and the rest of the scan still runs."""
    deep = "-" + "x" * (259 - len(str(tmp_path / "projects")))
    long = tmp_path / "projects" / deep / "long.jsonl"
    assert len(str(long)) > 260
    Log(sid="long").prompt().bash("ls").write(Path("\\\\?\\" + str(long)))     # only the prefix can create it
    project_log(tmp_path, "short")
    code, out, err = scan(tmp_path, capsys)
    assert code == 0, err
    assert sorted(p.name for p in (tmp_path / "out" / "2026-11-14").iterdir()) == ["long.yaml", "short.yaml"]
    assert scan(tmp_path, capsys)[1] == "0 written, 2 up to date, 0 not session logs\n"


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


def test_log_without_timestamps_is_not_a_session(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    import time
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset, which Windows lacks")
    time.tzset()
    log = Log(sid="a").prompt().bash("ls")
    for r in log.records:
        del r["timestamp"]
    log.write(tmp_path / "projects" / "-work-repo" / "a.jsonl")
    assert scan(tmp_path, capsys) == (0, "0 written, 0 up to date, 1 not session logs\n", "")
    assert not (tmp_path / "out").exists()


def test_one_file_per_session_across_dates(tmp_path, capsys):
    project_log(tmp_path, "a")
    old = tmp_path / "out" / "2026-01-01" / "a.yaml"
    old.parent.mkdir(parents=True)
    old.write_text("old\n")
    os.utime(old, (1000, 1000))
    assert scan(tmp_path, capsys)[1] == "1 written, 0 up to date, 0 not session logs\n"
    assert [p.relative_to(tmp_path / "out").as_posix() for p in (tmp_path / "out").glob("*/*.yaml")] == [
        "2026-11-14/a.yaml"]


def test_file_takes_log_mtime(tmp_path, capsys):
    log = project_log(tmp_path, "a", mtime=1000)
    file = tmp_path / "out" / "2026-11-14" / "a.yaml"
    scan(tmp_path, capsys)
    assert file.stat().st_mtime == 1000
    os.utime(log, (1001, 1001))                              # the live log grew after the file was written
    assert scan(tmp_path, capsys)[1] == "1 written, 0 up to date, 0 not session logs\n"


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
    assert d["subagents"] == [{"id": "a1", "type": "general-purpose", "description": "Standards review", "calls": 2,
                               "by_tool": {"Bash": 2}, "skills": {},
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
    assert d["subagents"][0]["type"] is None
    assert d["tokens"] == {"input": 1, "output": 1, "cache_read": 1, "cache_write": 1}


def test_human_turns(tmp_path, capsys):
    log = (Log().prompt("first")
           .user("hidden", isMeta=True)
           .user("summary", isCompactSummary=True)
           .user("back from agent", origin={"kind": "peer"})
           .user([{"type": "text", "text": "second"}], origin={"kind": "human"})
           .user("<bash-stdout>out</bash-stdout><bash-stderr></bash-stderr>")
           .bash("ls"))
    assert digest(tmp_path, log, capsys)["human_turns"] == 2


def test_active_time_and_interruptions(tmp_path, capsys):
    log = (Log().prompt("go").bash("ls")
           .user("[Request interrupted by user for tool use]")
           .user([{"type": "text", "text": "[Request interrupted by user]"}])
           .record(type="system", subtype="turn_duration", durationMs=61500)
           .record(type="system", subtype="turn_duration", durationMs=30000))
    d = digest(tmp_path, log, capsys)
    assert d["interruptions"] == 2
    assert d["active_s"] == 91
    assert d["human_turns"] == 1


def test_initial_prompt_after_clear(tmp_path, capsys):
    long = "fix the parser\n" + "x" * 5000
    log = Log().command("clear").user("<local-command-stdout></local-command-stdout>").prompt(long).prompt("next")
    assert digest(tmp_path, log, capsys)["initial_prompt"] == long
    assert digest(tmp_path, Log().prompt("hello").command("clear").prompt("after"), capsys)["initial_prompt"] == "hello"
    assert digest(tmp_path, Log().bash("ls"), capsys)["initial_prompt"] is None


def test_typed_skill_vs_builtin(tmp_path, capsys):
    log = (Log().command("clear").command("task", "resume x", skill=True)
           .command("compact").command("tdd", skill=True).command("model", "opus").command("task", skill=True))
    d = digest(tmp_path, log, capsys)
    assert d["skills"] == {"task": 2, "tdd": 1}
    assert d["commands"] == {"clear": 1, "compact": 1, "model": 1}


def test_skill_tool_counted(tmp_path, capsys):
    log = Log().command("task", skill=True).call("Skill", {"skill": "tdd"}).call("Skill", {"skill": "task", "args": "x"})
    assert digest(tmp_path, log, capsys)["skills"] == {"task": 2, "tdd": 1}


def test_start_skill(tmp_path, capsys):
    log = Log().command("clear").command("task", "resume\nthe log", skill=True).prompt("yes")
    d = digest(tmp_path, log, capsys)
    assert d["start_skill"] == {"name": "task", "args": "resume\nthe log"}
    assert d["initial_prompt"].startswith("<command-name>/task</command-name>")
    assert digest(tmp_path, Log().command("model", "opus").prompt("go"), capsys)["start_skill"] is None
    assert digest(tmp_path, Log().prompt("go").command("task", skill=True), capsys)["start_skill"] is None


def test_commands_quoted_in_summaries_are_not_typed(tmp_path, capsys):
    log = (Log().command("clear")
           .user("Summary: ran <command-name>/x</command-name>", isCompactSummary=True)
           .user("<command-name>/y</command-name>", origin={"kind": "peer"}))
    assert digest(tmp_path, log, capsys)["commands"] == {"clear": 1}


def test_compactions(tmp_path, capsys):
    meta = {"trigger": "auto", "preTokens": 214686, "postTokens": 23455, "durationMs": 43041,
            "preservedSegment": {"headUuid": "u1"}}
    log = (Log().prompt().record(type="system", subtype="compact_boundary", compactMetadata=meta)
           .record(type="system", subtype="compact_boundary", compactMetadata={"trigger": "manual", "preTokens": 9}))
    assert digest(tmp_path, log, capsys)["compactions"] == [
        {"time": "2026-11-14T10:02:00Z", "trigger": "auto", "pre_tokens": 214686, "post_tokens": 23455,
         "duration_ms": 43041},
        {"time": "2026-11-14T10:03:00Z", "trigger": "manual", "pre_tokens": 9, "post_tokens": None,
         "duration_ms": None}]


def test_non_ascii_text_is_read_and_written_as_utf8(tmp_path, capsys):
    """Session logs are UTF-8 whatever the locale: under cp1252, "Á" (bytes C3 81) read as a replacement
    character and then failed to write, and "ã" came back as "Ã£"."""
    log = Log().prompt().record(type="ai-title", aiTitle="Árvore de sessão")
    path = tmp_path / f"{log.sid}.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in log.records), encoding="utf-8")
    code, out, err = extract(tmp_path, capsys, path)
    assert code == 0, err
    written = (tmp_path / "out" / "2026-11-14" / f"{log.sid}.yaml").read_bytes().decode("utf-8")
    assert yaml.safe_load(written)["title"] == "Árvore de sessão"


def test_title_prefers_custom(tmp_path, capsys):
    log = Log().prompt().record(type="ai-title", aiTitle="First").record(type="ai-title", aiTitle="Second")
    assert digest(tmp_path, log, capsys)["title"] == "Second"
    log.record(type="custom-title", customTitle="Mine").record(type="ai-title", aiTitle="Third")
    assert digest(tmp_path, log, capsys)["title"] == "Mine"


def test_environment_distinct_values(tmp_path, capsys):
    log = Log().prompt().bash("ls").bash("pwd")
    for rec, branch, version in zip(log.records, ["main", "main", "feat/x", "main", "feat/x"],
                                    ["2.1.1", "2.1.1", "2.1.1", "2.1.2", "2.1.2"]):
        rec.update(gitBranch=branch, version=version, entrypoint="cli")
    log.records[1]["effort"] = "high"
    log.records[3]["effort"] = "medium"
    log.record(type="permission-mode", permissionMode="default").record(type="permission-mode", permissionMode="auto")
    log.record(type="permission-mode", permissionMode="default")
    assert digest(tmp_path, log, capsys)["environment"] == {
        "branches": ["main", "feat/x"], "versions": ["2.1.1", "2.1.2"], "entrypoint": "cli",
        "permission_modes": ["default", "auto"], "efforts": ["high", "medium"]}


def test_models_and_lines_from_last_cost_state(tmp_path, capsys):
    usage_ = {"inputTokens": 646, "outputTokens": 5298, "thinkingTokens": 1219, "cacheReadInputTokens": 658354,
              "cacheCreationInputTokens": 34328, "webSearchRequests": 0, "costUSD": 0.5148388}
    log = (Log().prompt()
           .record(type="cost-state", totalLinesAdded=1, totalLinesRemoved=0, modelUsage={"old": usage_})
           .record(type="cost-state", totalLinesAdded=12, totalLinesRemoved=3, modelUsage={"claude-opus-5-5": usage_}))
    d = digest(tmp_path, log, capsys)
    assert d["models"] == {"claude-opus-5-5": {"cost_usd": 0.5148388, "input": 646, "output": 5298,
                                               "cache_read": 658354, "cache_write": 34328}}
    assert d["lines"] == {"added": 12, "removed": 3}


def test_edited_files(tmp_path, capsys):
    log = (Log().prompt()
           .call("Edit", {"file_path": "/work/repo/a.py"}).call("Write", {"file_path": "/other/b.md"})
           .call("Edit", {"file_path": "/work/repo/a.py"}).call("NotebookEdit", {"notebook_path": "/work/repo/n.ipynb"})
           .call("Read", {"file_path": "/work/repo/c.py"}))
    assert digest(tmp_path, log, capsys)["edited_files"] == ["a.py", "/other/b.md", "n.ipynb"]


def test_denials_and_api_errors(tmp_path, capsys):
    log = Log().prompt().bash("rm x").bash("git push").bash("ls")
    log.records[2]["toolDenialKind"] = "permission-rule"
    log.records[4]["toolDenialKind"] = "user-rejected"
    log.records[6]["toolDenialKind"] = "permission-rule"
    log.record(type="assistant", isApiErrorMessage=True, error="server_error", message={"role": "assistant", "content": []})
    log.record(type="assistant", isApiErrorMessage=True, error="rate_limit", message={"role": "assistant", "content": []})
    log.record(type="assistant", isApiErrorMessage=True, error="server_error", message={"role": "assistant", "content": []})
    d = digest(tmp_path, log, capsys)
    assert d["denials"] == {"permission-rule": 2, "user-rejected": 1}
    assert d["api_errors"] == {"rate_limit": 1, "server_error": 2}


def test_prs(tmp_path, capsys):
    pr = {"type": "pr-link", "prNumber": 12, "prUrl": "https://github.com/o/r/pull/12", "prRepository": "o/r"}
    log = Log().prompt().record(**pr).record(**pr).record(**{**pr, "prNumber": 13, "prUrl": "https://github.com/o/r/pull/13"})
    assert digest(tmp_path, log, capsys)["prs"] == [
        {"number": 12, "url": "https://github.com/o/r/pull/12", "repo": "o/r"},
        {"number": 13, "url": "https://github.com/o/r/pull/13", "repo": "o/r"}]


def test_empty_values(tmp_path, capsys):
    d = digest(tmp_path, Log().bash("ls"), capsys)
    assert {k: d[k] for k in list(d)[12:]} == {
        "human_turns": 0, "interruptions": 0, "active_s": 0, "initial_prompt": None, "start_skill": None,
        "skills": {}, "commands": {}, "compactions": [], "title": None,
        "environment": {"branches": [], "versions": [], "entrypoint": None, "permission_modes": [], "efforts": []},
        "models": {}, "lines": {"added": 0, "removed": 0}, "edited_files": [], "denials": {}, "api_errors": {},
        "prs": []}


def test_subagent_type_and_counts(tmp_path, capsys):
    sub_dir = tmp_path / SID / "subagents"
    sub_dir.mkdir(parents=True)
    (Log().prompt("review").bash("ls").call("Skill", {"skill": "code-review"}).call("Read", {"file_path": "/a"})
     .write(sub_dir / "agent-a1.jsonl"))
    (sub_dir / "agent-a1.meta.json").write_text('{"agentType": "Explore", "description": "Find callers"}')
    d = digest(tmp_path, Log().prompt().call("Agent", {"prompt": "review"}), capsys)
    sub = d["subagents"][0]
    assert {k: sub[k] for k in ("type", "description", "calls", "by_tool", "skills")} == {
        "type": "Explore", "description": "Find callers", "calls": 3,
        "by_tool": {"Bash": 1, "Read": 1, "Skill": 1}, "skills": {"code-review": 1}}
    assert d["skills"] == {}
    assert d["calls"]["by_tool"] == {"Agent": 1}


def test_totals_summed_over_resumed_processes(tmp_path, capsys):
    def state(start, cost, added, model_cost):
        return dict(type="cost-state", startTime=start, totalCostUSD=cost, totalLinesAdded=added, totalLinesRemoved=1,
                    modelUsage={"m": {"inputTokens": 10, "outputTokens": 1, "cacheReadInputTokens": 0,
                                      "cacheCreationInputTokens": 0, "costUSD": model_cost}})
    log = (Log().prompt()
           .record(**state(1, 1.0, 5, 1.0)).record(**state(1, 3.25, 32, 3.25))
           .record(**state(2, 0.25, 1, 0.25)).record(**state(2, 2.5, 146, 2.5)))
    d = digest(tmp_path, log, capsys)
    assert d["cost_usd"] == 5.75
    assert d["lines"] == {"added": 178, "removed": 2}
    assert d["models"] == {"m": {"cost_usd": 5.75, "input": 20, "output": 2, "cache_read": 0, "cache_write": 0}}


def test_opening_builtins_skipped(tmp_path, capsys):
    log = Log().command("model", "opus").command("clear").command("task", "go", skill=True).prompt("yes")
    d = digest(tmp_path, log, capsys)
    assert d["start_skill"] == {"name": "task", "args": "go"}
    assert d["initial_prompt"].startswith("<command-name>/task</command-name>")


def hook(tmp_path, capsys, monkeypatch, stdin, cfg=None, *flags):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return run(capsys, "--config", str(cfg or config(tmp_path)), "extract", "--hook", *flags,
               "--projects", str(tmp_path / "projects"))


def test_hook_writes_transcript(tmp_path, capsys, monkeypatch):
    log = Log().prompt().bash("ls")
    a = log.write(tmp_path / "projects" / "-old" / f"{SID}.jsonl")
    b = Log(cwd="/work/new").prompt("later").write(tmp_path / "projects" / "-new" / f"{SID}.jsonl")
    out_file = tmp_path / "out" / "2026-11-14" / f"{SID}.yaml"
    out_file.parent.mkdir(parents=True)
    out_file.write_text("stale")
    os.utime(a, (1, 1)), os.utime(b, (1, 1))
    payload = json.dumps({"session_id": SID, "transcript_path": str(b), "cwd": "/work/new",
                          "hook_event_name": "SessionEnd", "reason": "exit"})
    code, out, err = hook(tmp_path, capsys, monkeypatch, payload)
    assert (code, err) == (0, "")
    d = yaml.safe_load(out_file.read_text())
    assert d["human_turns"] == 2
    assert d["calls"]["total"] == 1


def test_hook_never_fails(tmp_path, capsys, monkeypatch):
    log = Log().prompt().write(tmp_path / "projects" / "-p" / f"{SID}.jsonl")
    empty = tmp_path / "projects" / "-p" / "empty.jsonl"
    empty.write_text("")
    good = json.dumps({"transcript_path": str(log)})
    for stdin, cfg in [("not json", None), ("{}", None), (good, tmp_path / "missing.yaml"),
                       (json.dumps({"transcript_path": str(empty)}), None),
                       (json.dumps({"transcript_path": str(tmp_path / "gone.jsonl")}), None)]:
        code, out, err = hook(tmp_path, capsys, monkeypatch, stdin, cfg)
        assert code == 0
        assert len(err.strip().splitlines()) == 1, (stdin, err)
    monkeypatch.setattr(sessions, "digest", lambda paths: 1 / 0)
    code, out, err = hook(tmp_path, capsys, monkeypatch, good)
    assert code == 0 and "ZeroDivisionError" in err


def test_hook_prints_the_written_path(tmp_path, capsys, monkeypatch):
    log = Log().prompt().bash("ls").write(tmp_path / "projects" / "-p" / f"{SID}.jsonl")
    code, out, err = hook(tmp_path, capsys, monkeypatch, json.dumps({"transcript_path": str(log)}), None,
                          "--print-path")
    assert (code, err) == (0, "")
    path = Path(out.strip())
    assert out == f"{path}\n"
    assert path == tmp_path / "out" / "2026-11-14" / f"{SID}.yaml"
    assert yaml.safe_load(path.read_text())["session"] == SID


def test_hook_prints_no_path_on_failure(tmp_path, capsys, monkeypatch):
    for stdin in ["not json", "{}", json.dumps({"transcript_path": str(tmp_path / "gone.jsonl")})]:
        code, out, err = hook(tmp_path, capsys, monkeypatch, stdin, None, "--print-path")
        assert (code, out) == (0, ""), stdin
        assert len(err.strip().splitlines()) == 1, (stdin, err)


def test_print_path_needs_hook(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        sessions.main(["--config", str(config(tmp_path)), "extract", "--print-path"])
    assert exc.value.code == 2
    assert "--print-path" in capsys.readouterr().err


def test_hook_without_pyyaml_exits_0():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.py")
    code = ("import runpy, sys; sys.modules['yaml'] = None; "
            f"sys.argv = [{script!r}, 'extract', '--hook']; runpy.run_path({script!r}, run_name='__main__')")
    done = subprocess.run([sys.executable, "-c", code], input="{}", capture_output=True, text=True)
    assert done.returncode == 0
    assert len(done.stderr.strip().splitlines()) == 1 and "PyYAML" in done.stderr


def test_hook_rejects_named_logs(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        sessions.main(["--config", str(config(tmp_path)), "extract", "--hook", "a.jsonl"])
    assert exc.value.code == 2
    assert "--hook" in capsys.readouterr().err


def test_request_copies_are_not_calls(tmp_path, capsys):
    log = Log().prompt().call("Skill", {"skill": "tdd"}).bash("ls")
    copy = {"type": "api-request-blob", "message": {"role": "assistant", "content": [
        dict(log.records[1]["message"]["content"][0])]}}
    log.records.insert(2, copy)
    log.records.append(copy)
    d = digest(tmp_path, log, capsys)
    assert d["calls"] == {"total": 2, "by_tool": {"Bash": 1, "Skill": 1}}
    assert d["skills"] == {"tdd": 1}
    assert d["repeats"] == []
