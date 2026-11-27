"""step.py - the /task step to take next, and who it waits on.

step() reads the status.Task facade it is given after its checks ran, and returns the first bar not
met in the order of ../reference/format.md, Step. unproven() is the one rule for an item the PR may
not leave silent: the review step and the pr gate (gates.py) both read it. Loaded by status.py by
its file path as `task_step`.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

from lib import modules  # noqa: E402
from lib.yamlio import as_list  # noqa: E402

task_brief = modules.load(os.path.join(HERE, "brief.py"), "task_brief")
task_derive = modules.load(os.path.join(HERE, "derive.py"), "task_derive")

# Steps whose next action is always the user's, whoever its blockers wait on (format.md, Step).
ALWAYS_YOURS = ("consolidate", "plan", "build", "pr", "finish")


def pr_note(entry):
    """The pr_note of an item or decision, stripped; "" when it has none."""
    return str(entry.get("pr_note") or "").strip()


def unproven(task):
    """(item, status) of each active item neither concluded nor carrying a pr_note."""
    out = []
    for item in task.active_items():
        state = task.item_status(item)
        if state != "concluded" and not pr_note(item):
            out.append((item, state))
    return out


def open_refs(task):
    """The ids in the refs of the open pending items."""
    return {str(r) for p in task_derive.open_pending(task.pending) for r in as_list(p.get("refs"))}


def waits(task, ident, in_pending):
    """Whether the entity ident waits on someone else: it is in the refs of an open pending item
    (in_pending), or it is a proposed decision whose discuss_with names only others than me."""
    if ident in in_pending:
        return True
    dec = task.decisions.get(ident)
    if isinstance(dec, dict) and dec.get("status") == "proposed":
        who = [str(w) for w in as_list(dec.get("discuss_with"))]
        return bool(who) and "me" not in who
    return False


def item_waits(task, ident, in_pending):
    """Whether everything missing() lists for the requirements of item ident waits on someone else."""
    item = next((i for i in task.active_items() if i.get("id") == ident), {})
    entries = [m for req in as_list(item.get("requirements")) for m in task.missing(req)]
    return bool(entries) and all(m["id"] is not None and waits(task, str(m["id"]), in_pending) for m in entries)


def step(task):
    """The /task step to take next: the first bar not met, in the order of format.md, Step.

    Besides the reason the CLI prints, it returns the entities holding the step as data
    (blockers: {id, kind, state, waiting}) and whether the next action is the user's (your_turn);
    the reason is worded from the same blockers, so the two cannot disagree."""
    in_pending = open_refs(task)

    def blocker(ident, kind, state):
        waiting = waits(task, ident, in_pending) or (kind == "item" and item_waits(task, ident, in_pending))
        return {"id": ident, "kind": kind, "state": state, "waiting": waiting}

    def at(name, blockers, reason):
        turn = (bool(task.failures) or name in ALWAYS_YOURS
                or (name != "done" and any(not b["waiting"] for b in blockers)))
        return {"step": name, "reason": reason, "blockers": blockers, "your_turn": turn}

    def each(blockers, template):
        """One phrase per blocker, template filled with its id and state, joined by commas."""
        return ", ".join(template % (b["id"], b["state"]) for b in blockers)

    undecided = [blocker(d, "decision", dec.get("status")) for d, dec in task.decisions.items()
                 if dec.get("status") in ("open", "proposed") and not task.spikes_of(d) and d not in in_pending]
    if undecided:
        return at("decide", undecided, each(undecided, "%s is %s"))

    if not os.path.isfile(task.path("brief.md")):
        return at("consolidate", [blocker("brief.md", "brief", "missing")], "no brief.md")
    stamped = task.model.frontmatter(task.path("brief.md"))
    brief_date = stamped.get("date")
    if not brief_date or not re.match(r"\d{4}-\d{2}-\d{2}$", str(brief_date)):
        return at("consolidate", [blocker("brief.md", "brief", "no-date")], "brief.md has no date")
    sources = stamped.get("sources")
    if not isinstance(sources, dict) or not sources:
        return at("consolidate", [blocker("brief.md", "brief", "no-sources")], "brief.md has no sources")
    current = task_brief.sources_digest(task.model)
    changed = [blocker(g, "source", "changed") for g in task_brief.SOURCE_GROUPS if str(sources.get(g)) != current[g]]
    if changed:
        return at("consolidate", changed, "%s changed after brief.md" % ", ".join(b["id"] for b in changed))

    if not os.path.isfile(task.path(".specs", "roadmap.yaml")):
        return at("plan", [blocker("roadmap.yaml", "roadmap", "missing")], "no .specs/roadmap.yaml")

    feature_status = {rid: f.get("status") for rid, f in task.roadmap.items()}
    feature_status.update({name: f.get("status") for name, f in task.features.items()})
    spikes, blocked = [], []
    for v, val in task.blocking_spikes():
        feats = [f for f in task.blocked_features(val) if feature_status.get(f) != "done"]
        if feats:
            spikes.append(blocker(v, "spike", val.get("status")))
            blocked.append("%s blocks %s" % (v, ", ".join(feats)))
    if spikes:
        return at("spike", spikes, "; ".join(blocked))

    linked = {str(f.get("roadmap")) for f in task.features.values() if f.get("roadmap") is not None}
    building = [blocker(name, "feature", f.get("status")) for name, f in task.features.items()
                if f.get("status") != "done"]
    building += [blocker(rid, "feature", f.get("status") or "planned") for rid, f in task.roadmap.items()
                 if rid not in linked and f.get("status") != "done"]
    if building:
        return at("build", building, each(building, "%s is %s"))

    held = [blocker(item.get("id"), "item", state) for item, state in unproven(task)]
    if held:
        return at("review", held, each(held, "%s is %s and has no pr_note"))

    repos = task.repos()
    worktrees = [blocker(str(r.get("name")), "repo", "worktree") for r in repos if r.get("worktree")]
    if repos and not worktrees:
        return at("done", [], "no repo has a worktree")

    no_pr = [blocker(name, "feature", "no-pr") for name, f in task.features.items() if not f.get("pr")]
    if no_pr:
        return at("pr", no_pr, "%s has no PR" % ", ".join(b["id"] for b in no_pr))
    return at("finish", worktrees, "every feature has a PR; worktrees remain: %s"
              % (", ".join(b["id"] for b in worktrees) or "none listed"))
