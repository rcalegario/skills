"""model.py - the files of a /task folder, each read from disk at most once per load.

A Model is the one place status.py reads a task file: the raw text (line endings as written), the
text with LF endings (as open() gives it), the parsed YAML and the Markdown frontmatter are each
kept by path after their first read, so the checks, the step and the brief digest share one read.
A file is read when first asked for, so errors surface where they did before the model existed.
Loaded by status.py by its file path as `task_model` (see the skill's CLAUDE.md).
"""
import glob
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))

from lib import yamlio  # noqa: E402

def story(feature):
    """The `story` mapping of a feature.yaml (decisions, validations), or {} when it has none or is not a
    mapping: the one reader of a feature's story; the list fields stay as written, for the checks."""
    value = feature.get("story") if isinstance(feature, dict) else None
    return value if isinstance(value, dict) else {}


# Folders the text walk never enters: worktrees, git, archived context and evidence files.
SKIP = {"repos", ".git", os.path.join("context", "archive"), os.path.join("validations", "evidence")}


class Model:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._raw, self._docs, self._frontmatter = {}, {}, {}

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def raw(self, path):
        """The file's text with its line endings as written."""
        key = os.path.abspath(path)
        if key not in self._raw:
            with open(path, encoding="utf-8", newline="") as fh:
                self._raw[key] = fh.read()
        return self._raw[key]

    def put(self, path, text):
        """Keep `text`, just written to the file at `path`, as its read: what was parsed from the old
        content is dropped, so the next load or frontmatter parses the new text without opening the file."""
        key = os.path.abspath(path)
        self._raw[key] = text
        self._docs.pop(key, None)
        self._frontmatter.pop(key, None)

    def text(self, path):
        """The file's text with LF endings, as open() in text mode reads it."""
        return self.raw(path).replace("\r\n", "\n").replace("\r", "\n")

    def load(self, path, default=None):
        """The parsed YAML of the file, or `default` when it is missing or empty (as lib/yamlio.load)."""
        if not os.path.isfile(path):
            return default
        key = os.path.abspath(path)
        if key not in self._docs:
            stream = io.StringIO(self.text(path))
            stream.name = path  # the parser names the file in its error, as when it reads the file itself
            self._docs[key] = yamlio.parse(stream, path)
        data = self._docs[key]
        return default if data is None else data

    def frontmatter(self, path):
        """The mapping in the `---` header of a Markdown file, or {} when it has none."""
        key = os.path.abspath(path)
        if key not in self._frontmatter:
            self._frontmatter[key] = yamlio.frontmatter(self.text(path))
        return self._frontmatter[key]

    def glob(self, *parts):
        """The sorted paths matching the pattern under the root (a directory listing; nothing is read)."""
        return sorted(glob.glob(self.path(*parts)))

    def text_files(self):
        """Every .md and .yaml file of the task, without walking worktrees, git or archives."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel = os.path.relpath(dirpath, self.root)
            dirnames[:] = [d for d in dirnames if os.path.normpath(os.path.join(rel, d)) not in SKIP]
            for name in filenames:
                if name.endswith((".md", ".yaml")):
                    yield os.path.join(dirpath, name)
