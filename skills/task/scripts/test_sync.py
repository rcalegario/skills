"""Tests for one load per task.py command (sync.py, model.py). Run: python -m pytest <skill-dir>/scripts -q"""
import builtins
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import task as task_cli  # noqa: E402


def count_reads(monkeypatch, root):
    """A Counter of the task files opened for reading, by path relative to root."""
    reads = collections.Counter()
    real_open = builtins.open
    base = os.path.normcase(str(root))

    def counting_open(file, mode="r", *a, **kw):
        path = os.path.normcase(os.path.abspath(str(file)))
        if path.startswith(base) and not any(m in mode for m in "wax"):
            reads[os.path.relpath(path, base)] += 1
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", counting_open)
    return reads


def test_a_command_reads_each_file_once_after_its_edit(task, monkeypatch, capsys):
    reads = count_reads(monkeypatch, task)
    task_cli.main([str(task), "journal", "--type", "note", "--text", "a note"])
    capsys.readouterr()
    assert reads, "the command read no task file"
    assert {f: n for f, n in reads.items() if n > 1 and f != "journal.yaml"} == {}


def test_the_check_sees_what_sync_wrote_without_reading_it(task, monkeypatch, capsys):
    acs = task / "acs.yaml"
    acs.write_text(acs.read_text(encoding="utf-8").replace("status: decided", "status: proposed"), encoding="utf-8")
    brief = (task / "brief.md").read_text(encoding="utf-8")
    reads = count_reads(monkeypatch, task)
    code = task_cli.main([str(task), "sync"])
    out = capsys.readouterr().out
    assert (task / "acs.yaml").read_text(encoding="utf-8").count("status: proposed") == 0  # sync rewrote the statuses
    assert (task / "brief.md").read_text(encoding="utf-8") != brief  # and inserted the generated blocks
    assert "FAIL" not in out and code == 0
    assert reads["acs.yaml"] == 1 and reads["brief.md"] == 1


def test_sync_leaves_a_right_roadmap_unwritten(task, monkeypatch, capsys):
    task_cli.main([str(task), "sync"])  # every status right from here on
    roadmap = os.path.normcase(str(task / ".specs" / "roadmap.yaml"))
    before = (task / ".specs" / "roadmap.yaml").read_bytes()
    writes = []
    real_open = builtins.open

    def recording_open(file, mode="r", *a, **kw):
        if os.path.normcase(os.path.abspath(str(file))) == roadmap and any(m in mode for m in "wax"):
            writes.append(mode)
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", recording_open)
    task_cli.main([str(task), "sync"])
    capsys.readouterr()
    assert writes == []
    assert (task / ".specs" / "roadmap.yaml").read_bytes() == before
