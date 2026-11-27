#!/usr/bin/env python3
"""task.py - writes the YAML files of a /task folder, so no id, date or status is typed by hand.

Usage:
    python task.py [task-dir] journal --type T --text TEXT [--refs D-01,V-02]
    python task.py [task-dir] new decision SLUG --title T --question Q [--born-from D-01] [--requirement AC-1.1] [--discuss-with me]
    python task.py [task-dir] new validation SLUG --title T --how H --expected E [--where W] [--decides D-01]
    python task.py [task-dir] new pending --with WHO --action A [--refs D-01]
    python task.py [task-dir] decide D-nn --decision TEXT --why TEXT [--proposed] [--pr-note TEXT]
    python task.py [task-dir] supersede D-old D-new
    python task.py [task-dir] validate V-nn --status passed|failed|dropped [--evidence TEXT] [--attach FILE]
    python task.py [task-dir] close P-n [--status done|dropped] [--link URL]
    python task.py [task-dir] consolidate
    python task.py [task-dir] sync

`sync` writes the status of every requirement and item (acs.yaml) and of every roadmap feature and milestone
(.specs/roadmap.yaml) from the rest of the folder, and the generated blocks of brief.md: the requirements
(BRIEF-2) from acs.yaml and the open items (BRIEF-4) from the decisions and pending.yaml; every other command
does it after its own edit. None of these is typed by hand.

Each command edits only the lines it owns (comments and order stay), then runs the status.py checks and
exits 1 when the folder has failures. The folder layout is in ../reference/format.md.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

import status  # noqa: E402  (by name: task.py runs only as a script, whose folder Python puts on sys.path)
from lib import modules  # noqa: E402
from lib import yamledit as ye  # noqa: E402
from lib import yamlio  # noqa: E402

# Loaded by file path, never through sys.path (see the skill's CLAUDE.md).
commands = modules.load(os.path.join(HERE, "commands.py"), "task_commands")  # each command's edit
task_sync = modules.load(os.path.join(HERE, "sync.py"), "task_sync")  # acs, brief and roadmap from one load


def cmd_sync(loaded):
    """Sync the loaded task (sync.py)."""
    return "sync: %d acs.yaml line(s) changed" % task_sync.sync(loaded)


def cmd_consolidate(root, a):
    """consolidate with status.py's sources digest, looked up at each call (the tests patch it there)."""
    return commands.cmd_consolidate(root, a, status.sources_digest)


def cmd_new(root, a):
    return {"decision": commands.cmd_new_decision, "validation": commands.cmd_new_validation,
            "pending": commands.cmd_new_pending}[a.kind](root, a)


# The edit each command makes before the load, the sync and the check.
EDITS = {"journal": commands.cmd_journal, "new": cmd_new, "decide": commands.cmd_decide,
         "supersede": commands.cmd_supersede, "validate": commands.cmd_validate, "close": commands.cmd_close,
         "consolidate": cmd_consolidate}


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="?", default=".")
    sub = ap.add_subparsers(dest="command")
    sub.required = True

    def add(name, parent=sub, **kw):
        return parent.add_parser(name, **kw)

    j = add("journal")
    j.add_argument("--type", required=True)
    j.add_argument("--text", required=True)
    j.add_argument("--refs")

    new = add("new").add_subparsers(dest="kind")
    new.required = True
    d = add("decision", new)
    d.add_argument("slug")
    d.add_argument("--title", required=True)
    d.add_argument("--question", required=True)
    d.add_argument("--born-from")
    d.add_argument("--requirement", help="AC-n.m whose root decision this becomes")
    d.add_argument("--discuss-with")
    v = add("validation", new)
    v.add_argument("slug")
    v.add_argument("--title", required=True)
    v.add_argument("--how", required=True)
    v.add_argument("--expected", required=True)
    v.add_argument("--where", default="clone")
    v.add_argument("--decides", help="makes it a spike that settles these decisions")
    p = add("pending", new)
    p.add_argument("--with", dest="who", required=True)
    p.add_argument("--action", required=True)
    p.add_argument("--refs")

    de = add("decide")
    de.add_argument("id")
    de.add_argument("--decision", required=True)
    de.add_argument("--why")
    de.add_argument("--proposed", action="store_true")
    de.add_argument("--pr-note")
    su = add("supersede")
    su.add_argument("old")
    su.add_argument("new")
    va = add("validate")
    va.add_argument("id")
    va.add_argument("--status", required=True, choices=("passed", "failed", "dropped"))
    va.add_argument("--evidence")
    va.add_argument("--attach", action="append", help="file name under validations/evidence/")
    cl = add("close")
    cl.add_argument("id")
    cl.add_argument("--status", default="done", choices=("done", "dropped"))
    cl.add_argument("--link")
    add("consolidate")
    add("sync")
    return ap


def main(argv=None):
    try:
        return run(argv)
    except yamlio.YamlError as exc:
        raise SystemExit(str(exc))


def run(argv):
    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.task)
    if not os.path.isfile(os.path.join(root, "acs.yaml")):
        print("ERROR: %s has no acs.yaml; not a task folder" % root)
        return 2
    # The command edits its own file; then the task is loaded once, synced from that load, and the
    # check runs over the same load, which holds what sync wrote. `sync` has no edit of its own.
    try:
        if args.command == "sync":
            loaded = status.Task(root)
            print(cmd_sync(loaded))
        else:
            print(EDITS[args.command](root, args))
    except (commands.Refusal, ye.EditError) as exc:
        print("ERROR: %s" % exc)
        return 1
    if args.command != "sync":
        loaded = status.Task(root)
        task_sync.sync(loaded)
    check = status.Task(root, loaded.model)
    check.check()
    for failure in check.failures:
        print("FAIL: %s" % failure)
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
