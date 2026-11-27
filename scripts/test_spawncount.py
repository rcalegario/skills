"""Tests for spawncount.py. Run from the repo root: python -m pytest -q scripts/test_spawncount.py"""
import os
import re
import subprocess
import sys

import spawncount

INNER = """\
import subprocess
import sys


def test_two_pythons():
    subprocess.run([sys.executable, "-c", "pass"], check=True)
    subprocess.run([sys.executable, "-c", "pass"], check=True)


def test_one_git():
    subprocess.run(["git", "-c", "core.pager=cat", "-C", ".", "version"], check=True,
                   stdout=subprocess.PIPE)


def test_none():
    pass
"""

KEEPS = """\
import subprocess
import sys


def test_exit_code_and_output():
    done = subprocess.run([sys.executable, "-c", "import sys; print('hi'); sys.stderr.write('oops'); sys.exit(3)"],
                          capture_output=True, text=True)
    assert done.returncode == 3
    assert done.stdout.strip() == "hi"
    assert done.stderr == "oops"
"""


def run_counted(folder, capsys, *args):
    cwd = os.getcwd()
    code = spawncount.main([str(folder), "-p", "no:cacheprovider", *args])
    assert os.getcwd() == cwd
    return code, capsys.readouterr().out


def test_summary_counts_processes_by_program_and_test(tmp_path, capsys):
    (tmp_path / "test_inner.py").write_text(INNER)
    code, out = run_counted(tmp_path, capsys)
    assert code == 0, out
    assert re.search(r"^spawns: 3 +spawn time: [\d.]+s", out, re.M), out
    python = os.path.basename(sys.executable)
    assert re.search(r"^ +2 +[\d.]+s +%s$" % re.escape(python), out, re.M), out
    assert re.search(r"^ +1 +[\d.]+s +git version$", out, re.M), out
    tests = out.split("top tests by spawns:")[1].splitlines()
    assert "test_two_pythons" in tests[1] and re.match(r" +2 spawns", tests[1]), out
    assert "test_one_git" in tests[2], out
    assert not any("test_none" in line for line in tests), out


def test_counted_process_keeps_its_exit_code_and_output(tmp_path, capsys):
    (tmp_path / "test_keeps.py").write_text(KEEPS)
    code, out = run_counted(tmp_path, capsys)
    assert code == 0, out
    assert "spawns: 1 " in out, out


def test_subprocess_is_restored_after_the_run(tmp_path, capsys):
    # Restoring Popen is the behaviour here: a counted run must leave the caller's subprocess as it was.
    before = subprocess.Popen.__init__, subprocess.Popen.wait
    (tmp_path / "test_none.py").write_text("def test_none():\n    pass\n")
    run_counted(tmp_path, capsys)
    assert (subprocess.Popen.__init__, subprocess.Popen.wait) == before


def test_a_label_that_fails_leaves_the_process_alone(monkeypatch):
    def broken(args, shell=False):
        raise ValueError("cannot label")
    monkeypatch.setattr(spawncount, "spawn_label", broken)
    counter = spawncount.Counter()
    counter.install()
    try:
        done = subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True)
    finally:
        counter.uninstall()
    assert done.returncode == 0 and done.stdout.strip() == "ok"
    assert counter.count == 1 and counter.by_program["?"].count == 1
