"""Editing YAML files line by line, so comments, order and quoting outside the edit stay as written.

Two levels: `set_key` and its wrappers replace one scalar value inside a block; `put` replaces a top-level
key's whole value (a block or list included) with the lines `render` writes. Every write parses the result
and checks it with a `verify(data)` callback before touching the file."""
import json
import os
import re

from . import yamlio


class EditError(AssertionError):
    """The edited text parsed, but `verify` found the change missing: nothing was written."""


# ---------------------------------------------------------------- finding lines

def block_end(lines, start, indent):
    """First line after `start` that is not blank, not a comment and indented at most `indent`."""
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= indent:
            break
        end += 1
    return end


def item_blocks(lines, key, value):
    """(start, end, indent) of every list item that opens with `- key: value`."""
    pattern = re.compile(r"^(\s*)-\s+%s:\s*['\"]?%s['\"]?\s*(#.*)?$" % (re.escape(key), re.escape(value)))
    out = []
    for i, line in enumerate(lines):
        m = pattern.match(line.rstrip("\n"))
        if m:
            dash = len(m.group(1))
            out.append((i, block_end(lines, i, dash), dash + 2))
    return out


# ---------------------------------------------------------------- one scalar value

def set_key(lines, start, end, indent, key, value, after=None):
    """Replace `key:` inside lines[start:end] at the given indent, or insert it after `after:`.

    `value` is written as given (already a YAML scalar); a trailing comment on the old line is kept.
    Returns 1 when a line was inserted, 0 when one was replaced."""
    pattern = re.compile(r"^%s%s:(\s|$)" % (" " * indent, re.escape(key)))
    hits = [i for i in range(start, end) if pattern.match(lines[i])]
    assert len(hits) <= 1, "key %s appears %d times in the block" % (key, len(hits))
    new = "%s%s: %s\n" % (" " * indent, key, value)
    if hits:
        comment = re.search(r"\s+#.*$", lines[hits[0]].rstrip("\n"))
        if comment:
            new = new.rstrip("\n") + comment.group(0) + "\n"
        lines[hits[0]] = new
        return 0
    anchor = [i for i in range(start, end) if after and re.match(r"^%s%s:" % (" " * indent, after), lines[i])]
    pos = min(block_end(lines, anchor[0], indent), end) if anchor else end
    lines.insert(pos, new)
    return 1


def set_top(lines, key, value, after=None):
    set_key(lines, 0, len(lines), 0, key, value, after=after)


def set_child(lines, parent, key, value, after=None):
    """Set `parent.key`, turning `parent:` into a block when it is missing or inline."""
    hits = [i for i, l in enumerate(lines) if re.match(r"^%s:(\s|$)" % re.escape(parent), l)]
    if not hits:
        anchor = [i for i, l in enumerate(lines) if after and re.match(r"^%s:" % after, l)]
        pos = block_end(lines, anchor[0], 0) if anchor else len(lines)
        lines.insert(pos, "%s:\n" % parent)
        hits = [pos]
    start = hits[0]
    if re.sub(r"\s+#.*$", "", lines[start]).strip() != "%s:" % parent:
        lines[start] = "%s:\n" % parent
    set_key(lines, start + 1, block_end(lines, start, 0), 2, key, value)


# ---------------------------------------------------------------- whole values

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


class Quoted(str):
    """A string always written between quotes, so YAML never reads it back as a number (a hash of digits)."""


def render(key, value, indent=0):
    """Lines for `key: value`; a multi-line string becomes a literal block and a dict a nested map."""
    pad = " " * indent
    if isinstance(value, dict):
        return ["%s%s:\n" % (pad, key)] + [ln for k, v in value.items() for ln in render(k, v, indent + 2)]
    if isinstance(value, Quoted):
        return ["%s%s: %s\n" % (pad, key, json.dumps(str(value)))]
    if isinstance(value, str) and "\n" in value.strip("\n"):
        body = ["%s  %s\n" % (pad, ln) if ln else "\n" for ln in value.strip("\n").split("\n")]
        return ["%s%s: |\n" % (pad, key)] + body
    return ["%s%s: %s\n" % (pad, key, scalar(value))]


def put(lines, key, value, after=None):
    """Set a top-level key, replacing its whole value (a block included); insert after `after:` when new."""
    start = next((i for i, l in enumerate(lines) if re.match(r"^%s:(\s|$)" % re.escape(key), l)), None)
    new = render(key, value)
    if start is not None:
        end = block_end(lines, start, 0)
        while end < len(lines) and re.match(r"^-(\s|$)", lines[end]):  # an unindented list belongs to its key
            end = block_end(lines, end, 0)
        comment = re.search(r"\s+#.*$", lines[start].rstrip("\n"))
        if comment and len(new) == 1 and end == start + 1:
            new[0] = new[0].rstrip("\n") + comment.group(0) + "\n"
        lines[start:end] = new
        return
    anchor = next((i for i, l in enumerate(lines) if after and re.match(r"^%s:" % after, l)), None)
    pos = block_end(lines, anchor, 0) if anchor is not None else len(lines)
    lines[pos:pos] = new


def item_lines(fields):
    """The lines of one top-level list item from (key, value) pairs, the first opening with `- `."""
    lines = []
    for i, (key, value) in enumerate(fields):
        out = render(key, value, 2)
        out[0] = ("- " if i == 0 else "  ") + out[0][2:]
        lines += out
    return lines


# ---------------------------------------------------------------- files

def header_end(lines):
    """Index of the `---` line closing the header that opens `lines`; None without a header, -1 when unclosed."""
    if not lines or lines[0].strip() != "---":
        return None
    return next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), -1)


def split_lines(text):
    """The lines of a text, each ending with a newline."""
    lines = text.splitlines(True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return lines


def read_lines(path):
    return split_lines(yamlio.read(path))


def write_lines(path, lines, verify):
    """Write `lines` when their parsed form passes `verify`; EditError otherwise. Returns the parsed data."""
    text = "".join(lines)
    data = yamlio.parse(text, path)
    if not verify(data):
        raise EditError("the edit to %s did not apply" % path)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return data


def edit(path, text, change, verify):
    """Apply change(lines) to `text` (the file's content, or None to read it), verify, write; the parsed result."""
    lines = split_lines(yamlio.read(path) if text is None else text)
    change(lines)
    return write_lines(path, lines, verify)


def append_item(path, item_lines, items):
    """Append one item to a file holding a top-level YAML list of `items`, replacing an empty `[]`."""
    lines = read_lines(path) if os.path.isfile(path) else []
    lines = [l for l in lines if l.strip() != "[]"]
    if lines and lines[-1].strip():
        lines.append("\n")
    lines += item_lines
    write_lines(path, lines, lambda d: isinstance(d, list) and len(d) == len(items) + 1)
