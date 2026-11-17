"""Session log extraction for Claude Code: one YAML file per session.

  sessions.py extract [log ...]   write <out>/<local start date>/<session-id>.yaml for each named log; with
                                  none, for every session log under ~/.claude/projects whose file is missing
                                  or older than the log

Reads config.yaml beside this skill's SKILL.md (see config.example.yaml), or --config.
The digest functions are a copy of retro-report's retro.py.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("sessions.py needs PyYAML: pip install pyyaml")

# Error classes read off a result's text, after tokeneconomizer's observe.py; first match wins.
ERROR_PATTERNS = [
    ("command_missing", re.compile(r"command not found|: not found$|is not recognized as")),
    ("module_missing", re.compile(r"ModuleNotFoundError|No module named|Cannot find module", re.I)),
    ("file_missing", re.compile(r"No such file or directory|File does not exist|ENOENT", re.I)),
    ("permission_denied", re.compile(r"Permission denied|EACCES|Operation not permitted", re.I)),
]
LINE_MAX = 200
INPUT_MAX = 120
STREAK_MIN = 3
# Search tools, each with the input field that names what it searched.
SEARCH_TOOL_FIELD = {"Grep": "pattern", "Glob": "pattern", "Read": "file_path"}
SEARCH_HEADS = {"grep", "rg", "find", "ls", "cat", "head", "tail", "sed", "wc"}
# Commands that neither search nor change anything: they keep a shell search a search.
NEUTRAL_HEADS = {"cd", "echo", "sort", "uniq", "xargs", "true"}
# Shell words followed by a command; the command is the segment's head.
PREFIX_WORDS = {"do", "then", "else", "if"}
# Shell words whose segment runs no command of its own.
SKIP_WORDS = {"for", "done", "fi"}
SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")
# A redirect to a file; /dev/null and &N are not writes.
WRITE_REDIRECT = re.compile(r">>?\s*(?!/dev/null\b|&)\S")
WRITE_FLAGS = {"-i", "-delete"}
# Values that may change during a session: key in the file, record field.
ENVIRONMENT_FIELDS = {"branches": "gitBranch", "versions": "version", "permission_modes": "permissionMode",
                      "efforts": "effort"}
MODEL_FIELDS = {"cost_usd": "costUSD", "input": "inputTokens", "output": "outputTokens",
                "cache_read": "cacheReadInputTokens", "cache_write": "cacheCreationInputTokens"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
TOKEN_FIELDS = {"input": "input_tokens", "output": "output_tokens",
                "cache_read": "cache_read_input_tokens", "cache_write": "cache_creation_input_tokens"}

# User text that the harness wrote, not the human: command output and interruption notes.
INTERRUPTED = "[Request interrupted"
NOT_TYPED = ("<local-command-stdout>", "<local-command-stderr>", "<bash-stdout>", "<bash-stderr>", INTERRUPTED)

COMMAND_NAME = re.compile(r"<command-name>/?([^<]+)</command-name>")
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SKILL_BODY = "Base directory for this skill"


class NotASessionLog(Exception):
    pass


def read_records(path):
    """The JSON records of a session log; raises NotASessionLog when it holds no message."""
    path = Path(path)
    if not path.is_file():
        raise NotASessionLog(path)
    records = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    if not any(r.get("type") in ("user", "assistant") and isinstance(r.get("message"), dict) for r in records):
        raise NotASessionLog(path)
    return records


def calls(records):
    """Ordered tool calls: {n, tool, input, result, is_error}, results paired by tool_use id."""
    out, by_id = [], {}
    for rec in records:
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                call = {"n": len(out) + 1, "tool": block.get("name"), "input": block.get("input") or {},
                        "result": "", "is_error": False}
                out.append(call)
                by_id[block.get("id")] = call
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                call = by_id[block["tool_use_id"]]
                call["result"] = result_text(block.get("content"))
                call["is_error"] = bool(block.get("is_error"))
    return out


def user_text(rec):
    """The text of a user record; None when it holds a tool result."""
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return content if isinstance(content, str) else None


def prompt_text(rec):
    """The text of a user record a human typed or pasted, else None: harness notes, compact summaries,
    tool results and subagent hand-backs are not. The harness output in NOT_TYPED passes, for callers
    to count apart."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary"):
        return None
    if (rec.get("origin") or {}).get("kind", "human") != "human":
        return None
    text = user_text(rec)
    return text if text and text.strip() else None


def prompt_texts(records):
    return [t for t in map(prompt_text, records) if t]


def typed_commands(records):
    """Each typed /command: {name, args, skill, text}. A skill command is the one whose next user record is
    the skill's body, which the harness adds as a meta record; built-ins have none."""
    users = [r for r in records if r.get("type") == "user"]
    out = []
    for i, rec in enumerate(users):
        text = prompt_text(rec)
        name = command_name(text or "")
        if not name:
            continue
        nxt = users[i + 1] if i + 1 < len(users) else {}
        args = COMMAND_ARGS.search(text)
        out.append({"name": name, "args": args.group(1) if args else "", "text": text,
                    "skill": bool(nxt.get("isMeta")) and (user_text(nxt) or "").startswith(SKILL_BODY)})
    return out


def skill_counts(commands, call_list):
    names = [c["name"] for c in commands if c["skill"]]
    names += [c["input"].get("skill") for c in call_list if c["tool"] == "Skill" and c["input"].get("skill")]
    return sorted_counts(names)


def sorted_counts(values):
    return dict(sorted(Counter(values).items()))


def start_skill(first, commands):
    """The skill that opened the session: its command is the first prompt."""
    c = next((c for c in commands if c["text"] == first), None)
    return {"name": c["name"], "args": c["args"]} if c and c["skill"] else None


def command_name(text):
    """The name of a typed /command, or None when the text is not one."""
    m = COMMAND_NAME.search(text)
    return m.group(1).strip() if m else None


def initial_prompt(prompts, commands):
    """The first prompt the human typed, past the built-in commands (/clear, /model...) that open the session."""
    builtins = {c["text"] for c in commands if not c["skill"]}
    return next((t for t in prompts if not t.startswith(NOT_TYPED) and t not in builtins), None)


def compactions(records):
    out = []
    for r in records:
        if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
            meta = r.get("compactMetadata") or {}
            out.append({"time": _iso(r["timestamp"]) if r.get("timestamp") else None, "trigger": meta.get("trigger"),
                        "pre_tokens": meta.get("preTokens"), "post_tokens": meta.get("postTokens"),
                        "duration_ms": meta.get("durationMs")})
    return out


def title(records):
    """The name the user gave with /rename, else the last one the harness generated."""
    for kind, field in (("custom-title", "customTitle"), ("ai-title", "aiTitle")):
        titles = [r[field] for r in records if r.get("type") == kind and r.get(field)]
        if titles:
            return titles[-1]
    return None


def environment(records):
    """Each changing value as its distinct values in order of first appearance, and the entrypoint."""
    out = {key: list(dict.fromkeys(r[field] for r in records if r.get(field)))
           for key, field in ENVIRONMENT_FIELDS.items()}
    out["entrypoint"] = next((r["entrypoint"] for r in records if r.get("entrypoint")), None)
    return out


def process_states(records):
    """The last cost-state of each process: the record holds running totals that restart when a session is
    resumed, under a new startTime."""
    last = {}
    for r in records:
        if r.get("type") == "cost-state":
            last[r.get("startTime")] = r
    return list(last.values())


def models(states):
    out = {}
    for state in states:
        for model, u in (state.get("modelUsage") or {}).items():
            totals = out.setdefault(model, dict.fromkeys(MODEL_FIELDS, 0))
            for key, field in MODEL_FIELDS.items():
                totals[key] += u.get(field) or 0
    return out


def lines(states):
    return {"added": sum(s.get("totalLinesAdded") or 0 for s in states),
            "removed": sum(s.get("totalLinesRemoved") or 0 for s in states)}


def edited_files(call_list, cwd):
    """Distinct files the session edited, relative to its cwd when inside it."""
    paths = [c["input"].get("file_path") or c["input"].get("notebook_path")
             for c in call_list if c["tool"] in EDIT_TOOLS]
    root = (cwd or "").rstrip("/") + "/"
    return list(dict.fromkeys(p.removeprefix(root) if cwd and p.startswith(root) else p for p in paths if p))


def prs(records):
    out = {}
    for r in records:
        if r.get("type") == "pr-link" and r.get("prUrl"):
            out.setdefault(r["prUrl"], {"number": r.get("prNumber"), "url": r["prUrl"], "repo": r.get("prRepository")})
    return list(out.values())


def field_counts(records, field, when=lambda r: True):
    """How many records hold each value of field, sorted by value."""
    return sorted_counts(r[field] for r in records if r.get(field) and when(r))


def active_s(records):
    return int(sum(r.get("durationMs") or 0 for r in records
                   if r.get("type") == "system" and r.get("subtype") == "turn_duration") / 1000)


def result_text(content):
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def failures(call_list):
    """Calls grouped by error class: a line matching a pattern, else `other` when the tool said is_error.

    Only shell output and results marked is_error are scanned: a Read of a file that quotes an error is no failure."""
    out = {}
    for c in call_list:
        if c["tool"] != "Bash" and not c["is_error"]:
            continue
        lines = c["result"].splitlines()
        hit = next(((cls, line) for line in lines for cls, rx in ERROR_PATTERNS if rx.search(line)), None)
        if hit is None and c["is_error"]:
            hit = ("other", next((ln for ln in lines if ln.strip()), ""))
        if hit:
            cls, line = hit
            out.setdefault(cls, []).append({"call": c["n"], "tool": c["tool"], "line": line.strip()[:LINE_MAX]})
    order = [cls for cls, _ in ERROR_PATTERNS] + ["other"]
    return {cls: out[cls] for cls in order if cls in out}


def call_text(c):
    """What a call asked for, in one line: the command, the searched value, or the input as JSON."""
    if c["tool"] == "Bash":
        return str(c["input"].get("command", ""))
    key = SEARCH_TOOL_FIELD.get(c["tool"])
    if key and key in c["input"]:
        return f"{c['tool']} {c['input'][key]}"
    return json.dumps(c["input"], sort_keys=True)


def repeats(call_list):
    """Calls made more than once with identical input, in order of first use."""
    seen, first = Counter(), {}
    for c in call_list:
        key = (c["tool"], json.dumps(c["input"], sort_keys=True))
        seen[key] += 1
        first.setdefault(key, c)
    return [{"tool": key[0], "input": call_text(first[key])[:INPUT_MAX], "count": n}
            for key, n in seen.items() if n > 1]


def shell_heads(command):
    """The command each segment runs, past loop and if words; None for a segment that writes a file."""
    heads = []
    for seg in SEGMENT_SPLIT.split(command):
        words = seg.split()
        if WRITE_REDIRECT.search(seg) or WRITE_FLAGS & set(words):
            heads.append(None)
            continue
        while words and words[0] in PREFIX_WORDS:
            words = words[1:]
        if words and words[0] not in SKIP_WORDS:
            heads.append(words[0].lstrip("("))
    return heads


def is_search(c):
    if c["tool"] in SEARCH_TOOL_FIELD:
        return True
    if c["tool"] != "Bash":
        return False
    heads = shell_heads(call_text(c))
    return any(h in SEARCH_HEADS for h in heads) and all(h in SEARCH_HEADS | NEUTRAL_HEADS for h in heads)


def search_streaks(call_list):
    """Runs of STREAK_MIN or more search calls in a row."""
    runs, run = [], []
    for c in call_list + [None]:
        if c is not None and is_search(c):
            run.append(c)
            continue
        if len(run) >= STREAK_MIN:
            runs.append({"calls": [r["n"] for r in run], "commands": [call_text(r)[:INPUT_MAX] for r in run]})
        run = []
    return runs


def tokens(records):
    """Tokens summed once per message id: a message spread over several lines repeats its usage."""
    by_id = {}
    for rec in records:
        msg = rec.get("message") or {}
        if isinstance(msg.get("usage"), dict):
            by_id[msg.get("id") or id(rec)] = msg["usage"]
    return {k: sum(int(u.get(f) or 0) for u in by_id.values()) for k, f in TOKEN_FIELDS.items()}


def cost_usd(states):
    """The session's own total, summed over its processes; None when it recorded none."""
    totals = [s["totalCostUSD"] for s in states if "totalCostUSD" in s]
    return sum(totals) if totals else None


def subagents(path):
    """Each subagent log beside the session (<session>/subagents/agent-<id>.jsonl), digested apart: its
    counts are its own and never added to the session's."""
    out = []
    for log in sorted((Path(path).parent / Path(path).stem / "subagents").glob("agent-*.jsonl")):
        try:
            records = read_records(log)
        except NotASessionLog:
            continue
        meta_path = log.with_suffix(".meta.json")
        try:
            meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        except ValueError:
            meta = {}
        call_list = calls(records)
        out.append({"id": log.stem.removeprefix("agent-"), "type": meta.get("agentType"),
                    "description": meta.get("description"), "calls": len(call_list),
                    "by_tool": sorted_counts(c["tool"] for c in call_list),
                    "skills": skill_counts(typed_commands(records), call_list), "tokens": tokens(records)})
    return out


def _time(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(ts):
    return _time(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(paths):
    """One session from its logs (one per project folder it ran in), joined in order of their first record."""
    parts = []
    for path in paths:
        try:
            records = read_records(path)
        except NotASessionLog:
            continue
        stamps = [_time(r["timestamp"]) for r in records if r.get("timestamp")]
        if stamps:
            parts.append((min(stamps), records))
    if not parts:
        raise NotASessionLog(paths[0])
    records = [r for _, recs in sorted(parts, key=lambda part: part[0]) for r in recs]
    session = next((r["sessionId"] for r in records if r.get("sessionId")), Path(paths[0]).stem)
    project = next((r["cwd"] for r in records if r.get("cwd")), None)
    stamps = sorted((r["timestamp"] for r in records if r.get("timestamp")), key=_time)
    call_list = calls(records)
    prompts = prompt_texts(records)
    commands = typed_commands(records)
    first = initial_prompt(prompts, commands)
    states = process_states(records)
    return {
        "session": session,
        "project": project,
        "start": _iso(stamps[0]) if stamps else None,
        "end": _iso(stamps[-1]) if stamps else None,
        "duration_s": int((_time(stamps[-1]) - _time(stamps[0])).total_seconds()) if stamps else 0,
        "calls": {"total": len(call_list), "by_tool": sorted_counts(c["tool"] for c in call_list)},
        "failures": failures(call_list),
        "repeats": repeats(call_list),
        "search_streaks": search_streaks(call_list),
        "tokens": tokens(records),
        "cost_usd": cost_usd(states),
        "subagents": [a for path in paths for a in subagents(path)],
        "title": title(records),
        "initial_prompt": first,
        "start_skill": start_skill(first, commands),
        "skills": skill_counts(commands, call_list),
        "commands": sorted_counts(c["name"] for c in commands if not c["skill"]),
        "human_turns": sum(not t.startswith(NOT_TYPED) for t in prompts),
        "interruptions": sum(t.startswith(INTERRUPTED) for t in prompts),
        "active_s": active_s(records),
        "compactions": compactions(records),
        "environment": environment(records),
        "models": models(states),
        "lines": lines(states),
        "edited_files": edited_files(call_list, project),
        "denials": field_counts(records, "toolDenialKind"),
        "api_errors": field_counts(records, "error", lambda r: r.get("isApiErrorMessage")),
        "prs": prs(records),
    }


def load_config(path):
    """The out folder from config.yaml, ~ expanded; or None and the problem."""
    problem = None
    if not path.is_file():
        problem = "missing"
    else:
        try:
            cfg = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            cfg, problem = None, f"not valid YAML: {str(e).splitlines()[0]}"
        if problem is None and not (isinstance(cfg, dict) and isinstance(cfg.get("out"), str) and cfg["out"].strip()):
            problem = "out: must be a path"
    if problem:
        return None, f"{path}: {problem}; see config.example.yaml"
    return Path(cfg["out"]).expanduser(), None


def session_files(out, session):
    """The files a session has under out, one per date folder it was written to (normally one)."""
    return list(out.glob(f"*/{session}.yaml"))


def write_session(out, session, logs):
    """Digest one session's logs into <out>/<local start date>/<session>.yaml, dropping copies in other date folders,
    with the mtime of its newest log, so a log that grows later is newer than the file. False when none is a
    session log."""
    mtimes = [log.stat().st_mtime for log in logs if log.is_file()]       # read before the logs, not after
    try:
        d = digest(logs)
    except NotASessionLog:
        return False
    newest = max(mtimes)
    path = out / _time(d["start"]).astimezone().strftime("%Y-%m-%d") / f"{session}.yaml"
    for old in session_files(out, session):
        if old != path:
            old.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=200))
    os.utime(path, (newest, newest))
    return True


def is_fresh(out, session, logs):
    """True when the session's file exists and is not older than any of its logs."""
    newest = max(log.stat().st_mtime for log in logs)
    return any(f.stat().st_mtime >= newest for f in session_files(out, session))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config.yaml",
                        help="config.yaml to read (default: the one beside SKILL.md)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="write the session file of each named log")
    e.add_argument("logs", nargs="*", help="logs to write whatever their mtime (default: every stale one)")
    e.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects",
                   help="folder of the project log folders (default: ~/.claude/projects)")
    args = parser.parse_args(argv)

    out, problem = load_config(args.config)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    # A session id has a log in each project folder it ran in (a moved project): its file joins them all.
    groups = {}
    for log in [Path(name) for name in args.logs] or sorted(args.projects.glob("*/*.jsonl")):
        groups.setdefault(log.stem, {log}).update(args.projects.glob(f"*/{log.stem}.jsonl"))
    fresh = set() if args.logs else {s for s, logs in groups.items() if is_fresh(out, s, logs)}
    count = Counter(write_session(out, s, sorted(logs)) for s, logs in groups.items() if s not in fresh)
    print(f"{count[True]} written, {len(fresh)} up to date, {count[False]} not session logs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
