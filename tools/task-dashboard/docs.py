"""docs.py - a task's Markdown files: the list the page shows, and one file's text.

Every .md under the task folder is listed, except the worktrees under repos/. A file is read only when its
path is in that list, so no name given from outside is ever joined into a path.
"""
import os
import re

import yaml

# A block between a first line "---" and the next "---" line. It is front matter only when it reads as a YAML
# mapping (or is empty), so a document that opens with a horizontal rule keeps its text.
FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(?:(.*?)\r?\n)?---[ \t]*(?:\r?\n|\Z)", re.S)
FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[ \t]*$", re.S | re.M)
HEADING = re.compile(r"^# +(.+?)\s*#*\s*$", re.M)


def without_front_matter(text):
    found = FRONT_MATTER.match(text)
    if not found:
        return text
    try:
        data = yaml.safe_load(found.group(1) or "")
    except yaml.YAMLError:
        return text
    return text[found.end():] if data is None or isinstance(data, dict) else text


def order(rel):
    """README first, then the brief, then the context files, then the rest by path."""
    rank = {"README.md": 0, "brief.md": 1}.get(rel, 2 if rel.startswith("context/") else 3)
    return rank, rel.lower()


def read(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:  # -sig drops a byte order mark
        return fh.read()


def title(path, rel):
    """The first "# " heading outside code blocks, else the file name."""
    found = HEADING.search(FENCE.sub("", without_front_matter(read(path))))
    return found.group(1) if found else rel.rsplit("/", 1)[-1]


def files(task_path):
    """Each .md file of the task as (path relative with "/", full path)."""
    top = os.path.normcase(os.path.abspath(task_path))
    out = []
    for root, dirs, names in os.walk(task_path):
        if os.path.normcase(os.path.abspath(root)) == top:
            dirs[:] = [d for d in dirs if d != "repos"]
        for name in names:
            if name.lower().endswith(".md"):
                full = os.path.join(root, name)
                out.append((os.path.relpath(full, task_path).replace(os.sep, "/"), full))
    return sorted(out, key=lambda pair: order(pair[0]))


def listing(task_path):
    """The task's docs as [{path, title, mtime}], in the order the page lists them."""
    return [{"path": rel, "title": title(full, rel), "mtime": os.path.getmtime(full)}
            for rel, full in files(task_path)]


def text(task_path, rel):
    """The text of the listed doc `rel` without its front matter; None when the list does not hold it."""
    full = dict(files(task_path)).get(rel)
    return without_front_matter(read(full)) if full else None
