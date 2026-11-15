#!/usr/bin/env python3
"""status.py - status and consistency checks for a /task folder.

Usage:
    python status.py [task-dir]                 print status, agenda, open pending items and problems
    python status.py [task-dir] --gate plan     also fail when a decision in an active tree is still open
    python status.py [task-dir] --gate spec --feature F   fail when feature F links a decision still open or awaiting a spike
    python status.py [task-dir] --gate pr       also fail when an item is neither concluded nor carries a pr_note
    python status.py [task-dir] --pr-notes      print the pr_note of every item and active decision, then exit
    python status.py [task-dir] --find ID       print <file>:<line> of each place ID is defined, without the checks

Exits 1 when it finds a failure. The folder layout is in ../reference/format.md.
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "flow", "scripts"))

try:
    import yaml
except ImportError:
    sys.stderr.write("status.py needs PyYAML (pip install pyyaml).\n")
    sys.exit(2)

import flow  # noqa: E402  (the milestone status rule is /flow's)

DECISION_STATUSES = ("open", "proposed", "decided", "superseded", "dropped")
INACTIVE = {"superseded", "dropped"}
OPTION_STATUSES = ("chosen", "recommended", "alternative", "dropped")
VALIDATION_STATUSES = ("pending", "passed", "failed", "dropped")
SPIKE_BLOCKING = ("pending", "failed")  # a spike unblocks its decisions once passed or dropped
PENDING_STATUSES = ("open", "done", "dropped")
ORDER = ["discovery", "deciding", "decided", "built", "concluded"]
ITEM_STATUSES = ORDER + ["dropped"]

ID_RE = r"(?:D-\d{2}|V-\d{2}|J-\d{3}|P-\d+|(?:AC|X)-\d+(?:\.\d+)?)"


def lst(value):
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def load_yaml(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise SystemExit("%s is not valid YAML: %s" % (path, exc))
    return default if data is None else data


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}, text


class Task:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.failures, self.warnings = [], []
        self.items = load_yaml(self.path("acs.yaml"), []) or []
        self.journal = load_yaml(self.path("journal.yaml"), []) or []
        self.pending = load_yaml(self.path("pending.yaml"), []) or []
        self.decisions = self.load_dir("decisions", "D")
        self.validations = self.load_dir("validations", "V")
        self.features = self.load_features()
        self.roadmap = self.load_roadmap()

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def fail(self, msg):
        if msg not in self.failures:
            self.failures.append(msg)

    def load_dir(self, sub, prefix):
        found = {}
        for path in sorted(glob.glob(self.path(sub, "%s-*.yaml" % prefix))):
            data = load_yaml(path, {})
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
        found = {}
        for path in sorted(glob.glob(self.path(".specs", "features", "*", "feature.yaml"))):
            data = load_yaml(path, {})
            if isinstance(data, dict):
                found[os.path.basename(os.path.dirname(path))] = data
        return found

    def load_roadmap(self):
        """Roadmap features by id, from .specs/roadmap.yaml."""
        data = load_yaml(self.path(".specs", "roadmap.yaml"), {}) or {}
        found = {}
        for ms in lst(data.get("milestones") if isinstance(data, dict) else None):
            for feat in lst(ms.get("features") if isinstance(ms, dict) else None):
                if isinstance(feat, dict) and feat.get("id"):
                    found[str(feat["id"])] = feat
        return found

    # ------------------------------------------------------------ spikes

    def spikes_of(self, d):
        """Spikes (validations with 'decides') naming decision d that still block it."""
        return [v for v, val in self.validations.items()
                if d in lst(val.get("decides")) and val.get("status") in SPIKE_BLOCKING]

    # ------------------------------------------------------------ checks

    def check(self):
        self.check_shapes()
        self.check_references()
        self.build_tree()
        self.check_links()
        self.check_statuses()
        self.check_layout()

    def check_layout(self):
        """Tasks live in <home>/tasks/<main repo>/<YYYY-MM-DD-HHMM>-<slug>/. A README without `main` is the old layout: warn only."""
        path = self.path("README.md")
        if not os.path.isfile(path):
            return
        fm, _ = frontmatter(path)
        repos = [r for r in lst(fm.get("repos")) if isinstance(r, dict)]
        if not repos:
            return
        mains = [str(r.get("name")) for r in repos if r.get("main")]
        if not mains:
            self.warnings.append("README: no main repo (old layout); mark one repo with `main: true`")
            return
        if len(mains) != 1:
            self.fail("README: exactly one main repo, found %d (%s)" % (len(mains), ", ".join(mains)))
            return
        root = os.path.abspath(self.root)
        folder = os.path.basename(root)
        parent = os.path.basename(os.path.dirname(root))
        if not re.match(r"^\d{4}-\d{2}-\d{2}-\d{4}-[a-z0-9]+(-[a-z0-9]+)*$", folder):
            self.fail("folder %r must be named YYYY-MM-DD-HHMM-<slug>" % folder)
        if parent != mains[0]:
            self.fail("folder sits under %r but the main repo %r must be its parent" % (parent, mains[0]))

    def check_shapes(self):
        for d, dec in self.decisions.items():
            if dec.get("status") not in DECISION_STATUSES:
                self.fail("%s: status must be one of %s" % (d, ", ".join(DECISION_STATUSES)))
            for key in ("title", "question"):
                if not str(dec.get(key) or "").strip():
                    self.fail("%s: '%s' is required" % (d, key))
            if dec.get("status") in ("decided", "superseded") and not str(dec.get("decision") or "").strip():
                self.fail("%s: status %s needs 'decision'" % (d, dec.get("status")))
            if dec.get("status") == "decided" and not str(dec.get("why") or "").strip():
                self.fail("%s: status decided needs 'why'" % d)
            if dec.get("status") == "decided" and self.spikes_of(d):
                self.fail("%s: decided while spike %s has not passed" % (d, ", ".join(self.spikes_of(d))))
            if dec.get("status") == "superseded" and dec.get("superseded_by") not in self.decisions:
                self.fail("%s: superseded needs 'superseded_by' naming an existing decision" % d)
            for i, opt in enumerate(lst(dec.get("options"))):
                if not isinstance(opt, dict) or opt.get("status") not in OPTION_STATUSES:
                    self.fail("%s: options[%d] status must be one of %s" % (d, i, ", ".join(OPTION_STATUSES)))
        for v, val in self.validations.items():
            if val.get("status") not in VALIDATION_STATUSES:
                self.fail("%s: status must be one of %s" % (v, ", ".join(VALIDATION_STATUSES)))
            if val.get("status") in ("passed", "failed") and not (val.get("date") and str(val.get("evidence") or "").strip()):
                self.fail("%s: status %s needs 'date' and 'evidence'" % (v, val.get("status")))
            for d in lst(val.get("decides")):
                if d not in self.decisions:
                    self.fail("%s: decides %s, which does not exist" % (v, d))
            for att in lst(val.get("attachments")):
                if not os.path.isfile(self.path("validations", "evidence", str(att))):
                    self.fail("%s: attachment %s is not in validations/evidence/" % (v, att))
        ids = [p.get("id") for p in self.pending if isinstance(p, dict)]
        for p in self.pending:
            if not isinstance(p, dict) or not p.get("id"):
                self.fail("pending.yaml: every entry needs an 'id'")
                continue
            if ids.count(p["id"]) > 1:
                self.fail("pending.yaml: id %s is duplicated" % p["id"])
            if p.get("status") not in PENDING_STATUSES:
                self.fail("%s: status must be one of %s" % (p["id"], ", ".join(PENDING_STATUSES)))
            if p.get("status") in ("done", "dropped") and not p.get("closed"):
                self.fail("%s: status %s needs 'closed'" % (p["id"], p.get("status")))
            if not lst(p.get("with")) or not str(p.get("action") or "").strip():
                self.fail("%s: needs 'with' and 'action'" % p["id"])
        jids = [j.get("id") for j in self.journal if isinstance(j, dict)]
        for jid in sorted({j for j in jids if jids.count(j) > 1}):
            self.fail("journal.yaml: id %s is duplicated" % jid)

    def defined_ids(self):
        ids = set(self.decisions) | set(self.validations)
        ids |= {j.get("id") for j in self.journal if isinstance(j, dict)}
        ids |= {p.get("id") for p in self.pending if isinstance(p, dict)}
        for item in self.items:
            ids.add(item.get("id"))
            ids |= {r.get("id") for r in lst(item.get("requirements"))}
        self.codes = set()
        for path in glob.glob(self.path("context", "*.md")) + [self.path("brief.md")]:
            if not os.path.isfile(path):
                continue
            fm, text = frontmatter(path)
            if fm.get("code"):
                self.codes.add(str(fm["code"]))
            ids |= set(re.findall(r"^#+ ([A-Z]+-\d+(?:\.\d+)*)\b", text, re.M))
        return ids

    def check_references(self):
        defined = self.defined_ids()
        codes = "|".join(sorted(self.codes))
        pattern = ID_RE if not codes else r"(?:%s|(?:%s)-\d+(?:\.\d+)*)" % (ID_RE, codes)
        id_re = re.compile(r"\b%s\b" % pattern)
        for path in self.text_files():
            rel = os.path.relpath(path, self.root).replace("\\", "/")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for ref in sorted(set(id_re.findall(text))):
                if ref not in defined:
                    self.fail("%s: cites %s, which does not exist" % (rel, ref))

    SKIP = {"repos", ".git", os.path.join("context", "archive"), os.path.join("validations", "evidence")}

    def text_files(self):
        """Every .md and .yaml file of the task, without walking worktrees, git or archives."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel = os.path.relpath(dirpath, self.root)
            dirnames[:] = [d for d in dirnames if os.path.normpath(os.path.join(rel, d)) not in self.SKIP]
            for name in filenames:
                if name.endswith((".md", ".yaml")):
                    yield os.path.join(dirpath, name)

    def build_tree(self):
        self.children = {d: [] for d in self.decisions}
        for d, dec in self.decisions.items():
            if dec.get("status") in INACTIVE:
                continue
            for parent in lst(dec.get("born_from")):
                if parent in self.children:
                    self.children[parent].append(d)

    def tree(self, d, path=()):
        """d and all its active children, recursively."""
        if d in path:
            self.fail("cycle in born_from: " + " -> ".join(path + (d,)))
            return []
        out = [d]
        for child in self.children.get(d, []):
            out += [x for x in self.tree(child, path + (d,)) if x not in out]
        return out

    def active_items(self):
        return [i for i in self.items if i.get("status") != "dropped"]

    def check_links(self):
        self.req_tree = {}
        in_tree = set()
        proven = set()
        for item in self.active_items():
            reqs = lst(item.get("requirements"))
            if not reqs:
                self.fail("%s: has no requirements" % item.get("id"))
            for req in reqs:
                rid = req.get("id")
                roots = lst(req.get("decision"))
                if not roots:
                    self.fail("%s: requirement without a decision" % rid)
                elif len(roots) > 1:
                    self.fail("%s: requirement with %d decisions (%s); it takes one root" % (rid, len(roots), ", ".join(roots)))
                if not lst(req.get("validations")):
                    self.fail("%s: requirement without a validation" % rid)
                for v in lst(req.get("validations")):
                    if lst(self.validations.get(v, {}).get("decides")):
                        self.fail("%s: lists spike %s; a spike decides, it proves no requirement" % (rid, v))
                tree = []
                for r in roots:
                    if r not in self.decisions:
                        continue
                    if self.decisions[r].get("status") in INACTIVE:
                        self.fail("%s: points to %s, which is %s" % (rid, r, self.decisions[r]["status"]))
                    tree += [x for x in self.tree(r) if x not in tree]
                self.req_tree[rid] = tree
                in_tree |= set(tree)
                proven |= set(lst(req.get("validations")))
        for d, dec in self.decisions.items():
            if dec.get("status") not in INACTIVE and d not in in_tree:
                self.fail("%s: orphan (not in the tree of any requirement)" % d)
        for v, val in self.validations.items():
            if v not in proven and val.get("status") != "dropped" and not lst(val.get("decides")):
                self.warnings.append("%s: proves no requirement" % v)
        self.dec_features = {d: [] for d in self.decisions}
        repos = self.repo_names()
        for name, feat in self.features.items():
            if repos is not None and feat.get("repo") not in repos:
                self.fail("feature %s: repo %r is not in the README repos (%s)" % (
                    name, feat.get("repo"), ", ".join(sorted(repos)) or "none"))
            story = feat.get("story") if isinstance(feat.get("story"), dict) else {}
            for d in lst(story.get("decisions")):
                if d not in self.decisions:
                    continue
                self.dec_features[d].append(name)
                if self.decisions[d].get("status") in INACTIVE:
                    self.fail("feature %s: links %s, which is %s" % (name, d, self.decisions[d]["status"]))
        if os.path.isfile(self.path(".specs", "roadmap.yaml")):
            for d, dec in self.decisions.items():
                if dec.get("status") == "decided" and dec.get("needs_code", True) and not self.dec_features[d]:
                    self.warnings.append("%s: decided and needs code, but no feature links it" % d)

    def check_statuses(self):
        """The status written in acs.yaml and roadmap.yaml is the one the rest of the folder implies."""
        sync = "run `task.py sync`"
        for item in self.items:
            if item.get("status") is not None and item.get("status") not in ITEM_STATUSES:
                self.fail("%s: status must be one of %s" % (item.get("id"), ", ".join(ITEM_STATUSES)))
        for item in self.active_items():
            rows = [(item.get("id"), item, self.item_status(item), "its requirements")]
            rows += [(r.get("id"), r, self.req_status(r), "the decisions, features and validations")
                     for r in lst(item.get("requirements"))]
            for ident, entity, computed, source in rows:
                stored = entity.get("status")
                if stored is None:
                    self.fail("%s: no status (%s)" % (ident, sync))
                elif stored not in ORDER:
                    self.fail("%s: status must be one of %s" % (ident, ", ".join(ORDER)))
                elif stored != computed:
                    self.fail("%s: status is %s but %s say %s (%s)" % (ident, stored, source, computed, sync))
        self.check_roadmap_statuses(sync)

    def check_roadmap_statuses(self, sync):
        data = load_yaml(self.path(".specs", "roadmap.yaml"), {}) or {}
        if not isinstance(data, dict):
            return
        linked = {}
        for feat in self.features.values():
            if feat.get("roadmap") is not None:
                linked.setdefault(str(feat["roadmap"]), feat.get("status"))
        for ms in lst(data.get("milestones")):
            if not isinstance(ms, dict):
                continue
            states = []
            for feat in lst(ms.get("features")):
                if not isinstance(feat, dict) or feat.get("id") is None:
                    continue
                computed = linked.get(str(feat["id"])) or "planned"
                states.append(computed)
                self.compare_roadmap(feat["id"], feat.get("status"), computed, sync)
            if states:
                self.compare_roadmap(ms.get("id"), ms.get("status"), flow.milestone_status(states), sync)

    def compare_roadmap(self, ident, stored, computed, sync):
        if stored is None:
            self.fail("%s: no roadmap status (%s)" % (ident, sync))
        elif stored != computed:
            self.fail("%s: roadmap status is %s but the features say %s (%s)" % (ident, stored, computed, sync))

    def repo_names(self):
        """Repo names from the README header, or None when the README has no repos list."""
        path = self.path("README.md")
        if not os.path.isfile(path):
            return None
        fm, _ = frontmatter(path)
        if not isinstance(fm.get("repos"), list):
            return None
        return {str(r.get("name")) for r in fm["repos"] if isinstance(r, dict)}

    # ------------------------------------------------------------ status

    def req_status(self, req):
        tree = self.req_tree.get(req.get("id"), [])
        vals = lst(req.get("validations"))
        if len(lst(req.get("decision"))) != 1 or not vals or not tree:
            return "discovery"
        if any(self.decisions[d].get("status") != "decided" for d in tree):
            return "deciding"
        coded = [d for d in tree if self.decisions[d].get("needs_code", True)]
        for d in coded:
            feats = self.dec_features.get(d, [])
            if not feats or any(self.features[f].get("status") != "done" for f in feats):
                return "decided"
        if any(self.validations.get(v, {}).get("status") != "passed" for v in vals):
            return "built"
        return "concluded"

    def item_status(self, item):
        sts = [self.req_status(r) for r in lst(item.get("requirements"))]
        return min(sts, key=ORDER.index) if sts else "discovery"

    def report(self):
        out = []
        out.append("# Items\n")
        out.append("| Item | Status | Requirements | Decisions decided | Validations passed |")
        out.append("|---|---|---|---|---|")
        req_lines = []
        for item in self.active_items():
            ds, vs = set(), set()
            for req in lst(item.get("requirements")):
                tree = self.req_tree.get(req.get("id"), [])
                ds |= set(tree)
                vs |= set(lst(req.get("validations")))
                roots = lst(req.get("decision"))
                waiting = ["%s (%s)" % (d, self.decisions[d].get("status")) for d in tree
                           if self.decisions[d].get("status") != "decided"]
                children = [d for d in tree if d not in roots]
                vtxt = ", ".join("%s (%s)" % (v, self.validations.get(v, {}).get("status", "?"))
                                 for v in lst(req.get("validations")))
                req_lines.append("| %s | %s | %s | %s | %s | %s |" % (
                    req.get("id"), self.req_status(req), ", ".join(roots) or "-",
                    ", ".join(children) or "-", ", ".join(waiting) or "-", vtxt or "-"))
            n_dec = sum(1 for d in ds if self.decisions[d].get("status") == "decided")
            n_val = sum(1 for v in vs if self.validations.get(v, {}).get("status") == "passed")
            out.append("| %s | %s | %d | %d/%d | %d/%d |" % (
                item.get("id"), self.item_status(item), len(lst(item.get("requirements"))),
                n_dec, len(ds), n_val, len(vs)))
        out.append("\n# Requirements\n")
        out.append("| Requirement | Status | Root | Children | Not decided | Validations |")
        out.append("|---|---|---|---|---|---|")
        out += req_lines
        if self.features:
            out.append("\n# Features\n")
            out.append("| Feature | Status | Decisions | Validations |")
            out.append("|---|---|---|---|")
            for name, feat in self.features.items():
                story = feat.get("story") if isinstance(feat.get("story"), dict) else {}
                out.append("| %s | %s | %s | %s |" % (name, feat.get("status"),
                                                     ", ".join(lst(story.get("decisions"))) or "-",
                                                     ", ".join(lst(story.get("validations"))) or "-"))
        spikes = [(v, val) for v, val in self.validations.items()
                  if lst(val.get("decides")) and val.get("status") in SPIKE_BLOCKING]
        if spikes:
            out.append("\n# Spikes\n")
            out.append("| Spike | Status | Where | Decides | Blocks features |")
            out.append("|---|---|---|---|---|")
            for v, val in spikes:
                blocked = sorted({f for d in lst(val.get("decides")) for f in self.features_of(d)})
                out.append("| %s | %s | %s | %s | %s |" % (
                    v, val.get("status"), val.get("where") or "-",
                    ", ".join(lst(val.get("decides"))), ", ".join(blocked) or "-"))
        agenda = {}
        for d, dec in self.decisions.items():
            if dec.get("status") in ("open", "proposed"):
                waits = self.spikes_of(d)
                suffix = " - awaiting spike %s" % ", ".join(waits) if waits else ""
                for who in lst(dec.get("discuss_with")) or ["(nobody named)"]:
                    agenda.setdefault(str(who), []).append("%s (%s) %s%s" % (d, dec["status"], dec.get("title"), suffix))
        for p in self.pending:
            if isinstance(p, dict) and p.get("status") == "open":
                for who in lst(p.get("with")):
                    agenda.setdefault(str(who), []).append("%s (pending) %s" % (p.get("id"), p.get("action")))
        if agenda:
            out.append("\n# Agenda\n")
            for who in sorted(agenda):
                out.append("**%s**" % who)
                out += ["- %s" % line for line in agenda[who]]
                out.append("")
        return "\n".join(out)

    # ------------------------------------------------------------ gates

    def matches(self, fid, name):
        """True when feature id fid (e.g. F1.1) names roadmap id or feature folder name (e.g. F1.1-template)."""
        return fid == name or name.startswith(fid + "-") or fid.startswith(name + "-")

    def feature_decisions(self, fid):
        """Decisions linked to feature fid: its roadmap entry's 'decisions' and its feature.yaml story."""
        found = []
        for rid, feat in self.roadmap.items():
            if self.matches(fid, rid):
                found += lst(feat.get("decisions"))
        for name, feat in self.features.items():
            if self.matches(fid, name):
                story = feat.get("story") if isinstance(feat.get("story"), dict) else {}
                found += lst(story.get("decisions"))
        return [d for i, d in enumerate(found) if d not in found[:i]]

    def features_of(self, d):
        """Roadmap and spec'd features that link decision d."""
        out = {rid for rid, feat in self.roadmap.items() if d in lst(feat.get("decisions"))}
        return out | set(self.dec_features.get(d, []))

    def gate(self, name, feature=None):
        if name == "spec":
            if not any(self.matches(feature, n) for n in list(self.roadmap) + list(self.features)):
                self.fail("gate spec: feature %s is neither in the roadmap nor in .specs/features" % feature)
            for d in self.feature_decisions(feature):
                dec = self.decisions.get(d)
                if dec is None:
                    continue
                waits = self.spikes_of(d)
                if waits:
                    self.fail("gate spec: %s waits for spike %s, which decides %s" % (feature, ", ".join(waits), d))
                elif dec.get("status") == "open":
                    self.fail("gate spec: %s links %s, which is open" % (feature, d))
                elif dec.get("status") == "proposed":
                    self.warnings.append("gate spec: %s links %s, which is proposed" % (feature, d))
            return
        if name == "plan":
            for item in self.active_items():
                for req in lst(item.get("requirements")):
                    for d in self.req_tree.get(req.get("id"), []):
                        st = self.decisions[d].get("status")
                        if st == "open":
                            self.fail("gate plan: %s is open (tree of %s)" % (d, req.get("id")))
                        elif st == "proposed":
                            self.warnings.append("gate plan: %s is proposed; list it in BRIEF-4" % d)
        elif name == "pr":
            for item in self.active_items():
                st = self.item_status(item)
                if st != "concluded" and not str(item.get("pr_note") or "").strip():
                    self.fail("gate pr: %s is %s and has no pr_note" % (item.get("id"), st))
            for p in self.pending:
                if isinstance(p, dict) and p.get("status") == "open":
                    self.warnings.append("gate pr: %s is still open" % p.get("id"))

    def pr_notes(self):
        out = []
        for item in self.active_items():
            if str(item.get("pr_note") or "").strip():
                out.append("## %s (%s)\n\n%s" % (item.get("id"), self.item_status(item), item["pr_note"].strip()))
        for d, dec in self.decisions.items():
            if dec.get("status") not in INACTIVE and str(dec.get("pr_note") or "").strip():
                out.append("## %s %s\n\n%s" % (d, dec.get("title"), dec["pr_note"].strip()))
        vals = ["- %s %s: %s" % (v, val.get("title"), val.get("status")) for v, val in self.validations.items()
                if val.get("status") != "dropped"]
        if vals:
            out.append("## Validations\n\n" + "\n".join(vals))
        return "\n\n".join(out)

    def find(self, ident):
        """Each place ident is defined, as <file>:<line>: a YAML `id:` line or a Markdown heading."""
        defined = re.compile(r"""^\s*(?:-\s+)?id:\s*["']?%s["']?\s*$|^#+\s+%s(?![\w.-])""" % (re.escape(ident), re.escape(ident)))
        hits = []
        for path in sorted(self.text_files()):
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    if defined.match(line):
                        hits.append("%s:%d" % (os.path.relpath(path, self.root).replace("\\", "/"), n))
        return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="?", default=".")
    ap.add_argument("--gate", choices=("plan", "spec", "pr"))
    ap.add_argument("--feature", help="with --gate spec: the feature id (e.g. F1.1)")
    ap.add_argument("--pr-notes", action="store_true")
    ap.add_argument("--find", metavar="ID", help="print <file>:<line> where ID is defined, and skip the checks")
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
