#!/usr/bin/env python3
"""task.py - writes the YAML files of a /task folder, so no id, date or status is typed by hand.

Usage:
    python task.py [task-dir] journal --type T --text TEXT [--refs D-01,V-02]
    python task.py [task-dir] new decision SLUG --title T --question Q [--born-from D-01] [--requirement AC-1.1] [--discuss-with me]
    python task.py [task-dir] new validation SLUG --title T --how H --expected E [--where W] [--decides D-01]
    python task.py [task-dir] new pending --with WHO --action A [--refs D-01]
    python task.py [task-dir] decide D-nn --decision TEXT --why TEXT [--proposed] [--pr-note TEXT]
    python task.py [task-dir] supersede D-old D-new
    python task.py [task-dir] validate V-nn --status passed|failed|dropped [--evidence TEXT] [--attach FILE]
    python task.py [task-dir] close P-n [--status done|dropped] [--link URL]
    python task.py [task-dir] consolidate
    python task.py [task-dir] sync

`sync` writes the status of every requirement and item (acs.yaml) and of every roadmap feature and milestone
(.specs/roadmap.yaml) from the rest of the folder; every other command does it after its own edit. These
statuses are never typed by hand.

Each command edits only the lines it owns (comments and order stay), then runs the status.py checks and
exits 1 when the folder has failures. The folder layout is in ../reference/format.md.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "flow", "scripts"))

import flow  # noqa: E402  (line-editing helpers shared with /flow)
import status  # noqa: E402

yaml = status.yaml


def today():
    return datetime.date.today().isoformat()


class Refusal(Exception):
    pass


# ---------------------------------------------------------------- rendering

def scalar(value):
    """One YAML line for a value: flow list, number, or a double-quoted string."""
    if isinstance(value, list):
        return "[%s]" % ", ".join(scalar(v) for v in value)
    if value is None:
        return "null"
    if isinstance(value, (bool, int)):
        return json.dumps(value)
    text = str(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text  # a YAML date, as every template writes it
    if re.match(r"^[A-Za-z0-9_./-]+$", text) and not re.match(r"^(null|true|false|yes|no|~|[0-9.-]+)$", text, re.I):
        return text
    return json.dumps(text, ensure_ascii=False)


def render(key, value, indent=0):
    """Lines for `key: value`; a multi-line string becomes a literal block."""
    pad = " " * indent
    if isinstance(value, str) and "\n" in value.strip("\n"):
        body = ["%s  %s\n" % (pad, ln) if ln else "\n" for ln in value.strip("\n").split("\n")]
        return ["%s%s: |\n" % (pad, key)] + body
    return ["%s%s: %s\n" % (pad, key, scalar(value))]


def put(lines, key, value, after=None):
    """Set a top-level key, replacing its whole value (a block included); insert after `after:` when new."""
    start = next((i for i, l in enumerate(lines) if re.match(r"^%s:(\s|$)" % re.escape(key), l)), None)
    new = render(key, value)
    if start is not None:
        end = flow.block_end(lines, start, 0)
        while end < len(lines) and re.match(r"^-(\s|$)", lines[end]):  # an unindented list belongs to its key
            end = flow.block_end(lines, end, 0)
        comment = re.search(r"\s+#.*$", lines[start].rstrip("\n"))
        if comment and len(new) == 1 and end == start + 1:
            new[0] = new[0].rstrip("\n") + comment.group(0) + "\n"
        lines[start:end] = new
        return
    anchor = next((i for i, l in enumerate(lines) if after and re.match(r"^%s:" % after, l)), None)
    pos = flow.block_end(lines, anchor, 0) if anchor is not None else len(lines)
    lines[pos:pos] = new


def read_lines(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines(True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return lines


def write_lines(path, lines, verify):
    text = "".join(lines)
    if not verify(yaml.safe_load(text)):
        raise Refusal("the edit to %s did not apply" % path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


# ---------------------------------------------------------------- ids and files

def next_number(root, sub, prefix, width):
    nums = [int(m.group(1)) for p in glob.glob(os.path.join(root, sub, "%s-*.yaml" % prefix))
            for m in [re.match(r"%s-(\d+)-" % prefix, os.path.basename(p))] if m]
    return "%s-%0*d" % (prefix, width, max(nums or [0]) + 1)


def find_file(root, sub, ident):
    hits = glob.glob(os.path.join(root, sub, "%s-*.yaml" % ident))
    if not hits:
        raise Refusal("%s is not defined in %s/" % (ident, sub))
    return hits[0]


def append_item(path, item_lines, items):
    """Append a list item to journal.yaml / pending.yaml, replacing an empty `[]`."""
    lines = read_lines(path) if os.path.isfile(path) else []
    lines = [l for l in lines if l.strip() != "[]"]
    if lines and lines[-1].strip():
        lines.append("\n")
    lines += item_lines
    write_lines(path, lines, lambda d: isinstance(d, list) and len(d) == len(items) + 1)


def item_lines(fields):
    lines = []
    for i, (key, value) in enumerate(fields):
        out = render(key, value, 2)
        out[0] = ("- " if i == 0 else "  ") + out[0][2:]
        lines += out
    return lines


def split_refs(text):
    return [r.strip() for r in (text or "").split(",") if r.strip()]


# ---------------------------------------------------------------- commands

def cmd_journal(root, a):
    path = os.path.join(root, "journal.yaml")
    notes = status.load_yaml(path, []) or []
    nums = [int(n["id"][2:]) for n in notes if isinstance(n, dict) and re.match(r"^J-\d+$", str(n.get("id")))]
    ident = "J-%03d" % (max(nums or [0]) + 1)
    append_item(path, item_lines([("id", ident), ("date", today()), ("type", a.type),
                                  ("text", a.text), ("refs", split_refs(a.refs))]), notes)
    return "%s journal note" % ident


def mutate(path, change, verify):
    lines = read_lines(path)
    change(lines)
    write_lines(path, lines, verify)


def doc(path):
    return yaml.safe_load(open(path, encoding="utf-8")) or {}


def cmd_new_pending(root, a):
    path = os.path.join(root, "pending.yaml")
    items = status.load_yaml(path, []) or []
    nums = [int(i["id"][2:]) for i in items if isinstance(i, dict) and re.match(r"^P-\d+$", str(i.get("id")))]
    ident = "P-%d" % (max(nums or [0]) + 1)
    append_item(path, item_lines([("id", ident), ("with", split_refs(a.who)), ("action", a.action),
                                  ("refs", split_refs(a.refs)), ("status", "open")]), items)
    return "%s pending" % ident


def cmd_new_decision(root, a):
    ident = next_number(root, "decisions", "D", 2)
    path = os.path.join(root, "decisions", "%s-%s.yaml" % (ident, a.slug))
    fields = [("id", ident), ("title", a.title), ("status", "open"), ("date", today()), ("context", []),
              ("born_from", split_refs(a.born_from)), ("discuss_with", split_refs(a.discuss_with)),
              ("question", a.question)]
    if a.requirement:
        link_requirement(root, a.requirement, ident)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(l for k, v in fields for l in render(k, v)))
    return "%s %s" % (ident, os.path.relpath(path, root))


def link_requirement(root, req, decision):
    path = os.path.join(root, "acs.yaml")
    lines = read_lines(path)
    blocks = flow.item_blocks(lines, "id", req)
    if len(blocks) != 1:
        raise Refusal("requirement %s is not defined in acs.yaml" % req)
    start, end, indent = blocks[0]
    flow.set_key(lines, start, end, indent, "decision", decision, after="text")
    write_lines(path, lines, lambda d: True)


def cmd_new_validation(root, a):
    ident = next_number(root, "validations", "V", 2)
    path = os.path.join(root, "validations", "%s-%s.yaml" % (ident, a.slug))
    fields = [("id", ident), ("title", a.title), ("status", "pending"), ("date", None), ("where", a.where),
              ("depends_on", []), ("how", a.how), ("expected", a.expected), ("evidence", ""), ("attachments", [])]
    if a.decides:
        fields.insert(6, ("decides", split_refs(a.decides)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(l for k, v in fields for l in render(k, v)))
    return "%s %s%s" % (ident, os.path.relpath(path, root), " (spike)" if a.decides else "")


def cmd_decide(root, a):
    path = find_file(root, "decisions", a.id)
    state = "proposed" if a.proposed else "decided"
    current = doc(path).get("status")
    if current in ("decided", "superseded", "dropped"):
        raise Refusal("%s is %s; to change course write a new decision and `supersede` it" % (a.id, current))
    if state == "decided" and not a.why:
        raise Refusal("a decided decision needs --why (use --proposed to recommend without deciding)")

    def change(lines):
        put(lines, "status", state)
        put(lines, "date", today(), after="status")
        put(lines, "decision", a.decision, after="question")
        if a.why:
            put(lines, "why", a.why, after="decision")
        if a.pr_note:
            put(lines, "pr_note", a.pr_note)

    mutate(path, change, lambda d: d.get("status") == state)
    return "%s %s" % (a.id, state)


def cmd_supersede(root, a):
    old, new = find_file(root, "decisions", a.old), find_file(root, "decisions", a.new)

    def old_change(lines):
        put(lines, "status", "superseded")
        put(lines, "date", today(), after="status")
        put(lines, "superseded_by", a.new, after="born_from")

    if not doc(old).get("decision"):
        raise Refusal("%s has no decision to supersede; drop it instead" % a.old)
    mutate(old, old_change, lambda d: d.get("superseded_by") == a.new)
    mutate(new, lambda lines: put(lines, "supersedes", a.old, after="born_from"), lambda d: d.get("supersedes") == a.old)
    return "%s superseded by %s" % (a.old, a.new)


def cmd_validate(root, a):
    path = find_file(root, "validations", a.id)
    if doc(path).get("status") == "dropped":
        raise Refusal("%s is dropped: what it proved left the task" % a.id)
    if a.status in ("passed", "failed") and not (a.evidence or doc(path).get("evidence", "").strip()):
        raise Refusal("%s needs --evidence: date, environment and output of the run" % a.status)

    def change(lines):
        put(lines, "status", a.status)
        put(lines, "date", today(), after="status")
        if a.evidence:
            put(lines, "evidence", a.evidence)
        if a.attach:
            put(lines, "attachments", list(a.attach))

    mutate(path, change, lambda d: d.get("status") == a.status)
    return "%s %s" % (a.id, a.status)


def cmd_close(root, a):
    path = os.path.join(root, "pending.yaml")
    lines = read_lines(path)
    blocks = flow.item_blocks(lines, "id", a.id)
    if len(blocks) != 1:
        raise Refusal("%s is not defined in pending.yaml" % a.id)
    start, end, indent = blocks[0]
    current = next(i for i in yaml.safe_load("".join(lines)) if i.get("id") == a.id).get("status")
    if current in ("done", "dropped"):
        raise Refusal("%s is already %s" % (a.id, current))
    flow.set_key(lines, start, end, indent, "status", a.status)
    end = flow.block_end(lines, start, indent - 2)
    flow.set_key(lines, start, end, indent, "closed", today(), after="status")
    if a.link:
        end = flow.block_end(lines, start, indent - 2)
        flow.set_key(lines, start, end, indent, "link", scalar(a.link), after="closed")
    write_lines(path, lines, lambda d: any(i.get("id") == a.id and i.get("status") == a.status for i in d))
    return "%s %s" % (a.id, a.status)


def sync_acs(root, check):
    """Write each active requirement's and item's computed status into acs.yaml; returns the lines changed."""
    path = os.path.join(root, "acs.yaml")
    lines = read_lines(path)
    before = list(lines)
    for item in check.active_items():
        wanted = [(item.get("id"), check.item_status(item))]
        wanted += [(r.get("id"), check.req_status(r)) for r in status.lst(item.get("requirements"))]
        for ident, state in wanted:
            blocks = flow.item_blocks(lines, "id", str(ident))
            if len(blocks) == 1:
                start, end, indent = blocks[0]
                flow.set_key(lines, start, end, indent, "status", state, after="text")
    if lines != before:
        write_lines(path, lines, lambda d: isinstance(d, list))
    return len(lines) - len(before) + sum(1 for a, b in zip(before, lines) if a != b)


def sync_all(root):
    check = status.Task(root)
    check.check()
    changed = sync_acs(root, check)
    flow.sync_roadmap(os.path.join(root, ".specs"))
    return changed


def cmd_sync(root, a):
    return "sync: %d acs.yaml line(s) changed" % sync_all(root)


def cmd_consolidate(root, a):
    path = os.path.join(root, "brief.md")
    if not os.path.isfile(path):
        raise Refusal("brief.md does not exist yet: write it from templates/brief.md first")
    lines = read_lines(path)
    if not lines or lines[0].strip() != "---":
        raise Refusal("brief.md has no YAML header")
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        raise Refusal("brief.md header is not closed")
    head = lines[1:close]
    put(head, "date", today())
    lines[1:close] = head
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(lines))
    return "brief.md date %s" % today()


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="?", default=".")
    sub = ap.add_subparsers(dest="command")
    sub.required = True

    def add(name, parent=sub, **kw):
        return parent.add_parser(name, **kw)

    j = add("journal")
    j.add_argument("--type", required=True)
    j.add_argument("--text", required=True)
    j.add_argument("--refs")

    new = add("new").add_subparsers(dest="kind")
    new.required = True
    d = add("decision", new)
    d.add_argument("slug")
    d.add_argument("--title", required=True)
    d.add_argument("--question", required=True)
    d.add_argument("--born-from")
    d.add_argument("--requirement", help="AC-n.m whose root decision this becomes")
    d.add_argument("--discuss-with")
    v = add("validation", new)
    v.add_argument("slug")
    v.add_argument("--title", required=True)
    v.add_argument("--how", required=True)
    v.add_argument("--expected", required=True)
    v.add_argument("--where", default="clone")
    v.add_argument("--decides", help="makes it a spike that settles these decisions")
    p = add("pending", new)
    p.add_argument("--with", dest="who", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--refs")

    de = add("decide")
    de.add_argument("id")
    de.add_argument("--decision", required=True)
    de.add_argument("--why")
    de.add_argument("--proposed", action="store_true")
    de.add_argument("--pr-note")
    su = add("supersede")
    su.add_argument("old")
    su.add_argument("new")
    va = add("validate")
    va.add_argument("id")
    va.add_argument("--status", required=True, choices=("passed", "failed", "dropped"))
    va.add_argument("--evidence")
    va.add_argument("--attach", action="append", help="file name under validations/evidence/")
    cl = add("close")
    cl.add_argument("id")
    cl.add_argument("--status", default="done", choices=("done", "dropped"))
    cl.add_argument("--link")
    add("consolidate")
    add("sync")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.task)
    if not os.path.isfile(os.path.join(root, "acs.yaml")):
        print("ERROR: %s has no acs.yaml; not a task folder" % root)
        return 2
    handler = {"journal": cmd_journal, "decide": cmd_decide, "supersede": cmd_supersede,
               "validate": cmd_validate, "close": cmd_close, "consolidate": cmd_consolidate,
               "sync": cmd_sync,
               "new": lambda r, a: {"decision": cmd_new_decision, "validation": cmd_new_validation,
                                    "pending": cmd_new_pending}[a.kind](r, a)}[args.command]
    try:
        print(handler(root, args))
    except Refusal as exc:
        print("ERROR: %s" % exc)
        return 1
    if args.command != "sync":
        sync_all(root)
    check = status.Task(root)
    check.check()
    for failure in check.failures:
        print("FAIL: %s" % failure)
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
