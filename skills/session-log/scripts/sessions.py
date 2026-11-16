"""Session log extraction for Claude Code: one YAML file per session.

  sessions.py extract [log ...]   write <out>/<local start date>/<session-id>.yaml for each named log

Reads config.yaml beside this skill's SKILL.md (see config.example.yaml), or --config.
The digest functions are a copy of retro-report's retro.py.
"""
import argparse
import json
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
TOKEN_FIELDS = {"input": "input_tokens", "output": "output_tokens",
                "cache_read": "cache_read_input_tokens", "cache_write": "cache_creation_input_tokens"}


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


def cost_usd(records):
    """The session's own total from its last cost-state record; None when it recorded none."""
    totals = [r["totalCostUSD"] for r in records if r.get("type") == "cost-state" and "totalCostUSD" in r]
    return totals[-1] if totals else None


def subagents(path):
    """Each subagent log beside the session (<session>/subagents/agent-<id>.jsonl), digested apart."""
    out = []
    for log in sorted((Path(path).parent / Path(path).stem / "subagents").glob("agent-*.jsonl")):
        try:
            records = read_records(log)
        except NotASessionLog:
            continue
        meta = log.with_suffix(".meta.json")
        try:
            description = json.loads(meta.read_text()).get("description") if meta.is_file() else None
        except ValueError:
            description = None
        out.append({"id": log.stem.removeprefix("agent-"), "description": description,
                    "calls": len(calls(records)), "tokens": tokens(records)})
    return out


def _time(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(ts):
    return _time(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(path):
    records = read_records(path)
    session = next((r["sessionId"] for r in records if r.get("sessionId")), Path(path).stem)
    project = next((r["cwd"] for r in records if r.get("cwd")), None)
    stamps = sorted((r["timestamp"] for r in records if r.get("timestamp")), key=_time)
    call_list = calls(records)
    return {
        "session": session,
        "project": project,
        "start": _iso(stamps[0]) if stamps else None,
        "end": _iso(stamps[-1]) if stamps else None,
        "duration_s": int((_time(stamps[-1]) - _time(stamps[0])).total_seconds()) if stamps else 0,
        "calls": {"total": len(call_list), "by_tool": dict(sorted(Counter(c["tool"] for c in call_list).items()))},
        "failures": failures(call_list),
        "repeats": repeats(call_list),
        "search_streaks": search_streaks(call_list),
        "tokens": tokens(records),
        "cost_usd": cost_usd(records),
        "subagents": subagents(path),
    }


def _fail(errors):
    """Print the errors; true when there were any."""
    for e in errors:
        print(e, file=sys.stderr)
    return bool(errors)


def load_config(path):
    """out from config.yaml, ~ expanded, with one line per problem."""
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
        return None, [f"{path}: {problem}; see config.example.yaml"]
    return {"out": Path(cfg["out"]).expanduser()}, []


def session_file(out, d):
    """<out>/<local date of the session's start>/<session>.yaml."""
    day = _time(d["start"]).astimezone().strftime("%Y-%m-%d") if d["start"] else "undated"
    return out / day / f"{d['session']}.yaml"


def write_session(out, log):
    """Digest one log into its file; False when it is not a session log."""
    try:
        d = digest(log)
    except NotASessionLog:
        return False
    path = session_file(out, d)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=200))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parent.parent / "config.yaml",
                        help="config.yaml to read (default: the one beside SKILL.md)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="write the session file of each named log")
    e.add_argument("logs", nargs="*")
    args = parser.parse_args(argv)

    cfg, errors = load_config(args.config)
    if _fail(errors):
        return 1
    count = Counter(write_session(cfg["out"], Path(log)) for log in args.logs)
    print(f"{count[True]} written, 0 up to date, {count[False]} not session logs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
