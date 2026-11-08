#!/usr/bin/env python3
"""
index.py - generated indexes so agents read one short table instead of opening
every ADR or feature folder.

Subcommands:
  adr       docs/adr/AGENTS.md          from docs/adr/AD-*.md
  features  .specs/features/AGENTS.md   from .specs/features/m<N>.f<N>.<slug>/ (legacy names are listed too)

Each index is GENERATED and never hand-edited. A one-line CLAUDE.md that imports
it (`@AGENTS.md`) is created next to it once and never overwritten. Pure
standard library; operates only on markdown artifacts.

Usage:
  python3 <skill-dir>/scripts/index.py adr      [--root DIR] [--check]
  python3 <skill-dir>/scripts/index.py features [--root DIR] [--check]

  --root   Project root (default: current dir).
  --check  Do not write. Exit 1 if the AGENTS.md on disk differs from the
           generated one (or is missing while there are items).

Exit codes: 0 ok / up to date, 1 stale index or malformed ADR, 2 usage error.
A missing or empty target folder creates nothing and exits 0.
"""

import argparse
import os
import re

SUMMARY_MAX = 160
NOT_FILLED = "(spec not filled)"
FEATURE_CODE_RE = re.compile(r"^m(\d+)\.f(\d+)\.")
LEGACY_CODE_RE = re.compile(r"^m(\d+)(?:\.(\d+))?-")
VERDICT_RE = re.compile(r"^\**verdict\**\s*:\s*\**\s*(PASS|FAIL)\b", re.IGNORECASE)
ADR_FILE_RE = re.compile(r"^AD-(\d+)-.+\.md$")
STATUS_RE = re.compile(r"^(active|superseded by AD-\d+)$")


def _field(text, name):
    m = re.search(r"^\s*-\s*\*\*" + re.escape(name) + r"\*\*\s*:\s*(.+?)\s*$", text, re.MULTILINE)
    return m.group(1) if m else None


def _write_or_check(folder, content, check):
    """Write AGENTS.md (+ CLAUDE.md once) under folder, or compare in --check mode."""
    agents = os.path.join(folder, "AGENTS.md")
    if check:
        current = None
        if os.path.exists(agents):
            with open(agents, encoding="utf-8") as f:
                current = f.read()
        if current != content:
            print(f"index: {agents} is stale - run index.py to regenerate")
            return 1
        return 0
    with open(agents, "w", encoding="utf-8") as f:
        f.write(content)
    claude = os.path.join(folder, "CLAUDE.md")
    if not os.path.exists(claude):
        with open(claude, "w", encoding="utf-8") as f:
            f.write("@AGENTS.md\n")
    print(f"index: wrote {agents}")
    return 0


def build_adr(folder):
    """Return (content, errors) for the ADR index of folder."""
    active, superseded, errors = [], [], []
    for name in sorted(os.listdir(folder)):
        m = ADR_FILE_RE.match(name)
        if not m:
            continue
        with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
            text = f.read()
        decision, scope, status = _field(text, "Decision"), _field(text, "Scope"), _field(text, "Status")
        if not decision:
            errors.append(f"{name}: missing **Decision** field")
            continue
        if not status or not STATUS_RE.match(status):
            errors.append(f"{name}: **Status** must be 'active' or 'superseded by AD-NNN' (got {status!r})")
            continue
        num = int(m.group(1))
        ident = f"AD-{num:03d}"
        if status == "active":
            active.append((num, ident, name, scope or "", decision))
        else:
            superseded.append((num, ident, status.rsplit(" ", 1)[1]))
    if errors:
        return None, errors
    if not active and not superseded:
        return None, []
    lines = [
        "# ADR index (generated - do not edit; run scripts/index.py adr)",
        "",
        "Read this table first. Open a full ADR only when its Scope touches your work.",
        "",
        "## Active",
        "",
        "| ID | Scope | Decision |",
        "| --- | --- | --- |",
    ]
    for _, ident, name, scope, decision in sorted(active):
        lines.append(f"| [{ident}]({name}) | {scope} | {decision} |")
    if superseded:
        lines += ["", "## Superseded", ""]
        for _, ident, by in sorted(superseded):
            lines.append(f"- {ident} → {by}")
    return "\n".join(lines) + "\n", []


def cmd_adr(root, check):
    folder = os.path.join(root, "docs", "adr")
    if not os.path.isdir(folder):
        return 0
    content, errors = build_adr(folder)
    for e in errors:
        print(f"  ERROR {e}")
    if errors:
        return 1
    if content is None:
        return 0
    return _write_or_check(folder, content, check)


def _summary(spec_path):
    """First sentence of the Problem Statement, or NOT_FILLED."""
    if not os.path.isfile(spec_path):
        return NOT_FILLED
    with open(spec_path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    para, inside = [], False
    for ln in lines:
        if re.match(r"^#{1,3}\s+Problem Statement\s*$", ln.strip()):
            inside = True
            continue
        if inside:
            if re.match(r"^#{1,3}\s+\S", ln):
                break
            if ln.strip():
                para.append(ln.strip())
            elif para:
                break
    text = " ".join(para)
    if not text or re.match(r"^\[.*\]$", text):
        return NOT_FILLED
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) > SUMMARY_MAX:
        first = first[: SUMMARY_MAX - 3].rstrip() + "..."
    return first.replace("|", "\\|")


def _verdict(path):
    """'pass' or 'fail' from the report's `**Verdict**:` line; None if absent or still a placeholder."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = VERDICT_RE.match(ln.strip())
            if m:
                return m.group(1).lower()
    return None


def _state(fdir):
    vpath = os.path.join(fdir, "verification.md")
    if os.path.isfile(vpath):
        verdict = _verdict(vpath)
        if verdict == "pass":
            return "done"
        if verdict == "fail":
            return "failing"
    # tasks.md or a report without a filled verdict: still open.
    if os.path.isfile(vpath) or os.path.isfile(os.path.join(fdir, "tasks.md")):
        return "in progress"
    return "specified"


def _feature_order(name):
    """Milestone number first. Inside a milestone: legacy folders, then m<N>.f<N> features by number.
    Folders with no milestone code go last."""
    m = FEATURE_CODE_RE.match(name)
    if m:
        return (0, int(m.group(1)), 1, int(m.group(2)), name)
    m = LEGACY_CODE_RE.match(name)
    if m:
        return (0, int(m.group(1)), 0, int(m.group(2)) if m.group(2) else -1, name)
    return (1, 0, 0, 0, name)


def cmd_features(root, check):
    folder = os.path.join(root, ".specs", "features")
    if not os.path.isdir(folder):
        return 0
    names = sorted(
        (d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))),
        key=_feature_order,
    )
    if not names:
        return 0
    lines = [
        "# Feature index (generated - do not edit; run scripts/index.py features)",
        "",
        "Read this table before specifying a new feature or resuming work. Open a feature folder only when its row is relevant.",
        "",
        "| Feature | Status | Summary |",
        "| --- | --- | --- |",
    ]
    for name in names:
        fdir = os.path.join(folder, name)
        lines.append(f"| [{name}]({name}/) | {_state(fdir)} | {_summary(os.path.join(fdir, 'spec.md'))} |")
    return _write_or_check(folder, "\n".join(lines) + "\n", check)


def main(argv=None):
    p = argparse.ArgumentParser(prog="index.py", description="Generate the ADR and feature indexes.")
    p.add_argument("kind", choices=["adr", "features"])
    p.add_argument("--root", default=".")
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.kind == "adr":
        return cmd_adr(root, args.check)
    return cmd_features(root, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
