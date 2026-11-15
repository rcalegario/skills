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
