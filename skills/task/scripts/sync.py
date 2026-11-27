"""sync.py - writes what a /task folder derives from the rest of it, from one load.

`sync(task)` writes the status of every requirement and item into acs.yaml, the generated blocks of
brief.md and, through flow's roadmap.py, the statuses of roadmap.yaml. It reads every file through the
task's model, writes a file only when its content changes, and puts the text it wrote back into the
model, so a Task built over the same model sees it without reading the file again.
Loaded by task.py by its file path as `task_sync` (see the skill's CLAUDE.md).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from lib import modules  # noqa: E402
from lib import yamledit as ye  # noqa: E402
from lib.yamlio import as_list  # noqa: E402

task_brief = modules.load(os.path.join(HERE, "brief.py"), "task_brief")
flow_roadmap = modules.load(os.path.join(HERE, "..", "..", "flow", "scripts", "roadmap.py"), "flow_roadmap")


def sync(task):
    """Write acs.yaml, brief.md and roadmap.yaml from `task` (a status.Task); the acs.yaml lines changed."""
    changed = sync_acs(task)
    sync_brief(task)
    sync_roadmap(task)
    return changed


def sync_acs(task):
    """Write each active requirement's and item's computed status into acs.yaml; returns the lines changed."""
    path = task.path("acs.yaml")
    lines = ye.split_lines(task.model.text(path))
    before = list(lines)
    for item in task.active_items():
        wanted = [(item.get("id"), task.item_status(item))]
        wanted += [(r.get("id"), task.req_status(r)) for r in as_list(item.get("requirements"))]
        for ident, state in wanted:
            blocks = ye.item_blocks(lines, "id", str(ident))
            if len(blocks) == 1:
                start, end, indent = blocks[0]
                ye.set_key(lines, start, end, indent, "status", state, after="text")
    if lines != before:
        ye.write_lines(path, lines, lambda d: isinstance(d, list))
        task.model.put(path, "".join(lines))
    return len(lines) - len(before) + sum(1 for a, b in zip(before, lines) if a != b)


def write_block(text, name, section, body):
    """text with block `name` holding body: rewritten between its markers, or inserted under its section heading.

    Every byte outside the markers stays as it was; the block takes the text's line endings. Text with neither
    the markers nor the heading, or with a start marker and no end marker, comes back unchanged (status.py
    reports it)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    block = nl.join([task_brief.block_start(name)] + body.split("\n") + [task_brief.BLOCK_END])
    if task_brief.unclosed_block(text, name):
        return text
    marked = task_brief.block_span(text, name)
    if marked:
        return text[:marked.start()] + block + text[marked.end():]
    heading = re.search(task_brief.heading_re(section) + r"[^\r\n]*(\r?\n)?", text, re.M)
    if not heading:
        return text
    lead = "" if heading.group(1) else nl
    return text[:heading.end()] + lead + nl + block + nl + text[heading.end():]


def sync_brief(task):
    """Rewrite each generated block of brief.md (brief.BLOCKS), or insert it under its heading; True when the file changed."""
    path = task.path("brief.md")
    if not os.path.isfile(path):
        return False
    text = task.model.raw(path)
    new = text
    for name, section, render in task_brief.BLOCKS:
        new = write_block(new, name, section, render(task))
    if new == text:
        return False
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    task.model.put(path, new)
    return True


def sync_roadmap(task):
    """Write the roadmap statuses through flow's roadmap.py, from the roadmap and features the load parsed."""
    specs = task.path(".specs")
    path = flow_roadmap.roadmap_path(specs)
    if not os.path.isfile(path):
        return
    data = task.model.load(path)
    if not isinstance(data, dict):
        flow_roadmap.sync_roadmap(specs)  # empty or not a mapping: flow stops with its own error, as before
        return
    written = flow_roadmap.sync_roadmap(specs, data, flow_roadmap.links_of(task.features), task.model.text(path))
    if written is not None:
        task.model.put(path, written)
