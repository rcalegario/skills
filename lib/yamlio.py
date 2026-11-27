"""Reading YAML files and the small values every writer stamps: today's date, the next id."""
import datetime
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - the scripts that import this say how to install it
    raise SystemExit("PyYAML is required: pip install pyyaml")


class YamlError(Exception):
    """A file that is not valid YAML; the message is `<path> is not valid YAML: <parser error>`."""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse(source, path):
    """The parsed document of `source` (text, or an open file) read from `path`; YamlError when it
    is not valid YAML. An open file makes the parser's error name the file; text names a string."""
    try:
        return yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise YamlError("%s is not valid YAML: %s" % (path, exc))


def load(path, default=None):
    """The parsed document of the file at `path`, or `default` when the file is missing or empty."""
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        data = parse(fh, path)
    return default if data is None else data


def load_mapping(path):
    """(text, data) of a YAML file whose top level is a mapping; exits 1 with an ERROR line otherwise."""
    text = read(path)
    try:
        data = parse(text, path)
    except YamlError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        sys.exit(1)
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %s must be a mapping at the top level\n" % path)
        sys.exit(1)
    return text, data


def as_list(value):
    """`value` when it is a list, else []: a single value or a mapping is never read as a list.
    A caller that must reject such a value checks it with `not_a_list`."""
    return value if isinstance(value, list) else []


def not_a_list(value):
    """True for a value that is set but is not a list (`T1`, `{a: 1}`); None and lists are fine."""
    return value is not None and not isinstance(value, list)


def list_errors(entry, fields, label):
    """'<label> <field> must be a list ([value])' for each field of `entry` holding a value that is
    neither a list nor null: a list field is never read from a single value."""
    return ["%s%s must be a list ([%s])" % (label, field, entry.get(field)) for field in fields
            if not_a_list(entry.get(field))]


FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)


def frontmatter(text):
    """The mapping in the `---` header at the top of a text, or {} when it has none."""
    m = FRONTMATTER_RE.match(text)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def today():
    return datetime.date.today().isoformat()


def next_id(ids, prefix, width=1):
    """The id after the highest `<prefix>-<n>` among `ids`, zero-padded to `width` digits.

    Ids with another prefix or a non-numeric suffix are ignored: next_id(["D-01", "D-07"], "D", 2) is "D-08"."""
    pattern = re.compile(r"^%s-(\d+)$" % re.escape(prefix))
    nums = [int(m.group(1)) for i in ids for m in [pattern.match(str(i))] if m]
    return "%s-%0*d" % (prefix, width, max(nums or [0]) + 1)
