#!/usr/bin/env python3
"""status.py - status and consistency checks for a /task folder.

Usage:
    python status.py [task-dir]                 print status, agenda, open pending items and problems
    python status.py [task-dir] --gate plan     also fail when a decision in an active tree is still open
    python status.py [task-dir] --gate spec --feature F   fail when feature F links a decision still open or awaiting a spike
    python status.py [task-dir] --gate pr       also fail when an item is neither concluded nor carries a pr_note
    python status.py [task-dir] --pr-notes      print the pr_note of every item and active decision, then exit
    python status.py [task-dir] --find ID       print <file>:<line> of each place ID is defined, without the checks
    python status.py [task-dir] --json          print the same state as one JSON object (see collect())

Exits 1 when it finds a failure. The folder layout is in ../reference/format.md.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))

try:
    import yaml  # noqa: F401  (only to say how to install it; lib/yamlio reads the files)
except ImportError:
    sys.stderr.write("status.py needs PyYAML (pip install pyyaml).\n")
    sys.exit(2)

from lib import yamlio  # noqa: E402
from lib import modules  # noqa: E402
from lib.yamlio import as_list  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
FLOW_ROADMAP = os.path.join(HERE, "..", "..", "flow", "scripts", "roadmap.py")
flow_roadmap = modules.load(FLOW_ROADMAP, "flow_roadmap")  # /flow owns the roadmap status rule
task_model = modules.load(os.path.join(HERE, "model.py"), "task_model")  # each task file read once per load
task_derive = modules.load(os.path.join(HERE, "derive.py"), "task_derive")  # statuses computed once per load
task_report = modules.load(os.path.join(HERE, "report.py"), "task_report")  # the text report from collect()
task_brief = modules.load(os.path.join(HERE, "brief.py"), "task_brief")  # the brief's digest and generated blocks
task_checks = modules.load(os.path.join(HERE, "checks.py"), "task_checks")  # the folder's consistency checks
task_step = modules.load(os.path.join(HERE, "step.py"), "task_step")  # the next step and who it waits on
task_gates = modules.load(os.path.join(HERE, "gates.py"), "task_gates")  # the gates, PR notes and feature links

INACTIVE = task_derive.INACTIVE
SPIKE_BLOCKING = task_derive.SPIKE_BLOCKING
ORDER = task_derive.ORDER


root_ids = task_derive.root_ids


# The brief's digest and generated blocks live in brief.py; task.py and the tests use them through these names.
SOURCE_GROUPS = task_brief.SOURCE_GROUPS
DIGEST_LENGTH = task_brief.DIGEST_LENGTH
_short_hash = task_brief._short_hash
sources_digest = task_brief.sources_digest
OPEN_ITEMS, NOTHING_OPEN = task_brief.OPEN_ITEMS, task_brief.NOTHING_OPEN
REQUIREMENTS, NO_REQUIREMENTS = task_brief.REQUIREMENTS, task_brief.NO_REQUIREMENTS
NO_ACTIVE_ROOT = task_derive.NO_ACTIVE_ROOT
BLOCK_END, BLOCK_START_PREFIX = task_brief.BLOCK_END, task_brief.BLOCK_START_PREFIX
block_start = task_brief.block_start
block_span = task_brief.block_span
unclosed_block = task_brief.unclosed_block
generated_block = task_brief.generated_block
open_items_block = task_brief.open_items_block
one_line = task_brief.one_line
requirements_block = task_brief.requirements_block
BLOCKS = task_brief.BLOCKS
heading_re = task_brief.heading_re


class Task:
    def __init__(self, root, model=None):
        """The task at `root`, read through `model` when given (a load already made, e.g. after task.py's
        sync put what it wrote into it), else through a new one."""
        self.root = os.path.abspath(root)
        self.model = model or task_model.Model(self.root)
        self.failures, self.warnings = [], []
        self.items = self.model.load(self.path("acs.yaml"), []) or []
        self.journal = self.model.load(self.path("journal.yaml"), []) or []
        self.pending = self.model.load(self.path("pending.yaml"), []) or []
        self.decisions = self.load_dir("decisions", "D")
        self.validations = self.load_dir("validations", "V")
        self.features = self.load_features()
        self.roadmap = self.load_roadmap()
        self.derived = task_derive.Derived(self.items, self.decisions, self.validations, self.features, self.pending)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def fail(self, msg):
        if msg not in self.failures:
            self.failures.append(msg)

    def load_dir(self, sub, prefix):
        found = {}
        for path in self.model.glob(sub, "%s-*.yaml" % prefix):
            data = self.model.load(path, {})
            name = os.path.basename(path)
            if not isinstance(data, dict) or not data.get("id"):
                self.fail("%s/%s: needs an 'id'" % (sub, name))
                continue
            if not name.startswith(str(data["id"]) + "-"):
                self.fail("%s/%s: file name does not start with its id %s" % (sub, name, data["id"]))
            if data["id"] in found:
                self.fail("%s: id %s is used by two files" % (sub, data["id"]))
            data["_file"] = name
            found[data["id"]] = data
        return found

    def load_features(self):
        paths = self.model.glob(".specs", "features", "*", "feature.yaml")
        return flow_roadmap.features_from(paths, lambda p: self.model.load(p, {}))

    def load_roadmap(self):
        """Roadmap features by id, from .specs/roadmap.yaml, read by /flow's rule."""
        data = self.model.load(self.path(".specs", "roadmap.yaml"), {}) or {}
        if not isinstance(data, dict):
            return {}
        return {rid: feat for rid, (_, feat) in flow_roadmap.roadmap_features(data).items()}

    # ------------------------------------------------------------ spikes

    def blocking_spikes(self):
        """(id, validation) of every spike that still blocks its decisions."""
        return self.derived.blocking_spikes()

    def spikes_of(self, d):
        """Spikes (validations with 'decides') naming decision d that still block it."""
        return self.derived.spikes_of(d)

    def blocked_features(self, val):
        """Roadmap and spec'd features that link a decision spike val decides, sorted."""
        return task_gates.blocked_features(self, val)

    # ------------------------------------------------------------ checks

    def chain_end(self, d):
        """The first decision after d along superseded_by that is not superseded, or None on a broken link or a cycle."""
        return self.derived.chain_end(d)

    def decision_status(self, decision):
        """The status of a decision id, or None when it is not one of the task's decisions."""
        return self.derived.decision_status(decision)

    def active_root(self, decision):
        """The active decision a requirement rooted at `decision` hangs from, or NO_ACTIVE_ROOT."""
        return self.derived.active_root(decision)

    def text_files(self):
        """Every .md and .yaml file of the task, without walking worktrees, git or archives."""
        return self.model.text_files()

    def check(self):
        """Every check of the folder (checks.py); sets req_tree and dec_features for collect() and the gates."""
        task_checks.run(self)

    def active_items(self):
        return self.derived.active_items()

    def repo_names(self):
        """Repo names from the README header, or None when the README has no repos list."""
        path = self.path("README.md")
        if not os.path.isfile(path):
            return None
        fm = self.model.frontmatter(path)
        if not isinstance(fm.get("repos"), list):
            return None
        return {str(r.get("name")) for r in fm["repos"] if isinstance(r, dict)}

    # ------------------------------------------------------------ status

    def req_status(self, req):
        return self.derived.req_status(req)

    def item_status(self, item):
        return self.derived.item_status(item)

    def missing(self, req):
        """What keeps req from its next status, by the status it has: one dict per blocker."""
        return self.derived.missing(req)

    def missing_text(self, req):
        return "; ".join(m["text"] for m in self.missing(req)) or "-"

    # ------------------------------------------------------------ structured state

    def readme(self):
        path = self.path("README.md")
        return self.model.frontmatter(path) if os.path.isfile(path) else {}

    def repos(self):
        """The repos listed in the README header; [] when there is none."""
        return [r for r in as_list(self.readme().get("repos")) if isinstance(r, dict)]

    def roadmap_milestones(self):
        data = self.model.load(self.path(".specs", "roadmap.yaml"), {}) or {}
        out = []
        for ms in as_list(data.get("milestones") if isinstance(data, dict) else None):
            if not isinstance(ms, dict):
                continue
            feats = [{"id": str(f.get("id")), "title": f.get("title"), "status": f.get("status"),
                      "goal": f.get("goal"), "blocked_by": [str(b) for b in as_list(f.get("blocked_by"))]}
                     for f in as_list(ms.get("features")) if isinstance(f, dict) and f.get("id") is not None]
            out.append({"id": ms.get("id"), "title": ms.get("title"), "status": ms.get("status"),
                        "outcome": ms.get("outcome"), "features": feats})
        return out

    def agenda(self):
        """Open or proposed decisions and open pending items, grouped by who they wait on."""
        return self.derived.agenda()

    def agenda_lines(self):
        """The agenda as one line per entry, by person: the Agenda of the report and the open-items block of the brief."""
        return task_report.agenda_lines(self.agenda())

    def collect(self):
        """The task's whole state as plain data; call after check(). Printed by --json."""
        fm = self.readme()
        reqs, items = [], []
        for item in self.items:
            dropped = item.get("status") == "dropped"
            items.append({"id": item.get("id"), "text": item.get("text"),
                          "status": "dropped" if dropped else self.item_status(item),
                          "pr_note": item.get("pr_note"),
                          "requirements": [r.get("id") for r in as_list(item.get("requirements"))]})
            if dropped:
                continue
            for req in as_list(item.get("requirements")):
                rid = req.get("id")
                reqs.append({
                    "id": rid, "item": item.get("id"), "text": req.get("text"), "status": self.req_status(req),
                    "decision": (root_ids(req) or [None])[0], "tree": self.req_tree.get(rid, []),
                    "validations": [{"id": v, "status": self.validations.get(v, {}).get("status")}
                                    for v in as_list(req.get("validations"))],
                    "missing": self.missing(req)})
        features = []
        for name, feat in self.features.items():
            story = task_model.story(feat)
            features.append({"id": name, "roadmap": None if feat.get("roadmap") is None else str(feat["roadmap"]),
                             "title": feat.get("title"), "status": feat.get("status"), "size": feat.get("size"),
                             "repo": feat.get("repo"), "pr": feat.get("pr"),
                             "decisions": as_list(story.get("decisions")), "validations": as_list(story.get("validations"))})
        spikes = [{"id": v, "status": val.get("status"), "where": val.get("where"),
                   "decides": as_list(val.get("decides")), "blocks": self.blocked_features(val)}
                  for v, val in self.blocking_spikes()]
        return {
            "task": {"id": os.path.basename(self.root), "root": self.root.replace(os.sep, "/"),
                     "title": fm.get("title"), "link": fm.get("link"),
                     "repos": self.repos()},
            "step": self.step(),
            "items": items, "requirements": reqs, "features": features,
            "roadmap": self.roadmap_milestones(), "spikes": spikes, "agenda": self.agenda(),
            "warnings": list(self.warnings), "failures": list(self.failures),
        }

    def waits(self, ident, in_pending):
        return task_step.waits(self, ident, in_pending)

    def item_waits(self, ident, in_pending):
        return task_step.item_waits(self, ident, in_pending)

    def step(self):
        """The /task step to take next (step.py)."""
        return task_step.step(self)

    def report(self):
        """The text report, rendered from collect() and what it does not carry: each decision's and
        validation's status, and every root each requirement names, in collect()'s order."""
        statuses = {d: dec.get("status") for d, dec in self.decisions.items()}
        statuses.update({v: val.get("status", "?") for v, val in self.validations.items()})
        roots = [root_ids(req) for item in self.active_items() for req in as_list(item.get("requirements"))]
        return task_report.render(self.collect(), statuses, roots)

    # ------------------------------------------------------------ gates

    def feature_decisions(self, fid):
        return task_gates.feature_decisions(self, fid)

    def features_of(self, d):
        return task_gates.features_of(self, d)

    def gate(self, name, feature=None):
        task_gates.gate(self, name, feature)

    def pr_notes(self):
        return task_gates.pr_notes(self)

    def find(self, ident):
        """Each place ident is defined, as <file>:<line>: a YAML `id:` line or a Markdown heading."""
        defined = re.compile(r"""^\s*(?:-\s+)?id:\s*["']?%s["']?\s*$|^#+\s+%s(?![\w.-])""" % (re.escape(ident), re.escape(ident)))
        hits = []
        for path in sorted(self.text_files()):
            for n, line in enumerate(self.model.text(path).split("\n"), 1):
                if defined.match(line):
                    hits.append("%s:%d" % (os.path.relpath(path, self.root).replace("\\", "/"), n))
        return hits


def main(argv=None):
    try:
        return run(argv)
    except yamlio.YamlError as exc:
        raise SystemExit(str(exc))


def run(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="?", default=".")
    ap.add_argument("--gate", choices=("plan", "spec", "pr"))
    ap.add_argument("--feature", help="with --gate spec: the feature id (e.g. F1.1)")
    ap.add_argument("--pr-notes", action="store_true")
    ap.add_argument("--find", metavar="ID", help="print <file>:<line> where ID is defined, and skip the checks")
    ap.add_argument("--json", action="store_true", help="print the state as one JSON object")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.isfile(os.path.join(args.task, "acs.yaml")):
        print("ERROR: %s has no acs.yaml; not a task folder" % os.path.abspath(args.task))
        return 2
    task = Task(args.task)
    if args.find:
        hits = task.find(args.find)
        print("\n".join(hits) if hits else "%s is not defined" % args.find)
        return 0 if hits else 1
    task.check()
    if args.pr_notes:
        print(task.pr_notes())
        return 1 if task.failures else 0
    if args.gate == "spec" and not args.feature:
        ap.error("--gate spec needs --feature")
    if args.gate:
        task.gate(args.gate, args.feature)
    if args.json:
        print(json.dumps(task.collect(), ensure_ascii=False, indent=1, default=str))
        return 1 if task.failures else 0
    print(task.report())
    if task.warnings:
        print("\n# Warnings\n")
        print("\n".join("- %s" % w for w in task.warnings))
    if task.failures:
        print("\n# Failures\n")
        print("\n".join("- %s" % f for f in task.failures))
        return 1
    print("\nNo failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
