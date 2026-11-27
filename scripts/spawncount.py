"""Count the processes a pytest suite starts, by program and by test (see TESTING.md).

Usage, under the same `uv run` as the suite's test command:
    python scripts/spawncount.py <suite-folder> [pytest args]

It changes into <suite-folder>, runs pytest there serially (xdist off, so one process sees every
spawn) and prints, after the usual summary, how many processes started, their wall time, the count
and time per program (a git call named by its subcommand) and the ten tests that started the most.
A process is timed from its start to its first wait(); one never waited is counted with no time.
As a plugin: `python -m pytest -p spawncount` with this folder on PYTHONPATH.
"""
import os
import subprocess
import sys
import time
from dataclasses import dataclass

import pytest

GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
TOP_TESTS = 10


def spawn_label(args, shell=False):
    """The label of a spawn: `git <subcommand>` for git, the executable's file name otherwise."""
    if shell or isinstance(args, (str, bytes)):
        text = os.fsdecode(args)
        return "shell: " + (text.split() or [""])[0]
    args = [os.fsdecode(a) for a in args]
    if not args:
        return "?"
    name = os.path.basename(args[0])
    if os.path.splitext(name)[0].lower() != "git":
        return name
    rest = iter(args[1:])
    for arg in rest:
        if arg in GIT_OPTIONS_WITH_VALUE:
            next(rest, None)
        elif not arg.startswith("-"):
            return "git " + arg
    return "git"


@dataclass
class Spawn:
    """What the counter keeps on one Popen: when it started, its label, whether its time is added."""
    started: float
    label: str
    timed: bool = False


@dataclass
class Tally:
    """Processes and their wall time, for one program."""
    count: int = 0
    seconds: float = 0.0


def safe_label(args, shell):
    """spawn_label, or "?" when it cannot read args: Popen itself then reports what is wrong."""
    try:
        return spawn_label(args, shell)
    except Exception:
        return "?"


class Counter:
    """Wraps subprocess.Popen while installed: counts each start, times it until its first wait."""

    def __init__(self):
        self.count = 0
        self.seconds = 0.0
        self.by_program = {}
        self.per_test = []
        self._saved = None

    def install(self):
        counter = self
        init, wait = subprocess.Popen.__init__, subprocess.Popen.wait
        self._saved = init, wait

        def counted_init(popen, args, *a, **kw):
            popen._spawncount = Spawn(time.perf_counter(), safe_label(args, kw.get("shell", False)))
            init(popen, args, *a, **kw)
            counter.count += 1
            counter.by_program.setdefault(popen._spawncount.label, Tally()).count += 1

        def timed_wait(popen, *a, **kw):
            result = wait(popen, *a, **kw)
            spawn = getattr(popen, "_spawncount", None)
            if spawn and not spawn.timed:
                spawn.timed = True
                seconds = time.perf_counter() - spawn.started
                counter.seconds += seconds
                counter.by_program[spawn.label].seconds += seconds
            return result

        subprocess.Popen.__init__, subprocess.Popen.wait = counted_init, timed_wait

    def uninstall(self):
        if self._saved:
            subprocess.Popen.__init__, subprocess.Popen.wait = self._saved
            self._saved = None

    # pytest hooks: registered as a plugin object.

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        count, seconds = self.count, self.seconds
        yield
        self.per_test.append((item.nodeid, self.count - count, self.seconds - seconds))

    def pytest_terminal_summary(self, terminalreporter):
        write = terminalreporter.write_line
        write("")
        write("spawns: %d  spawn time: %.1fs" % (self.count, self.seconds))
        write("by program (count, seconds):")
        for label, tally in sorted(self.by_program.items(), key=lambda item: -item[1].count):
            write("  %5d %7.1fs  %s" % (tally.count, tally.seconds, label))
        write("top tests by spawns:")
        ranked = sorted((t for t in self.per_test if t[1]), key=lambda t: -t[1])[:TOP_TESTS]
        for nodeid, n, seconds in ranked:
            write("  %4d spawns %6.1fs  %s" % (n, seconds, nodeid))


_counter = None


def pytest_configure(config):
    """Install the counter when loaded with -p spawncount."""
    global _counter
    if _counter is None:
        _counter = Counter()
        _counter.install()
        config.pluginmanager.register(_counter, "spawncount-counter")


def pytest_unconfigure(config):
    global _counter
    if _counter is not None:
        _counter.uninstall()
        _counter = None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        sys.stderr.write(__doc__)
        return 2
    folder, args = argv[0], argv[1:]
    cwd = os.getcwd()
    os.chdir(folder)
    try:
        return int(pytest.main(["-p", "no:xdist", *args], plugins=[sys.modules[__name__]]))
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    sys.exit(main())
