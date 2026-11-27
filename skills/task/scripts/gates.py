"""gates.py - the gates of a /task folder (plan, spec, pr), its PR notes and the links between
features and decisions they read.

Each function reads the status.Task facade it is given after its checks ran, and reports through
task.fail and task.warnings. Loaded by status.py by its file path as `task_gates`; the rules are in
../reference/format.md.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from lib import modules  # noqa: E402
from lib.yamlio import as_list  # noqa: E402

task_model = modules.load(os.path.join(HERE, "model.py"), "task_model")
task_derive = modules.load(os.path.join(HERE, "derive.py"), "task_derive")
task_step = modules.load(os.path.join(HERE, "step.py"), "task_step")


def matches(fid, name):
    """True when feature id fid (e.g. F1.1) names roadmap id or feature folder name (e.g. F1.1-template)."""
    return fid == name or name.startswith(fid + "-") or fid.startswith(name + "-")


def feature_decisions(task, fid):
    """Decisions linked to feature fid: its roadmap entry's 'decisions' and its feature.yaml story."""
    found = []
    for rid, feat in task.roadmap.items():
        if matches(fid, rid):
            found += as_list(feat.get("decisions"))
    for name, feat in task.features.items():
        if matches(fid, name):
            found += as_list(task_model.story(feat).get("decisions"))
    return [d for i, d in enumerate(found) if d not in found[:i]]


def features_of(task, d):
    """Roadmap and spec'd features that link decision d."""
    out = {rid for rid, feat in task.roadmap.items() if d in as_list(feat.get("decisions"))}
    return out | set(task.dec_features.get(d, []))


def blocked_features(task, val):
    """Roadmap and spec'd features that link a decision spike val decides, sorted."""
    return sorted({f for d in as_list(val.get("decides")) for f in features_of(task, d)})


def gate(task, name, feature=None):
    if name == "spec":
        if not any(matches(feature, n) for n in list(task.roadmap) + list(task.features)):
            task.fail("gate spec: feature %s is neither in the roadmap nor in .specs/features" % feature)
        for d in feature_decisions(task, feature):
            dec = task.decisions.get(d)
            if dec is None:
                continue
            waits = task.spikes_of(d)
            if waits:
                task.fail("gate spec: %s waits for spike %s, which decides %s" % (feature, ", ".join(waits), d))
            elif dec.get("status") == "open":
                task.fail("gate spec: %s links %s, which is open" % (feature, d))
            elif dec.get("status") == "proposed":
                task.warnings.append("gate spec: %s links %s, which is proposed" % (feature, d))
        return
    if name == "plan":
        for item in task.active_items():
            for req in as_list(item.get("requirements")):
                for d in task.req_tree.get(req.get("id"), []):
                    st = task.decisions[d].get("status")
                    if st == "open":
                        task.fail("gate plan: %s is open (tree of %s)" % (d, req.get("id")))
                    elif st == "proposed":
                        task.warnings.append("gate plan: %s is proposed; list it in BRIEF-4" % d)
    elif name == "pr":
        for item, st in task_step.unproven(task):
            task.fail("gate pr: %s is %s and has no pr_note" % (item.get("id"), st))
        for p in task_derive.open_pending(task.pending):
            task.warnings.append("gate pr: %s is still open" % p.get("id"))


def pr_notes(task):
    out = []
    for item in task.active_items():
        if task_step.pr_note(item):
            out.append("## %s (%s)\n\n%s" % (item.get("id"), task.item_status(item), task_step.pr_note(item)))
    for d, dec in task.decisions.items():
        if dec.get("status") not in task_derive.INACTIVE and task_step.pr_note(dec):
            out.append("## %s %s\n\n%s" % (d, dec.get("title"), task_step.pr_note(dec)))
    vals = ["- %s %s: %s" % (v, val.get("title"), val.get("status")) for v, val in task.validations.items()
            if val.get("status") != "dropped"]
    if vals:
        out.append("## Validations\n\n" + "\n".join(vals))
    return "\n\n".join(out)
