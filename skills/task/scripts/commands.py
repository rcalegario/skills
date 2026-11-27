"""commands.py - the edits of each task.py command: journal, new, decide, supersede, validate, close, consolidate.

Each command edits only the lines it owns (comments and order stay), through the repo's lib/yamledit, and
returns the line task.py prints; a Refusal is printed as an ERROR. The sync and the check that follow every
command are task.py's. Loaded by task.py by its file path as `task_commands` (see the skill's CLAUDE.md).
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from lib import yamledit as ye  # noqa: E402
from lib import yamlio  # noqa: E402



class Refusal(Exception):
    pass


# ---------------------------------------------------------------- ids and files

def file_ids(root, sub, prefix):
    """The ids of the `<prefix>-<n>-<slug>.yaml` files in `sub/`."""
    return [m.group(1) for p in glob.glob(os.path.join(root, sub, "%s-*.yaml" % prefix))
            for m in [re.match(r"(%s-\d+)-" % prefix, os.path.basename(p))] if m]


def find_file(root, sub, ident):
    hits = glob.glob(os.path.join(root, sub, "%s-*.yaml" % ident))
    if not hits:
        raise Refusal("%s is not defined in %s/" % (ident, sub))
    return hits[0]


def split_refs(text):
    return [r.strip() for r in (text or "").split(",") if r.strip()]


# ---------------------------------------------------------------- commands

def cmd_journal(root, a):
    path = os.path.join(root, "journal.yaml")
    notes = yamlio.load(path, []) or []
    ident = yamlio.next_id([n.get("id") for n in notes if isinstance(n, dict)], "J", 3)
    ye.append_item(path, ye.item_lines([("id", ident), ("date", yamlio.today()), ("type", a.type),
                                  ("text", a.text), ("refs", split_refs(a.refs))]), notes)
    return "%s journal note" % ident


def cmd_new_pending(root, a):
    path = os.path.join(root, "pending.yaml")
    items = yamlio.load(path, []) or []
    ident = yamlio.next_id([i.get("id") for i in items if isinstance(i, dict)], "P")
    ye.append_item(path, ye.item_lines([("id", ident), ("with", split_refs(a.who)), ("action", a.action),
                                  ("refs", split_refs(a.refs)), ("status", "open")]), items)
    return "%s pending" % ident


def cmd_new_decision(root, a):
    ident = yamlio.next_id(file_ids(root, "decisions", "D"), "D", 2)
    path = os.path.join(root, "decisions", "%s-%s.yaml" % (ident, a.slug))
    fields = [("id", ident), ("title", a.title), ("status", "open"), ("date", yamlio.today()), ("context", []),
              ("born_from", split_refs(a.born_from)), ("discuss_with", split_refs(a.discuss_with)),
              ("question", a.question)]
    if a.requirement:
        link_requirement(root, a.requirement, ident)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(l for k, v in fields for l in ye.render(k, v)))
    return "%s %s" % (ident, os.path.relpath(path, root))


def link_requirement(root, req, decision):
    path = os.path.join(root, "acs.yaml")
    lines = ye.read_lines(path)
    blocks = ye.item_blocks(lines, "id", req)
    if len(blocks) != 1:
        raise Refusal("requirement %s is not defined in acs.yaml" % req)
    start, end, indent = blocks[0]
    ye.set_key(lines, start, end, indent, "decision", decision, after="text")
    ye.write_lines(path, lines, lambda d: True)


def cmd_new_validation(root, a):
    ident = yamlio.next_id(file_ids(root, "validations", "V"), "V", 2)
    path = os.path.join(root, "validations", "%s-%s.yaml" % (ident, a.slug))
    fields = [("id", ident), ("title", a.title), ("status", "pending"), ("date", None), ("where", a.where),
              ("depends_on", []), ("how", a.how), ("expected", a.expected), ("evidence", ""), ("attachments", [])]
    if a.decides:
        fields.insert(6, ("decides", split_refs(a.decides)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(l for k, v in fields for l in ye.render(k, v)))
    return "%s %s%s" % (ident, os.path.relpath(path, root), " (spike)" if a.decides else "")


def cmd_decide(root, a):
    path = find_file(root, "decisions", a.id)
    state = "proposed" if a.proposed else "decided"
    current = yamlio.load(path, {}).get("status")
    if current in ("decided", "superseded", "dropped"):
        raise Refusal("%s is %s; to change course write a new decision and `supersede` it" % (a.id, current))
    if state == "decided" and not a.why:
        raise Refusal("a decided decision needs --why (use --proposed to recommend without deciding)")

    def change(lines):
        ye.put(lines, "status", state)
        ye.put(lines, "date", yamlio.today(), after="status")
        ye.put(lines, "decision", a.decision, after="question")
        if a.why:
            ye.put(lines, "why", a.why, after="decision")
        if a.pr_note:
            ye.put(lines, "pr_note", a.pr_note)

    ye.edit(path, None, change, lambda d: d.get("status") == state)
    return "%s %s" % (a.id, state)


def cmd_supersede(root, a):
    old, new = find_file(root, "decisions", a.old), find_file(root, "decisions", a.new)

    def old_change(lines):
        ye.put(lines, "status", "superseded")
        ye.put(lines, "date", yamlio.today(), after="status")
        ye.put(lines, "superseded_by", a.new, after="born_from")

    if not yamlio.load(old, {}).get("decision"):
        raise Refusal("%s has no decision to supersede; drop it instead" % a.old)
    ye.edit(old, None, old_change, lambda d: d.get("superseded_by") == a.new)
    ye.edit(new, None, lambda lines: ye.put(lines, "supersedes", a.old, after="born_from"), lambda d: d.get("supersedes") == a.old)
    return "%s superseded by %s" % (a.old, a.new)


def cmd_validate(root, a):
    path = find_file(root, "validations", a.id)
    if yamlio.load(path, {}).get("status") == "dropped":
        raise Refusal("%s is dropped: what it proved left the task" % a.id)
    if a.status in ("passed", "failed") and not (a.evidence or yamlio.load(path, {}).get("evidence", "").strip()):
        raise Refusal("%s needs --evidence: date, environment and output of the run" % a.status)

    def change(lines):
        ye.put(lines, "status", a.status)
        ye.put(lines, "date", yamlio.today(), after="status")
        if a.evidence:
            ye.put(lines, "evidence", a.evidence)
        if a.attach:
            ye.put(lines, "attachments", list(a.attach))

    ye.edit(path, None, change, lambda d: d.get("status") == a.status)
    return "%s %s" % (a.id, a.status)


def cmd_close(root, a):
    path = os.path.join(root, "pending.yaml")
    lines = ye.read_lines(path)
    blocks = ye.item_blocks(lines, "id", a.id)
    if len(blocks) != 1:
        raise Refusal("%s is not defined in pending.yaml" % a.id)
    start, end, indent = blocks[0]
    current = next(i for i in yamlio.parse("".join(lines), path) if i.get("id") == a.id).get("status")
    if current in ("done", "dropped"):
        raise Refusal("%s is already %s" % (a.id, current))
    ye.set_key(lines, start, end, indent, "status", a.status)
    end = ye.block_end(lines, start, indent - 2)
    ye.set_key(lines, start, end, indent, "closed", yamlio.today(), after="status")
    if a.link:
        end = ye.block_end(lines, start, indent - 2)
        ye.set_key(lines, start, end, indent, "link", ye.scalar(a.link), after="closed")
    ye.write_lines(path, lines, lambda d: any(i.get("id") == a.id and i.get("status") == a.status for i in d))
    return "%s %s" % (a.id, a.status)


def cmd_consolidate(root, a, sources_digest):
    """Stamp brief.md's date and the digest of its sources; `sources_digest(root)` is status.py's."""
    path = os.path.join(root, "brief.md")
    if not os.path.isfile(path):
        raise Refusal("brief.md does not exist yet: write it from templates/brief.md first")
    lines = ye.read_lines(path)
    close = ye.header_end(lines)
    if close is None:
        raise Refusal("brief.md has no YAML header")
    if close == -1:
        raise Refusal("brief.md header is not closed")
    head = lines[1:close]
    ye.put(head, "date", yamlio.today())
    ye.put(head, "sources", {g: ye.Quoted(h) for g, h in sources_digest(root).items()}, after="date")
    lines[1:close] = head
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("".join(lines))
    return "brief.md date %s, sources stamped" % yamlio.today()
