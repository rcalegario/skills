"""brief.py - what brief.md summarises and the blocks a script writes into it.

The sources digest (one hash per group of sources, format.md, Files, brief.md) and the generated blocks:
how a block is found (status.py reads it, task.py writes it) and what each one holds. Loaded by status.py
by its file path as `task_brief`; status.py keeps these names for task.py and the tests.
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))

from lib import modules  # noqa: E402
from lib import yamlio  # noqa: E402
from lib.yamlio import as_list  # noqa: E402

task_model = modules.load(os.path.join(os.path.dirname(os.path.realpath(__file__)), "model.py"), "task_model")


# ------------------------------------------------------------ sources digest

SOURCE_GROUPS = ("context", "acs", "decisions")
DIGEST_LENGTH = 12


def _short_hash(data):
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def _context_text(model, path):
    """A context file with LF endings and without the read_on line a script stamps in its header."""
    text = model.text(path)
    m = yamlio.FRONTMATTER_RE.match(text)
    if not m:
        return text
    # group(1) is the header without its `---` lines and its last newline: both are written back as they were
    head = re.sub(r"^read_on:.*\n", "", m.group(1) + "\n", flags=re.M)
    return "---\n" + head + "---\n" + text[m.end():]


def _acs_fields(model):
    """What a person writes in acs.yaml: the texts and links, and an item dropped by hand, never a derived status."""
    items = []
    for item in model.load(model.path("acs.yaml"), []) or []:
        if not isinstance(item, dict):
            continue
        reqs = [{k: req.get(k) for k in ("id", "text", "decision", "validations")}
                for req in as_list(item.get("requirements")) if isinstance(req, dict)]
        items.append({"id": item.get("id"), "text": item.get("text"),
                      "dropped": item.get("status") == "dropped", "requirements": reqs})
    return items


def _decision_fields(model):
    """What a person writes in a decision, never the date a script stamps."""
    found = []
    for path in model.glob("decisions", "D-*.yaml"):
        dec = model.load(path, {})
        if not isinstance(dec, dict):
            continue
        fields = {k: dec.get(k) for k in ("id", "title", "status", "question", "decision", "why", "consequences")}
        fields["options"] = [{"name": o.get("name"), "status": o.get("status")}
                             for o in as_list(dec.get("options")) if isinstance(o, dict)]
        found.append(fields)
    return found


def sources_digest(source):
    """One short hash per group of sources a brief summarises (format.md, Files, brief.md): context, acs, decisions.

    `source` is the task folder, or the task_model.Model already loaded from it."""
    model = source if isinstance(source, task_model.Model) else task_model.Model(source)
    context = {os.path.basename(p): _context_text(model, p) for p in model.glob("context", "*.md")}
    return {"context": _short_hash(context),
            "acs": _short_hash(_acs_fields(model)),
            "decisions": _short_hash(_decision_fields(model))}


# ------------------------------------------------------------ generated blocks of the brief

OPEN_ITEMS = "open-items"
NOTHING_OPEN = "None: no decision is open or proposed and no pending item is open."
REQUIREMENTS = "requirements"
NO_REQUIREMENTS = "None: acs.yaml has no requirements."
BLOCK_END = "<!-- /task:generated -->"


BLOCK_START_PREFIX = "<!-- task:generated "


def block_start(name):
    return "%s%s -->" % (BLOCK_START_PREFIX, name)


def block_span(text, name):
    """The match of block `name` in a brief, from its start marker to the end marker; None when missing.

    The one rule both status.py (reading) and task.py (writing) use to find a block. A block never runs past
    the start marker of another one, so a block that lost its end marker is missing, not one that swallows
    the text up to the next block's end."""
    return re.search(r"%s((?:(?!%s).)*?)%s" % (re.escape(block_start(name)), re.escape(BLOCK_START_PREFIX),
                                                re.escape(BLOCK_END)), text, re.S)


def unclosed_block(text, name):
    """True when the start marker of block `name` is in text with no end marker of its own."""
    return block_start(name) in text and not block_span(text, name)


def generated_block(text, name):
    """What a brief holds between the markers of block `name`, with LF endings; None when the markers are missing."""
    m = block_span(text, name)
    if not m:
        return None
    return m.group(1).replace("\r\n", "\n").strip("\n")


def open_items_block(task):
    """The lines between the open-items markers: the agenda of task, grouped by person in sorted order."""
    agenda = task.agenda_lines()
    if not agenda:
        return NOTHING_OPEN
    return "\n\n".join("**%s**\n%s" % (who, "\n".join("- %s" % line for line in agenda[who]))
                       for who in sorted(agenda))


def one_line(text):
    """text with every run of whitespace, newlines included, made one space: one list line per item."""
    return " ".join(str(text or "").split())


def requirements_block(task):
    """The lines between the requirements markers: each item not dropped, then its requirements not dropped,
    each with its active root decision."""
    lines = []
    for item in task.items:
        if not isinstance(item, dict) or item.get("status") == "dropped":
            continue
        lines.append("- **%s** %s" % (item.get("id"), one_line(item.get("text"))))
        for req in as_list(item.get("requirements")):
            if isinstance(req, dict) and req.get("status") != "dropped":
                lines.append("  - %s (%s) %s" % (req.get("id"), task.active_root(req.get("decision")),
                                                 one_line(req.get("text"))))
    return "\n".join(lines) or NO_REQUIREMENTS


# Each generated block of the brief: its name, the BRIEF section heading that holds it, and what it holds.
BLOCKS = [(REQUIREMENTS, "BRIEF-2", requirements_block),
          (OPEN_ITEMS, "BRIEF-4", open_items_block)]


def heading_re(section):
    return r"^## %s\b" % re.escape(section)
