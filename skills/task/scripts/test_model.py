"""Tests for the one read per load of status.py (model.py). Run: python -m pytest <skill-dir>/scripts -q"""
import builtins
import collections
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402


@pytest.mark.parametrize("args", [[], ["--json"], ["--gate", "plan"], ["--gate", "pr"],
                                  ["--gate", "spec", "--feature", "F1.1"], ["--pr-notes"], ["--find", "D-01"]])
def test_one_status_run_opens_each_file_once(task, monkeypatch, capsys, args):
    opened = collections.Counter()
    real_open = builtins.open
    root = os.path.normcase(str(task))

    def counting_open(file, *a, **kw):
        path = os.path.normcase(os.path.abspath(str(file)))
        if path.startswith(root):
            opened[os.path.relpath(path, root)] += 1
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", counting_open)
    status.main([str(task)] + args)
    capsys.readouterr()
    assert opened, "the run read no task file"
    assert {f: n for f, n in opened.items() if n > 1} == {}


def test_bad_yaml_names_the_first_broken_file(task):
    broken = "id: D-01\ntitle: [unclosed\n"
    (task / "decisions" / "D-01-source.yaml").write_text(broken, encoding="utf-8")
    (task / ".specs" / "roadmap.yaml").write_text("milestones: [\n", encoding="utf-8")
    path = os.path.join(str(task), "decisions", "D-01-source.yaml")
    with pytest.raises(SystemExit) as exc:
        status.main([str(task)])
    message = str(exc.value)
    assert message.startswith("%s is not valid YAML: " % path)
    assert 'in "%s", line 2' % path in message
