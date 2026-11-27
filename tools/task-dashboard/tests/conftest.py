"""Shared fixtures: a temporary home with one current task, one legacy task and one broken task."""
import os
import sys

import pytest

TOOL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOL)

ACS = """\
- id: AC-1
  text: "The thing works."
  status: deciding
  requirements:
    - id: AC-1.1
      text: "it works"
      status: deciding
      decision: D-01
      validations: [V-01]
"""

D01 = """\
id: D-01
title: "How it works"
status: open
date: 2026-11-12
born_from: []
discuss_with: [me]
question: |
  How?
"""

V01 = """\
id: V-01
title: "It works"
status: pending
how: |
  Run it.
"""

README = """\
---
id: 2026-11-12-0900-alpha
title: "Alpha task"
link: null
repos:
  - name: skills
    origin: ~/skills
    worktree: repos/skills
    branch: feat/alpha
    main: true
---

# alpha
"""


def write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


@pytest.fixture
def home(tmp_path):
    alpha = "tasks/skills/2026-11-12-0900-alpha/"
    write(tmp_path, alpha + "README.md", README)
    write(tmp_path, alpha + "acs.yaml", ACS)
    write(tmp_path, alpha + "decisions/D-01-how.yaml", D01)
    write(tmp_path, alpha + "validations/V-01-works.yaml", V01)
    write(tmp_path, alpha + "journal.yaml", "[]\n")
    write(tmp_path, alpha + "pending.yaml", "[]\n")
    old = "tasks/iac/2026-11-10-1000-old/"
    write(tmp_path, old + "README.md", "# old\n")
    write(tmp_path, old + "acs.yaml", "[]\n")
    write(tmp_path, old + "diario.yaml", "[]\n")
    write(tmp_path, old + "decisoes/D-01-x.md", "# x\n")
    write(tmp_path, "tasks/iac/notes/readme.txt", "not a task\n")
    return tmp_path
