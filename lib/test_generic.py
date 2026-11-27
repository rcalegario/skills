"""lib/ stays generic: no module names a file, field or status of a skill (README.md, Rule)."""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# Names that belong to the task and flow skills' files. Extend it when a skill adds a file or a field.
SKILL_WORDS = [
    "acs.yaml", "feature.yaml", "roadmap", "journal", "pending.yaml", "brief", "decision", "validation",
    "milestone", "blocked_by", "born_from", "story", "superseded", "verifying", "spike",
]


def modules():
    return [p for p in glob.glob(os.path.join(HERE, "*.py")) if not os.path.basename(p).startswith("test_")]


def test_lib_names_nothing_of_task_or_flow():
    hits = []
    for path in modules():
        text = open(path, encoding="utf-8").read()
        for word in SKILL_WORDS:
            if re.search(r"\b%s\b" % re.escape(word), text, re.I):
                hits.append("%s: %s" % (os.path.basename(path), word))
    assert modules() and not hits, hits
