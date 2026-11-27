"""summary.py - status.py's output shortened: the step's reason for one task row; for the task page, its next
actions and its checks grouped by kind.

status.py gives each step's blockers as data ({id, kind, state, waiting}); this groups them by kind and state
into one phrase per group ("2 decisions open (D-01, D-04)", "F1.1 in review"), joined in the order status.py gave
them. The full reason stays for the hover. A blocker this page cannot word shows status.py's reason as is.
"""
import collections
import re

# How one kind of blocker reads:
#   plural   the noun of a group ("2 decisions open")
#   one      one blocker, from its id and the words of its state
#   by_state whether blockers of different states form different groups
#   words    the words of each state, where they differ from the state itself
#   fixed    the words of every state, for a kind whose state does not matter
Kind = collections.namedtuple("Kind", "plural one by_state words fixed", defaults=({}, None))
KINDS = {
    "decision": Kind("decisions", "{id} {words}", True),
    "spike": Kind("spikes", "spike {id} {words}", True),
    "feature": Kind("features", "{id} {words}", True, {"review": "in review", "no-pr": "without PR"}),
    "item": Kind("items", "{id} {words}", False, fixed="without pr_note"),
    "repo": Kind("worktrees", "worktree {id} {words}", False, fixed="left"),
}
BRIEF = {"missing": "no brief", "no-date": "brief has no date", "no-sources": "brief has no sources"}
MAX_IDS = 3


def short_id(ident, kind):
    """A feature reads by its roadmap id: F1.1-vm-ssh-key is F1.1."""
    match = re.match(r"(F\d+(?:\.\d+)*)-", ident) if kind == "feature" else None
    return match.group(1) if match else ident


def ids_text(ids):
    return ", ".join(ids) if len(ids) <= MAX_IDS else "%s–%s" % (ids[0], ids[-1])


def phrase(kind, state, ids):
    words = kind.fixed or kind.words.get(state, state)
    if len(ids) == 1:
        return kind.one.format(id=ids[0], words=words)
    return "%d %s %s (%s)" % (len(ids), kind.plural, words, ids_text(ids))


def grouped(blockers):
    """One phrase per group of blockers, or None when one cannot be worded (an unknown kind, a missing state)."""
    groups = {}
    for b in blockers:
        kind = KINDS.get(b.get("kind"))
        if kind is None or (kind.by_state and not b.get("state")):
            return None
        key = (b["kind"], b["state"] if kind.by_state else None)
        groups.setdefault(key, []).append(short_id(str(b["id"]), b["kind"]))
    return ", ".join(phrase(KINDS[name], state, ids) for (name, state), ids in groups.items())


def summarize(step):
    """The short text for a step, or None when status.py's reason must show instead."""
    blockers = step.get("blockers") or []
    if step.get("step") == "done":
        return ""
    if not blockers:
        return None
    kinds = {b.get("kind") for b in blockers}
    if kinds == {"roadmap"}:
        return "no roadmap"
    if kinds == {"source"}:
        return "brief behind %s" % ", ".join(b["id"] for b in blockers)
    if kinds == {"brief"} and len(blockers) == 1:
        return BRIEF.get(blockers[0].get("state"))
    return grouped(blockers)


def reason(step, failures):
    """The row's reason: {text, hover, failed}. Failures win over the step: fixing the folder comes first."""
    if failures:
        n = len(failures)
        return {"text": "%d check failure%s" % (n, "" if n == 1 else "s"), "hover": "\n".join(failures),
                "failed": True}
    full = step.get("reason") or ""
    text = summarize(step)
    return {"text": full if text is None else text, "hover": full, "failed": False}


# Next actions: each blocker of the step as what to do, for the task page's Next panel.
# How one kind of blocker reads as an action:
#   verbs  the verb of each state; ANY_STATE stands for every state; a state it lacks reads "Resolve"
#   name   the name every action of the kind takes, or None to name it by the task's title for its id
Doing = collections.namedtuple("Doing", "verbs name")
ANY_STATE = "*"
ACTIONS = {
    "feature": Doing({"planned": "Spec", "draft": "Approve spec", "approved": "Build", "building": "Build",
                      "review": "Finish review", "no-pr": "Open PR for"}, None),
    "decision": Doing({"open": "Decide", "proposed": "Confirm"}, None),
    "spike": Doing({"pending": "Run spike", "failed": "Rerun spike"}, None),
    "item": Doing({ANY_STATE: "Close"}, None),
    "repo": Doing({"worktree": "Remove worktree"}, ""),
    "brief": Doing({"missing": "Write brief", "no-date": "Restamp brief", "no-sources": "Restamp brief"}, "brief.md"),
    "roadmap": Doing({"missing": "Plan"}, "write the roadmap"),
}
UNKNOWN = "Resolve"


def make_action(verb, ident, short, name, state, waiting):
    return {"verb": verb, "id": ident, "short": short, "name": name, "state": state, "waiting": bool(waiting)}


def action(blocker, titles, roadmap):
    kind, state, ident = blocker.get("kind"), blocker.get("state"), str(blocker.get("id"))
    doing = ACTIONS.get(kind)
    verb = doing and (doing.verbs.get(state) or doing.verbs.get(ANY_STATE))
    if not verb:
        verb, name = UNKNOWN, ""
    elif doing.name is not None:
        name = doing.name
    else:
        # A feature built from the roadmap reads by its roadmap entry.
        name = titles.get(roadmap.get(ident, ident)) or titles.get(ident) or ""
    short = roadmap.get(ident) or short_id(ident, kind)
    return make_action(verb, ident, short, name, state, blocker.get("waiting"))


def brief_action(sources):
    """The changed source groups as one action: the brief is updated once for all of them."""
    name = "%s changed since brief.md was stamped" % ", ".join(str(s["id"]) for s in sources)
    return make_action("Update brief", "brief.md", "brief.md", name, "changed",
                       any(s.get("waiting") for s in sources))


def next_actions(step, titles, roadmap):
    """One action per blocker of the step, in status.py's order ({verb, id, short, name, state, waiting}).

    titles maps an id to the task's title for it; roadmap maps a feature folder to its roadmap id.
    The changed source groups make one action, where the first of them stood. Done has none.
    """
    if step.get("step") == "done":
        return []
    blockers = step.get("blockers") or []
    sources = [b for b in blockers if b.get("kind") == "source" and b.get("state") == "changed"]
    out = []
    for b in blockers:
        if b in sources:
            if b is sources[0]:
                out.append(brief_action(sources))
            continue
        out.append(action(b, titles, roadmap))
    return out


# Check groups: status.py's failures and warnings, one group per kind of message, in plain words.
#   kind     a short name of the kind
#   pattern  matches the message; its group "id" is the id the message is about, when it names one
#   one/many the title for one message and for n of them
#   fix      what to do about it
Check = collections.namedtuple("Check", "kind pattern one many fix")
CHECKS = [
    Check("no-feature", r"(?P<id>\S+): decided and needs code, but no feature links it",
          "1 decision with no feature to build it", "{n} decisions with no feature to build them",
          "Link it in a feature's story at plan or spec, or set needs_code: false if it changes no code."),
    Check("unproving", r"(?P<id>\S+): proves no requirement",
          "1 validation proving no requirement", "{n} validations proving no requirement",
          "List it under a requirement in acs.yaml, or drop it."),
    Check("no-main", r"README: no main repo",
          "README has no main repo", "README has no main repo", "Mark one repo with main: true."),
    Check("before-spike", r"(?P<id>\S+): decided while spike .+? has not passed",
          "1 decision decided before its spike passed", "{n} decisions decided before their spike passed",
          "Run the spike first, or move the decision back to proposed."),
    Check("missing-id", r".+?: cites (?P<id>\S+), which does not exist",
          "1 reference to an id that does not exist", "{n} references to ids that do not exist",
          "Fix or remove the id in that file."),
    Check("obsolete-id", r"brief\.md: cites (?P<id>\S+), ",
          "1 superseded or dropped id cited in brief.md", "{n} superseded or dropped ids cited in brief.md",
          "Cite the decision that replaced it, or remove it, then run task.py consolidate."),
    Check("stale-block", r"brief\.md: (?:block \S+ is stale|no \S+ block \(run)",
          "brief.md out of sync with the folder", "brief.md out of sync with the folder", "Run task.py sync."),
    Check("orphan", r"(?P<id>\S+): orphan",
          "1 decision outside every requirement's tree", "{n} decisions outside every requirement's tree",
          "Give it born_from, make it a requirement's root, or drop it."),
    Check("no-validation", r"(?P<id>\S+): requirement without a validation",
          "1 requirement with nothing to prove it", "{n} requirements with nothing to prove them",
          "Add a validation to it in acs.yaml."),
    Check("no-decision", r"(?P<id>\S+): requirement without a decision",
          "1 requirement with no decision", "{n} requirements with no decision",
          "Give it a root decision in acs.yaml."),
    Check("stale-status", r"(?P<id>\S+): (?:no (?:roadmap )?status \(|(?:roadmap )?status is \S+ but )",
          "1 status out of date", "{n} statuses out of date", "Run task.py sync."),
]
OTHER = "other"


def check_kind(message):
    """The kind a message is of and the id it names, or (None, None) for a message of no known kind."""
    for check in CHECKS:
        match = re.match(check.pattern, message)
        if match:
            return check, match.groupdict().get("id")
    return None, None


def check_groups(failures, warnings):
    """One group per kind of message, failures first, each kind where its first message stood:
    {severity, kind, title, fix, ids, messages}. A message of no known kind is a group of its own,
    titled by the message as status.py wrote it."""
    out, checks = [], {}
    for severity, messages in (("failure", failures), ("warning", warnings)):
        by_kind = {}
        for message in messages:
            check, ident = check_kind(message)
            if check is None:
                out.append({"severity": severity, "kind": OTHER, "title": message, "fix": "", "ids": [],
                            "messages": [message]})
                continue
            group = by_kind.get(check.kind)
            if group is None:
                group = by_kind[check.kind] = {"severity": severity, "kind": check.kind, "title": "",
                                               "fix": check.fix, "ids": [], "messages": []}
                checks[id(group)] = check
                out.append(group)
            group["messages"].append(message)
            if ident and ident not in group["ids"]:
                group["ids"].append(ident)
    for group in out:
        check = checks.get(id(group))
        if check:
            n = len(group["messages"])
            group["title"] = check.one if n == 1 else check.many.format(n=n)
    return out
