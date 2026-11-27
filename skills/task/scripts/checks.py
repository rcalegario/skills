"""checks.py - the consistency checks of a /task folder: list fields, shapes, references, links,
statuses, the roadmap statuses, the layout and the brief's generated blocks.

Each check reads the status.Task facade it is given and reports through task.fail and task.warnings,
in the order run() calls them, which is the order the report prints. Loaded by status.py by its file
path as `task_checks`; the rules are in ../reference/format.md.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from lib import modules  # noqa: E402
from lib.graph import find_cycle  # noqa: E402
from lib.yamlio import as_list, not_a_list  # noqa: E402

flow_roadmap = modules.load(os.path.join(HERE, "..", "..", "flow", "scripts", "roadmap.py"), "flow_roadmap")
task_model = modules.load(os.path.join(HERE, "model.py"), "task_model")
task_derive = modules.load(os.path.join(HERE, "derive.py"), "task_derive")
task_brief = modules.load(os.path.join(HERE, "brief.py"), "task_brief")

BLOCKS = task_brief.BLOCKS
generated_block, unclosed_block, heading_re = task_brief.generated_block, task_brief.unclosed_block, task_brief.heading_re

DECISION_STATUSES = ("open", "proposed", "decided", "superseded", "dropped")
INACTIVE = task_derive.INACTIVE
OPTION_STATUSES = ("chosen", "recommended", "alternative", "dropped")
VALIDATION_STATUSES = ("pending", "passed", "failed", "dropped")
PENDING_STATUSES = ("open", "done", "dropped")
ORDER = task_derive.ORDER
ITEM_STATUSES = ORDER + ["dropped"]

ID_RE = r"(?:D-\d{2}|V-\d{2}|J-\d{3}|P-\d+|(?:AC|X)-\d+(?:\.\d+)?)"


# Fields written as lists, per kind of entry; a value that is neither a list nor null fails
# (`check_lists`). A requirement's `decision` and a decision's `superseded_by` hold one id.
LIST_FIELDS = {
    "decision": ("born_from", "discuss_with", "context", "options"),
    "validation": ("decides", "attachments", "depends_on"),
    "pending": ("with", "refs"),
    "journal": ("refs",),
    "item": ("requirements",),
    "requirement": ("validations",),
    "readme": ("repos",),
    "story": ("decisions", "validations"),
    "roadmap feature": ("decisions",),
}


root_ids = task_derive.root_ids


def run(task):
    check_lists(task)
    check_shapes(task)
    check_references(task)
    build_tree(task)
    check_links(task)
    check_statuses(task)
    check_layout(task)
    check_brief_blocks(task)


def check_lists(task):
    """A failure for each list field written as a single value."""
    def each(entry, kind, label):
        if not isinstance(entry, dict):
            return
        for field in LIST_FIELDS[kind]:
            value = entry.get(field)
            if not_a_list(value):
                task.fail("%s %s must be a list ([%s])" % (label, field, value))

    for d, dec in task.decisions.items():
        each(dec, "decision", "%s:" % d)
    for v, val in task.validations.items():
        each(val, "validation", "%s:" % v)
    for p in task.pending if isinstance(task.pending, list) else []:
        each(p, "pending", "pending.yaml: %s" % (p.get("id") if isinstance(p, dict) else None))
    for j in task.journal if isinstance(task.journal, list) else []:
        each(j, "journal", "journal.yaml: %s" % (j.get("id") if isinstance(j, dict) else None))
    for item in task.items if isinstance(task.items, list) else []:
        if not isinstance(item, dict):
            continue
        each(item, "item", "acs.yaml: %s" % item.get("id"))
        for req in as_list(item.get("requirements")):
            if isinstance(req, dict):
                each(req, "requirement", "acs.yaml: %s" % req.get("id"))
    each(task.readme(), "readme", "README.md:")
    for name, feat in task.features.items():
        story = task_model.story(feat)
        for field in LIST_FIELDS["story"]:
            if not_a_list(story.get(field)):
                task.fail("%s: story.%s must be a list ([%s])" % (name, field, story.get(field)))
    for rid, feat in task.roadmap.items():
        each(feat, "roadmap feature", "roadmap.yaml: %s" % rid)


def check_brief_blocks(task):
    """Each generated block of brief.md is the one its sources give (format.md, brief.md)."""
    path = task.path("brief.md")
    if not os.path.isfile(path):
        return
    text = task.model.raw(path)
    for name, section, render in BLOCKS:
        stored = generated_block(text, name)
        if unclosed_block(text, name):
            task.fail("brief.md: block %s has no end marker (fix it by hand)" % name)
        elif stored is None:
            if not re.search(heading_re(section), text, re.M):
                task.fail("brief.md: no %s heading to hold the %s block" % (section, name))
            else:
                task.fail("brief.md: no %s block (run `task.py sync`)" % name)
        elif stored != render(task):
            task.fail("brief.md: block %s is stale (run `task.py sync`)" % name)


def check_layout(task):
    """Tasks live in <home>/tasks/<main repo>/<YYYY-MM-DD-HHMM>-<slug>/. A README without `main` is the old layout: warn only."""
    repos = task.repos()
    if not repos:
        return
    mains = [str(r.get("name")) for r in repos if r.get("main")]
    if not mains:
        task.warnings.append("README: no main repo (old layout); mark one repo with `main: true`")
        return
    if len(mains) != 1:
        task.fail("README: exactly one main repo, found %d (%s)" % (len(mains), ", ".join(mains)))
        return
    root = os.path.abspath(task.root)
    folder = os.path.basename(root)
    parent = os.path.basename(os.path.dirname(root))
    if not re.match(r"^\d{4}-\d{2}-\d{2}-\d{4}-[a-z0-9]+(-[a-z0-9]+)*$", folder):
        task.fail("folder %r must be named YYYY-MM-DD-HHMM-<slug>" % folder)
    if parent != mains[0]:
        task.fail("folder sits under %r but the main repo %r must be its parent" % (parent, mains[0]))


def check_shapes(task):
    for d, dec in task.decisions.items():
        if dec.get("status") not in DECISION_STATUSES:
            task.fail("%s: status must be one of %s" % (d, ", ".join(DECISION_STATUSES)))
        for key in ("title", "question"):
            if not str(dec.get(key) or "").strip():
                task.fail("%s: '%s' is required" % (d, key))
        if dec.get("status") in ("decided", "superseded") and not str(dec.get("decision") or "").strip():
            task.fail("%s: status %s needs 'decision'" % (d, dec.get("status")))
        if dec.get("status") == "decided" and not str(dec.get("why") or "").strip():
            task.fail("%s: status decided needs 'why'" % d)
        if dec.get("status") == "decided" and task.spikes_of(d):
            task.fail("%s: decided while spike %s has not passed" % (d, ", ".join(task.spikes_of(d))))
        if dec.get("status") == "superseded" and dec.get("superseded_by") not in task.decisions:
            task.fail("%s: superseded needs 'superseded_by' naming an existing decision" % d)
        for i, opt in enumerate(as_list(dec.get("options"))):
            if not isinstance(opt, dict) or opt.get("status") not in OPTION_STATUSES:
                task.fail("%s: options[%d] status must be one of %s" % (d, i, ", ".join(OPTION_STATUSES)))
    for v, val in task.validations.items():
        if val.get("status") not in VALIDATION_STATUSES:
            task.fail("%s: status must be one of %s" % (v, ", ".join(VALIDATION_STATUSES)))
        if val.get("status") in ("passed", "failed") and not (val.get("date") and str(val.get("evidence") or "").strip()):
            task.fail("%s: status %s needs 'date' and 'evidence'" % (v, val.get("status")))
        for d in as_list(val.get("decides")):
            if d not in task.decisions:
                task.fail("%s: decides %s, which does not exist" % (v, d))
        for att in as_list(val.get("attachments")):
            if not os.path.isfile(task.path("validations", "evidence", str(att))):
                task.fail("%s: attachment %s is not in validations/evidence/" % (v, att))
    ids = [p.get("id") for p in task.pending if isinstance(p, dict)]
    for p in task.pending:
        if not isinstance(p, dict) or not p.get("id"):
            task.fail("pending.yaml: every entry needs an 'id'")
            continue
        if ids.count(p["id"]) > 1:
            task.fail("pending.yaml: id %s is duplicated" % p["id"])
        if p.get("status") not in PENDING_STATUSES:
            task.fail("%s: status must be one of %s" % (p["id"], ", ".join(PENDING_STATUSES)))
        if p.get("status") in ("done", "dropped") and not p.get("closed"):
            task.fail("%s: status %s needs 'closed'" % (p["id"], p.get("status")))
        if not as_list(p.get("with")) or not str(p.get("action") or "").strip():
            task.fail("%s: needs 'with' and 'action'" % p["id"])
    jids = [j.get("id") for j in task.journal if isinstance(j, dict)]
    for jid in sorted({j for j in jids if jids.count(j) > 1}):
        task.fail("journal.yaml: id %s is duplicated" % jid)


def defined_ids(task):
    """(every id the folder defines, the codes of its context files and brief)."""
    ids = set(task.decisions) | set(task.validations)
    ids |= {j.get("id") for j in task.journal if isinstance(j, dict)}
    ids |= {p.get("id") for p in task.pending if isinstance(p, dict)}
    for item in task.items:
        ids.add(item.get("id"))
        ids |= {r.get("id") for r in as_list(item.get("requirements"))}
    codes = set()
    for path in task.model.glob("context", "*.md") + [task.path("brief.md")]:
        if not os.path.isfile(path):
            continue
        text = task.model.text(path)
        fm = task.model.frontmatter(path)
        if fm.get("code"):
            codes.add(str(fm["code"]))
        ids |= set(re.findall(r"^#+ ([A-Z]+-\d+(?:\.\d+)*)\b", text, re.M))
    return ids, codes


def check_references(task):
    defined, codes = defined_ids(task)
    codes = "|".join(sorted(codes))
    pattern = ID_RE if not codes else r"(?:%s|(?:%s)-\d+(?:\.\d+)*)" % (ID_RE, codes)
    id_re = re.compile(r"\b%s\b" % pattern)
    for path in task.text_files():
        rel = os.path.relpath(path, task.root).replace("\\", "/")
        text = task.model.text(path)
        for ref in sorted(set(id_re.findall(text))):
            if ref not in defined:
                task.fail("%s: cites %s, which does not exist" % (rel, ref))
                continue
            reason = obsolete_reason(task, ref) if rel == "brief.md" else None
            if reason:
                task.fail("brief.md: cites %s, %s" % (ref, reason))


def obsolete_reason(task, ref):
    """Why the brief may not cite ref (a decision or item that no longer holds), or None."""
    state = task.decisions.get(ref, {}).get("status")
    if state == "superseded":
        end = task.chain_end(ref)
        if end is None:
            return "which is superseded"
        if task.decisions[end].get("status") == "dropped":
            return "superseded by %s, which is dropped" % end
        return "superseded by %s" % end
    if state == "dropped":
        return "which is dropped"
    for item in task.items:
        if item.get("status") != "dropped":
            continue
        if item.get("id") == ref:
            return "which is dropped"
        if ref in {r.get("id") for r in as_list(item.get("requirements")) if isinstance(r, dict)}:
            return "whose item %s is dropped" % item.get("id")
    return None


def build_tree(task):
    task.children = task.derived.children()


def check_links(task):
    in_tree = set()
    proven = set()
    for item in task.active_items():
        reqs = as_list(item.get("requirements"))
        if not reqs:
            task.fail("%s: has no requirements" % item.get("id"))
        for req in reqs:
            rid = req.get("id")
            roots = root_ids(req)
            if not roots:
                task.fail("%s: requirement without a decision" % rid)
            elif len(roots) > 1:
                task.fail("%s: requirement with %d decisions (%s); it takes one root" % (rid, len(roots), ", ".join(roots)))
            if not as_list(req.get("validations")):
                task.fail("%s: requirement without a validation" % rid)
            for v in as_list(req.get("validations")):
                if as_list(task.validations.get(v, {}).get("decides")):
                    task.fail("%s: lists spike %s; a spike decides, it proves no requirement" % (rid, v))
            tree = []
            for r in roots:
                if r not in task.decisions:
                    continue
                if task.decisions[r].get("status") in INACTIVE:
                    task.fail("%s: points to %s, which is %s" % (rid, r, task.decisions[r]["status"]))
                tree += [x for x in task.derived.tree(r) if x not in tree]
            in_tree |= set(tree)
            proven |= set(as_list(req.get("validations")))
    for d, dec in task.decisions.items():
        if dec.get("status") not in INACTIVE and d not in in_tree:
            task.fail("%s: orphan (not in the tree of any requirement)" % d)
    for v, val in task.validations.items():
        if v not in proven and val.get("status") != "dropped" and not as_list(val.get("decides")):
            task.warnings.append("%s: proves no requirement" % v)
    task.req_tree = task.derived.req_tree()
    task.dec_features = task.derived.dec_features()
    repos = task.repo_names()
    for name, feat in task.features.items():
        if repos is not None and feat.get("repo") not in repos:
            task.fail("feature %s: repo %r is not in the README repos (%s)" % (
                name, feat.get("repo"), ", ".join(sorted(repos)) or "none"))
        story = task_model.story(feat)
        for d in as_list(story.get("decisions")):
            if d not in task.decisions:
                continue
            if task.decisions[d].get("status") in INACTIVE:
                task.fail("feature %s: links %s, which is %s" % (name, d, task.decisions[d]["status"]))
    if os.path.isfile(task.path(".specs", "roadmap.yaml")):
        for d, dec in task.decisions.items():
            if dec.get("status") == "decided" and dec.get("needs_code", True) and not task.dec_features[d]:
                task.warnings.append("%s: decided and needs code, but no feature links it" % d)
    # find_cycle skips an edge from a node to itself; a decision born from itself is a cycle here.
    itself = next((d for d, kids in task.children.items() if d in kids), None)
    cycle = [itself, itself] if itself else find_cycle(task.children)
    if cycle:
        task.fail("cycle in born_from: " + " -> ".join(cycle))


def check_statuses(task):
    """The status written in acs.yaml and roadmap.yaml is the one the rest of the folder implies."""
    sync = "run `task.py sync`"
    for item in task.items:
        if item.get("status") is not None and item.get("status") not in ITEM_STATUSES:
            task.fail("%s: status must be one of %s" % (item.get("id"), ", ".join(ITEM_STATUSES)))
    for item in task.active_items():
        rows = [(item.get("id"), item, task.item_status(item), "its requirements")]
        rows += [(r.get("id"), r, task.req_status(r), "the decisions, features and validations")
                 for r in as_list(item.get("requirements"))]
        for ident, entity, computed, source in rows:
            stored = entity.get("status")
            if stored is None:
                task.fail("%s: no status (%s)" % (ident, sync))
            elif stored not in ORDER:
                task.fail("%s: status must be one of %s" % (ident, ", ".join(ORDER)))
            elif stored != computed:
                task.fail("%s: status is %s but %s say %s (%s)" % (ident, stored, source, computed, sync))
    check_roadmap_statuses(task, sync)


def check_roadmap_statuses(task, sync):
    data = task.model.load(task.path(".specs", "roadmap.yaml"), {}) or {}
    if not isinstance(data, dict):
        return
    linked = flow_roadmap.linked_statuses(flow_roadmap.links_of(task.features))
    linked = {rid: state for rid, state in linked.items() if state}  # a feature with no status counts as unlinked
    for ms, features, computed in flow_roadmap.statuses(data, linked):
        for feat, state in features:
            compare_roadmap(task, feat["id"], feat.get("status"), state, sync)
        if computed is not None:
            compare_roadmap(task, ms.get("id"), ms.get("status"), computed, sync)


def compare_roadmap(task, ident, stored, computed, sync):
    if stored is None:
        task.fail("%s: no roadmap status (%s)" % (ident, sync))
    elif stored != computed:
        task.fail("%s: roadmap status is %s but the features say %s (%s)" % (ident, stored, computed, sync))
