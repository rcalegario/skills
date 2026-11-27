"""derive.py - what a /task folder's files imply: the decision trees, the features of each decision,
and the status and blockers of each requirement and item, each computed once per load.

A Derived works on the entries status.Task loaded (one model, D-01 in the task that built it) and fails
nothing: the checks in status.py report what is wrong, worded and ordered as before. The rules are the
ones in ../reference/format.md, Status. Loaded by status.py by its file path as `task_derive`.

Each value is kept for the life of the Derived, which holds the entries as loaded: a folder that changed
needs a new status.Task (and so a new Derived), never a change to the entries it was built from.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))

from lib import modules  # noqa: E402
from lib.yamlio import as_list  # noqa: E402

task_model = modules.load(os.path.join(os.path.dirname(os.path.realpath(__file__)), "model.py"), "task_model")

INACTIVE = {"superseded", "dropped"}
SPIKE_BLOCKING = ("pending", "failed")  # a spike unblocks its decisions once passed or dropped
ORDER = ["discovery", "deciding", "decided", "built", "concluded"]
NO_ACTIVE_ROOT = "no active root"


def open_pending(pending):
    """The entries of pending.yaml still open."""
    return [p for p in pending if isinstance(p, dict) and p.get("status") == "open"]


def root_ids(req):
    """The root decision of a requirement as a list: one id, or the list written (it takes one)."""
    value = req.get("decision")
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def req_key(req):
    """The memo key of a requirement: what its status reads from its own entry (id, root, validations).

    The key is the content, not the requirement id, because callers also ask about entries that are not
    in acs.yaml (a requirement built by hand) and two such entries with one id may differ; repr makes
    the values hashable whatever their YAML type."""
    return (repr(req.get("id")), repr(root_ids(req)), repr(as_list(req.get("validations"))))


class Derived:
    def __init__(self, items, decisions, validations, features, pending):
        self.items, self.decisions, self.validations = items, decisions, validations
        self.features, self.pending = features, pending
        self._memo = {}

    def _once(self, key, compute):
        if key not in self._memo:
            self._memo[key] = compute()
        return self._memo[key]

    def active_items(self):
        return [i for i in self.items if i.get("status") != "dropped"]

    # ------------------------------------------------------------ decisions

    def children(self):
        """{decision: its active children by born_from}."""
        def compute():
            out = {d: [] for d in self.decisions}
            for d, dec in self.decisions.items():
                if dec.get("status") in INACTIVE:
                    continue
                for parent in as_list(dec.get("born_from")):
                    if parent in out:
                        out[parent].append(d)
            return out
        return self._once(("children",), compute)

    def tree(self, d):
        """d and all its active children, recursively; a born_from cycle stops the walk (checks.py reports it)."""
        def walk(node, path):
            if node in path:
                return []
            out = [node]
            for child in self.children().get(node, []):
                out += [x for x in walk(child, path + (node,)) if x not in out]
            return out

        return self._once(("tree", d), lambda: walk(d, ()))

    def req_tree(self):
        """{requirement id: the decisions of the trees of its active roots}, for the items not dropped."""
        def compute():
            out = {}
            for item in self.active_items():
                for req in as_list(item.get("requirements")):
                    tree = []
                    for r in root_ids(req):
                        if r in self.decisions:
                            tree += [x for x in self.tree(r) if x not in tree]
                    out[req.get("id")] = tree
            return out
        return self._once(("req_tree",), compute)

    def dec_features(self):
        """{decision: the features whose story links it}."""
        def compute():
            out = {d: [] for d in self.decisions}
            for name, feat in self.features.items():
                story = task_model.story(feat)
                for d in as_list(story.get("decisions")):
                    if d in out:
                        out[d].append(name)
            return out
        return self._once(("dec_features",), compute)

    def chain_end(self, d):
        """The first decision after d along superseded_by that is not superseded, or None on a broken link or a cycle."""
        seen = {d}
        nxt = self.decisions[d].get("superseded_by")
        while nxt in self.decisions and nxt not in seen:
            if self.decisions[nxt].get("status") != "superseded":
                return nxt
            seen.add(nxt)
            nxt = self.decisions[nxt].get("superseded_by")
        return None

    def decision_status(self, decision):
        """The status of a decision id, or None when it is not one of the task's decisions."""
        if not isinstance(decision, str) or decision not in self.decisions:
            return None
        return self.decisions[decision].get("status")

    def active_root(self, decision):
        """The decision a requirement rooted at `decision` hangs from today: it, or the active end of its
        superseded_by chain; NO_ACTIVE_ROOT when there is none."""
        if self.decision_status(decision) == "superseded":
            decision = self.chain_end(decision)
        return decision if self.decision_status(decision) not in (None, "dropped") else NO_ACTIVE_ROOT

    # ------------------------------------------------------------ spikes

    def blocking_spikes(self):
        """(id, validation) of every spike that still blocks its decisions."""
        return self._once(("blocking_spikes",), lambda: [
            (v, val) for v, val in self.validations.items()
            if as_list(val.get("decides")) and val.get("status") in SPIKE_BLOCKING])

    def spikes_of(self, d):
        """Spikes (validations with 'decides') naming decision d that still block it."""
        return [v for v, val in self.blocking_spikes() if d in as_list(val.get("decides"))]

    # ------------------------------------------------------------ status

    def req_status(self, req):
        return self._once(("req_status",) + req_key(req), lambda: self.compute_req_status(req))

    def compute_req_status(self, req):
        """The status of a requirement by format.md, Status (req_status keeps it per load)."""
        tree = self.req_tree().get(req.get("id"), [])
        vals = as_list(req.get("validations"))
        if len(root_ids(req)) != 1 or not vals or not tree:
            return "discovery"
        if any(self.decisions[d].get("status") != "decided" for d in tree):
            return "deciding"
        coded = [d for d in tree if self.decisions[d].get("needs_code", True)]
        for d in coded:
            feats = self.dec_features().get(d, [])
            if not feats or any(self.features[f].get("status") != "done" for f in feats):
                return "decided"
        if any(self.validations.get(v, {}).get("status") != "passed" for v in vals):
            return "built"
        return "concluded"

    def item_status(self, item):
        reqs = as_list(item.get("requirements"))
        key = ("item_status", repr(item.get("id"))) + tuple(k for r in reqs for k in req_key(r))
        return self._once(key, lambda: self.compute_item_status(reqs))

    def compute_item_status(self, reqs):
        """The lowest status of an item's requirements (item_status keeps it per load)."""
        sts = [self.req_status(r) for r in reqs]
        return min(sts, key=ORDER.index) if sts else "discovery"

    def missing(self, req):
        """What keeps req from its next status, by the status it has: one dict per blocker."""
        return self._once(("missing",) + req_key(req), lambda: self.compute_missing(req))

    def compute_missing(self, req):
        def entry(kind, text, ident=None, status=None, who=(), awaits=()):
            return {"kind": kind, "id": ident, "status": status, "who": list(who), "awaits": list(awaits), "text": text}
        st = self.req_status(req)
        tree = self.req_tree().get(req.get("id"), [])
        out = []
        if st == "discovery":
            roots = root_ids(req)
            if not roots:
                out.append(entry("decision", "no root decision"))
            elif len(roots) > 1:
                out.append(entry("decision", "%d root decisions; it takes one" % len(roots)))
            elif not tree:
                out.append(entry("decision", "%s is not an active decision" % roots[0], roots[0]))
            if not as_list(req.get("validations")):
                out.append(entry("validation", "no validation"))
        elif st == "deciding":
            for d in tree:
                dec = self.decisions[d]
                if dec.get("status") == "decided":
                    continue
                who = [str(w) for w in as_list(dec.get("discuss_with"))]
                waits = self.spikes_of(d)
                text = "%s is %s" % (d, dec.get("status"))
                if who:
                    text += " (%s)" % ", ".join(who)
                if waits:
                    text += ", awaiting spike %s" % ", ".join(waits)
                out.append(entry("decision", text, d, dec.get("status"), who, waits))
        elif st == "decided":
            seen = []
            for d in tree:
                if not self.decisions[d].get("needs_code", True):
                    continue
                feats = self.dec_features().get(d, [])
                if not feats:
                    out.append(entry("feature", "%s needs code and no feature links it" % d))
                for f in feats:
                    fst = self.features[f].get("status")
                    if fst != "done" and f not in seen:
                        seen.append(f)
                        out.append(entry("feature", "%s is %s" % (f, fst), f, fst))
        elif st == "built":
            for v in as_list(req.get("validations")):
                vst = self.validations.get(v, {}).get("status")
                if vst != "passed":
                    out.append(entry("validation", "%s is %s" % (v, vst), v, vst))
        return out

    # ------------------------------------------------------------ agenda

    def agenda(self):
        """Open or proposed decisions and open pending items, grouped by who they wait on."""
        return self._once(("agenda",), self.compute_agenda)

    def compute_agenda(self):
        agenda = {}
        for d, dec in self.decisions.items():
            if dec.get("status") in ("open", "proposed"):
                for who in as_list(dec.get("discuss_with")) or ["(nobody named)"]:
                    agenda.setdefault(str(who), []).append({
                        "kind": "decision", "id": d, "status": dec["status"], "title": dec.get("title"),
                        "awaits": self.spikes_of(d)})
        for p in open_pending(self.pending):
            for who in as_list(p.get("with")) or ["(nobody named)"]:
                agenda.setdefault(str(who), []).append({
                    "kind": "pending", "id": p.get("id"), "status": "open", "title": p.get("action"),
                    "awaits": []})
        return agenda
