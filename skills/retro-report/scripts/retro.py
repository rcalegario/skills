"""Retro helper for Claude Code sessions.

  retro.py digest <session.jsonl>   one session's calls, failures, repeats and cost, as YAML
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml


# Error classes read off a result's text, after tokeneconomizer's observe.py; first match wins.
ERROR_PATTERNS = [
    ("command_missing", re.compile(r"command not found|: not found\b|is not recognized", re.I)),
    ("module_missing", re.compile(r"ModuleNotFoundError|No module named|Cannot find module", re.I)),
    ("file_missing", re.compile(r"No such file or directory|File does not exist|ENOENT", re.I)),
    ("permission_denied", re.compile(r"Permission denied|EACCES|Operation not permitted", re.I)),
]
LINE_MAX = 200
INPUT_MAX = 120
STREAK_MIN = 3
SEARCH_TOOLS = {"Grep": "pattern", "Glob": "pattern", "Read": "file_path"}
SEARCH_HEADS = {"grep", "rg", "find", "ls", "cat", "head", "tail", "sed", "wc"}
# Words that neither search nor change anything: they keep a shell search a search.
NEUTRAL_HEADS = {"cd", "echo", "for", "do", "done", "if", "then", "else", "fi", "sort", "uniq", "xargs", "true"}
SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n")


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


def failures(cs):
    """Calls grouped by error class: a line matching a pattern, else `other` when the tool said is_error.

    Only shell output and results marked is_error are scanned: a Read of a file that quotes an error is no failure."""
    out = {}
    for c in cs:
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
    key = SEARCH_TOOLS.get(c["tool"])
    if key and key in c["input"]:
        return f"{c['tool']} {c['input'][key]}"
    return json.dumps(c["input"], sort_keys=True)


def repeats(cs):
    """Calls made more than once with identical input, in order of first use."""
    seen = Counter((c["tool"], json.dumps(c["input"], sort_keys=True)) for c in cs)
    shown = {(c["tool"], json.dumps(c["input"], sort_keys=True)): call_text(c) for c in cs}
    return [{"tool": key[0], "input": shown[key][:INPUT_MAX], "count": n} for key, n in seen.items() if n > 1]


def is_search(c):
    if c["tool"] in SEARCH_TOOLS:
        return True
    if c["tool"] != "Bash":
        return False
    heads = [seg.split()[0].lstrip("(") for seg in SEGMENT_SPLIT.split(call_text(c)) if seg.split()]
    return any(h in SEARCH_HEADS for h in heads) and all(h in SEARCH_HEADS | NEUTRAL_HEADS for h in heads)


def search_streaks(cs):
    """Runs of STREAK_MIN or more search calls in a row."""
    runs, run = [], []
    for c in cs + [None]:
        if c is not None and is_search(c):
            run.append(c)
            continue
        if len(run) >= STREAK_MIN:
            runs.append({"calls": [r["n"] for r in run], "commands": [call_text(r)[:INPUT_MAX] for r in run]})
        run = []
    return runs


TOKEN_FIELDS = {"input": "input_tokens", "output": "output_tokens",
                "cache_read": "cache_read_input_tokens", "cache_write": "cache_creation_input_tokens"}


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
    return round(float(totals[-1]), 4) if totals else None


def _time(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(ts):
    return _time(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(path):
    records = read_records(path)
    session = next((r["sessionId"] for r in records if r.get("sessionId")), Path(path).stem)
    project = next((r["cwd"] for r in records if r.get("cwd")), None)
    stamps = sorted((r["timestamp"] for r in records if r.get("timestamp")), key=_time)
    cs = calls(records)
    return {
        "session": session,
        "project": project,
        "start": _iso(stamps[0]) if stamps else None,
        "end": _iso(stamps[-1]) if stamps else None,
        "duration_s": int((_time(stamps[-1]) - _time(stamps[0])).total_seconds()) if stamps else 0,
        "calls": {"total": len(cs), "by_tool": dict(sorted(Counter(c["tool"] for c in cs).items()))},
        "failures": failures(cs),
        "repeats": repeats(cs),
        "search_streaks": search_streaks(cs),
        "tokens": tokens(records),
        "cost_usd": cost_usd(records),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digest", help="digest one Claude Code session log")
    d.add_argument("log")
    args = parser.parse_args(argv)

    if args.cmd == "digest":
        try:
            result = digest(args.log)
        except NotASessionLog:
            print(f"{args.log} is not a Claude Code session log", file=sys.stderr)
            return 1
        print(yaml.safe_dump(result, sort_keys=False, allow_unicode=True, width=200), end="")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
