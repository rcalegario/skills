"""Tests for the folder checks (checks.py). Run: python -m pytest <skill-dir>/scripts -q"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402

ORPHAN = "id: D-03\ntitle: O\nstatus: open\nborn_from: []\ndiscuss_with: [me]\nquestion: Q?\n"


def test_born_from_cycle_fails_once_after_the_links(task, capsys):
    d01 = task / "decisions" / "D-01-source.yaml"
    d01.write_text(d01.read_text().replace("born_from: []", "born_from: [D-02]"))
    (task / "decisions" / "D-03-orphan.yaml").write_text(ORPHAN)
    assert status.main([str(task)]) == 1
    failures = capsys.readouterr().out.split("# Failures")[1].split("\n")
    cycle = "- cycle in born_from: D-01 -> D-02 -> D-01"
    assert failures.count(cycle) == 1
    assert failures.index(cycle) > failures.index("- D-03: orphan (not in the tree of any requirement)")


def test_decision_born_from_itself_fails_as_a_cycle(task, capsys):
    d01 = task / "decisions" / "D-01-source.yaml"
    d01.write_text(d01.read_text().replace("born_from: []", "born_from: [D-01]"))
    assert status.main([str(task)]) == 1
    failures = capsys.readouterr().out.split("# Failures")[1].split("\n")
    assert failures.count("- cycle in born_from: D-01 -> D-01") == 1
