"""Session log extraction for Claude Code: one YAML file per session.

  sessions.py extract [log ...]   write <out>/<local start date>/<session-id>.yaml for each named log; with
                                  none, for every session log under ~/.claude/projects whose file is missing
                                  or older than the log
  sessions.py extract <id> ...    the same for each session id or unique prefix, only when its file is missing
                                  or stale; exit 1 when an id matches no log or a prefix matches several
  sessions.py extract ... --print-path
                                  print only the path of each named session's file, one per line
  sessions.py extract --hook     the same for the log named by the SessionEnd hook JSON on stdin; never fails
  sessions.py extract --hook --print-path
                                  the same, printing only the written file's path (nothing on failure), so the
                                  hook can pipe it into another script
  sessions.py transcript <id>     print the session's conversation, compact: prompts and agent text whole,
                                  thinking and call results cut, calls numbered as the session file numbers
                                  them, skills, compactions, interruptions and subagents one line each
    --agent <id>                  a subagent's log instead, with its own call numbers
    --from N --to M               only calls N to M and what lies between them
    --full                        nothing cut
    --lines N                     thinking lines and result lines kept at each end (default 3); an error
                                  result always keeps its first 20 lines

Every file is read and written as UTF-8, whatever the locale.
Reads config.yaml beside this skill's SKILL.md (see config.example.yaml), or --config.
"""
import argparse
import glob
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
    print("sessions.py needs PyYAML: pip install pyyaml", file=sys.stderr)
    # The SessionEnd hook must never fail the session's exit.
    sys.exit(0 if "--hook" in sys.argv else 1)

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
# transcript: lines kept of thinking and of each end of a result, lines of an error, characters of an input.
TRANSCRIPT_LINES = 3
ERROR_LINES = 20
INPUT_LINE_MAX = 200
PROJECTS = Path.home() / ".claude" / "projects"
CALL_INPUT_FIELDS = ("command", "file_path", "notebook_path", "pattern", "url", "query", "skill", "description")
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
TASK_ID = re.compile(r"<task-id>([^<]+)</task-id>")
SKILL_BODY = "Base directory for this skill"


class NotASessionLog(Exception):
    pass


def read_records(path):
    """The JSON records of a session log; raises NotASessionLog when it holds no message."""
    path = Path(path)
    if not path.is_file():
        raise NotASessionLog(path)
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
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
    """Ordered tool calls: {n, id, tool, input, result, is_error}, results paired by tool_use id. Only the
    conversation's own records count: others, like api-request-blob, repeat its content."""
    out, by_id = [], {}
    for rec in records:
        if rec.get("type") not in ("assistant", "user"):
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                call = {"n": len(out) + 1, "id": block.get("id"), "tool": block.get("name"),
                        "input": block.get("input") or {},
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
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
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


def _stamps(records):
    """The timestamps of the records, in time order."""
    return sorted((r["timestamp"] for r in records if r.get("timestamp")), key=_time)


def _iso(ts):
    return _time(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_records(paths):
    """The records of one session's logs (one per project folder it ran in), joined in order of their first
    record. Every reader of a session starts here, so call numbers agree. Raises NotASessionLog when none is."""
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
    return [r for _, recs in sorted(parts, key=lambda part: part[0]) for r in recs]


def digest(paths):
    """One session from its logs, joined by session_records."""
    records = session_records(paths)
    session = next((r["sessionId"] for r in records if r.get("sessionId")), Path(paths[0]).stem)
    project = next((r["cwd"] for r in records if r.get("cwd")), None)
    stamps = _stamps(records)
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


def _clock(rec):
    return _time(rec["timestamp"]).strftime("%H:%M:%S") if rec.get("timestamp") else "--:--:--"


def _indent(lines):
    return ["  " + line for line in lines]


def _one_line(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def call_input(c):
    """What a call asked for, for a reader: the command, the path or pattern, else the input as JSON."""
    inp = c["input"]
    for key in CALL_INPUT_FIELDS:
        if isinstance(inp.get(key), str):
            return inp[key]
    return json.dumps(inp, sort_keys=True, ensure_ascii=False)


def result_lines(c, lines):
    """A call's result cut for reading: head and tail on success, the first ERROR_LINES on an error; whole
    when lines is None."""
    text = c["result"].splitlines()
    if lines is None:
        return text
    if c["is_error"]:
        more = len(text) - ERROR_LINES
        return text[:ERROR_LINES] + ([f"… {more} more lines"] if more > 0 else [])
    if len(text) <= 2 * lines:
        return text
    return text[:lines] + [f"… {len(text) - 2 * lines} lines …"] + text[-lines:]


def _lines_label(text):
    return f"({len(str(text).splitlines())} lines)"


def marker_lines(rec):
    """The one line (or the queued prompt, whole) a non-message record leaves in a transcript, else []."""
    clock = f"[{_clock(rec)}]"
    if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
        meta = rec.get("compactMetadata") or {}
        return [f"{clock} ── compacted ({meta.get('trigger')}, {meta.get('preTokens')} → {meta.get('postTokens')} "
                f"tokens) ──"]
    a = rec.get("attachment") if rec.get("type") == "attachment" else None
    if not isinstance(a, dict):
        return []
    if a.get("type") == "edited_text_file":
        return [f"{clock} edited {a.get('filename')} {_lines_label(a.get('snippet', ''))}"]
    if a.get("type") == "nested_memory":
        return [f"{clock} memory {a.get('path')} {_lines_label((a.get('content') or {}).get('content', ''))}"]
    if a.get("type") == "queued_command":
        origin, prompt = a.get("origin") or {}, a.get("prompt")
        prompt = prompt if isinstance(prompt, str) else json.dumps(prompt, ensure_ascii=False)
        if origin.get("kind", "human") != "human":
            return relayed(clock, origin, origin.get("handbackReportText") or prompt)
        return [f"{clock} user (queued)", *_indent(prompt.splitlines())]
    return []


def relayed(clock, origin, text):
    """One line for a message relayed to the session by a subagent or a background task, not typed."""
    if origin.get("handback") or origin.get("kind") == "peer":
        return [f"{clock} hand-back from agent {origin.get('from')} {_lines_label(text)}"]
    task = TASK_ID.search(text)
    name = f" {task.group(1)}" if task else ""
    return [f"{clock} {str(origin.get('kind')).replace('-', ' ')}{name} {_lines_label(text)}"]


def agent_ids(records):
    """The subagent each Agent call started: tool_use id -> agent id, read off the result record."""
    out = {}
    for rec in records:
        agent = (rec.get("toolUseResult") or {}).get("agentId") if isinstance(rec.get("toolUseResult"), dict) else None
        content = (rec.get("message") or {}).get("content")
        if agent and isinstance(content, list):
            out.update({b.get("tool_use_id"): agent for b in content if b.get("type") == "tool_result"})
    return out


def call_lines(c, clock, lines, agents):
    """A call's head line, then its result; whole (the input on its own lines) when lines is None."""
    inp = call_input(c).splitlines() or [""]
    first = _one_line(" ".join(inp), INPUT_LINE_MAX) if lines is not None else inp[0]
    rest = [f"> {line}" for line in inp[1:]] if lines is None else []
    tail = f" → agent {agents[c['id']]}" if c["id"] in agents else ""
    head = f"[{clock}] #{c['n']} {c['tool']} {first}{' error' if c['is_error'] else ''}{tail}"
    return [head, *_indent(rest + result_lines(c, lines))]


def entries(records, lines, agents):
    """The transcript as (call number or None, lines) entries, in log order."""
    by_id = {c["id"]: c for c in calls(records)}
    out = []
    for rec in records:
        kind = rec.get("type")
        if kind not in ("user", "assistant"):
            out.append((None, marker_lines(rec)))
            continue
        clock = _clock(rec)
        if kind == "user":
            text = prompt_text(rec)
            body = user_text(rec) if rec.get("isMeta") else None
            origin = rec.get("origin") or {}
            if origin.get("kind", "human") != "human" and not rec.get("isCompactSummary"):
                out.append((None, relayed(f"[{clock}]", origin, user_text(rec) or "")))
            elif text and text.startswith(INTERRUPTED):
                out.append((None, [f"[{clock}] ── interrupted ──"]))
            elif text and text.startswith(NOT_TYPED):
                continue
            elif text:
                out.append((None, [f"[{clock}] user", *_indent(text.splitlines())]))
            elif body and body.startswith(SKILL_BODY):
                name = re.split(r"[\\/]", body.splitlines()[0].removeprefix(SKILL_BODY).strip(" :"))[-1]
                out.append((None, [f"[{clock}] skill {name} {_lines_label(body)}"]))
            continue
        content = (rec.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "text" and block.get("text", "").strip():
                out.append((None, [f"[{clock}] agent", *_indent(block["text"].splitlines())]))
            elif block.get("type") == "thinking" and block.get("thinking", "").strip():
                text = block["thinking"].splitlines()
                keep = len(text) if lines is None else lines
                more = f" (+{len(text) - keep} lines)" if len(text) > keep else ""
                out.append((None, [f"[{clock}] thinking{more}", *_indent(text[:keep])]))
            elif block.get("type") == "tool_use" and block.get("id") in by_id:
                c = by_id[block["id"]]
                out.append((c["n"], call_lines(c, clock, lines, agents)))
    return out


def transcript(records, lines=TRANSCRIPT_LINES, first=None, last=None):
    """The conversation of a session as text lines, in log order: typed prompts and agent text whole, thinking
    cut to its first lines, each call numbered as calls() numbers it, its result cut; skills, edited files,
    memories, hand-backs, compactions and interruptions one line each. Other records (api-request blobs,
    hooks, snapshots) and harness notes print nothing. lines None prints all in full; first and last keep
    the entries from call first to call last."""
    items = entries(records, lines, agent_ids(records))
    numbers = [i for i, (n, _) in enumerate(items) if n is not None]
    lo = next((i for i in numbers if items[i][0] >= first), len(items)) if first else 0
    hi = max((i for i in numbers if items[i][0] <= last), default=-1) + 1 if last else len(items)
    return [line for _, block in items[lo:hi] for line in block]


def transcript_header(records, metrics, agent=None):
    """session, the subagent when one is read (id, type and description), project, span and metrics file."""
    stamps = _stamps(records)
    return [f"session  {next((r['sessionId'] for r in records if r.get('sessionId')), '')}",
            *([f"agent    {agent}"] if agent else []),
            f"project  {next((r['cwd'] for r in records if r.get('cwd')), '')}",
            f"span     {_iso(stamps[0])} → {_iso(stamps[-1])}" if stamps else "span",
            f"metrics  {metrics[0] if metrics else '(not written)'}", ""]


def load_config(path):
    """The out folder from config.yaml, ~ expanded; or None and the problem."""
    problem = None
    if not path.is_file():
        problem = "missing"
    else:
        try:
            cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
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
    path.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8")
    os.utime(path, (newest, newest))
    return True


def long_path(path):
    """On Windows, an absolute drive path in its extended form, so stat, glob and open reach past 260 characters
    (a desktop scratch workspace can make a project folder name that long)."""
    path = os.path.abspath(path)
    if sys.platform == "win32" and path[1:3] == ":\\":
        path = "\\\\?\\" + path
    return Path(path)


def is_fresh(out, session, logs):
    """True when the session's file exists and is not older than any of its logs."""
    newest = max(log.stat().st_mtime for log in logs)
    return any(f.stat().st_mtime >= newest for f in session_files(out, session))


def resolve(name, projects):
    """The one session id under projects whose log name starts with name; ValueError when none or several."""
    ids = sorted({log.stem for log in long_path(projects).glob(f"*/{glob.escape(name)}*.jsonl")})
    if not ids:
        raise ValueError(f"no session log matches {name}")
    if len(ids) > 1:
        raise ValueError(f"ambiguous {name}: {', '.join(ids)}")
    return ids[0]


def extract(out, logs, projects, ids=()):
    """Write the file of each named log, and of each named session id whose file is missing or stale; with
    neither, of every session log under projects whose file is missing or stale. Returns (written, up to
    date, not session logs)."""
    # A session id has a log in each project folder it ran in (a moved project): its file joins them all.
    groups = {}
    logs, projects = [long_path(log) for log in logs], long_path(projects)
    named = logs + [log for s in ids for log in sorted(projects.glob(f"*/{s}.jsonl"))]
    for log in named or sorted(projects.glob("*/*.jsonl")):
        groups.setdefault(log.stem, {log}).update(projects.glob(f"*/{log.stem}.jsonl"))
    always = {log.stem for log in logs}
    fresh = {s for s, group in groups.items() if s not in always and is_fresh(out, s, group)}
    count = Counter(write_session(out, s, sorted(group)) for s, group in groups.items() if s not in fresh)
    return count[True], len(fresh), count[False]


def hook(config, projects, print_path=False):
    """SessionEnd hook: the session's transcript_path comes as JSON on stdin. Every failure is one stderr
    line and exit 0, so ending a session never blocks. With print_path, stdout carries only the written
    file's path, for a script piped after the hook."""
    try:
        log = Path(json.load(sys.stdin)["transcript_path"])
        out, problem = load_config(config)
        if problem:
            raise RuntimeError(problem)
        written, _, skipped = extract(out, [log], projects)
        if skipped:
            raise RuntimeError(f"not a session log: {log}")
        if print_path:
            print(*session_files(out, log.stem), sep="\n")
        else:
            print(f"{written} written")
    except Exception as exc:  # noqa: BLE001 - a hook must never fail the session's exit
        print(f"session-log hook: {exc!r}", file=sys.stderr)
    return 0


def subagent_log(logs, agent):
    """The records of a session's subagent log, and its header label (id, type and description from its meta
    file). Raises NotASessionLog when no log of the session has that subagent."""
    for log in logs:
        path = log.parent / log.stem / "subagents" / f"agent-{agent}.jsonl"
        if not path.is_file():
            continue
        records = read_records(path)
        try:
            meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        label = f"{agent} ({meta.get('agentType')}: {meta.get('description')})" if meta else agent
        return records, label
    raise NotASessionLog(agent)


def print_transcript(args):
    """The transcript command: the session's header, then its conversation, as UTF-8 whatever the console."""
    try:
        session = resolve(args.session, args.projects)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    projects = long_path(args.projects)
    logs = sorted(projects.glob(f"*/{session}.jsonl"))
    try:
        records, agent = session_records(logs), None
    except NotASessionLog:
        print(f"not a session log: {session}", file=sys.stderr)
        return 1
    if args.agent:
        try:
            records, agent = subagent_log(logs, args.agent)
        except NotASessionLog:
            print(f"no subagent {args.agent} in {session}", file=sys.stderr)
            return 1
    out, problem = load_config(args.config)
    metrics = session_files(out, session) if not problem else []
    lines = None if args.full else args.lines
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    body = transcript(records, lines, args.start, args.to)
    print(*transcript_header(records, metrics, agent), *body, sep="\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config.yaml",
                        help="config.yaml to read (default: the one beside SKILL.md)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="write the session file of each named log")
    e.add_argument("logs", nargs="*", metavar="log|id",
                   help="logs to write whatever their mtime, or session ids (or unique prefixes) to write when "
                        "missing or stale (default: every stale log)")
    e.add_argument("--hook", action="store_true",
                   help="SessionEnd hook: read the log from the hook JSON on stdin; never exit non-zero")
    e.add_argument("--print-path", action="store_true",
                   help="print only the path of each named session's file (with --hook: nothing on failure)")
    e.add_argument("--projects", type=Path, default=PROJECTS,
                   help="folder of the project log folders (default: ~/.claude/projects)")
    t = sub.add_parser("transcript", help="print a session's conversation, compact, with its call numbers")
    t.add_argument("session", metavar="id", help="session id or unique prefix")
    t.add_argument("--projects", type=Path, default=PROJECTS,
                   help="folder of the project log folders (default: ~/.claude/projects)")
    t.add_argument("--agent", metavar="id", help="print this subagent's log instead, with its own call numbers")
    t.add_argument("--from", dest="start", type=int, metavar="N", help="start at call N")
    t.add_argument("--to", type=int, metavar="M", help="end after call M")
    t.add_argument("--full", action="store_true", help="truncate nothing")
    t.add_argument("--lines", type=int, default=TRANSCRIPT_LINES, metavar="N",
                   help=f"thinking lines and result lines kept at each end (default: {TRANSCRIPT_LINES})")
    args = parser.parse_args(argv)
    if args.cmd == "transcript":
        if args.lines < 1:
            parser.error("--lines must be 1 or more")
        return print_transcript(args)
    if args.hook and args.logs:
        parser.error("--hook reads its log from stdin: name no logs")

    if args.hook:
        return hook(args.config, args.projects, args.print_path)
    out, problem = load_config(args.config)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    logs, ids, sessions = [], [], []
    try:
        for name in args.logs:
            if name.endswith(".jsonl") or long_path(name).is_file():
                logs.append(Path(name))
                sessions.append(Path(name).stem)
            else:
                ids.append(resolve(name, args.projects))
                sessions.append(ids[-1])
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    written, fresh, skipped = extract(out, logs, args.projects, ids)
    if args.print_path:
        for s in sessions:
            print(*session_files(out, s), sep="\n")
    else:
        print(f"{written} written, {fresh} up to date, {skipped} not session logs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
