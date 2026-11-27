"""review.py - the CLOSE review of a /flow feature: review.yaml (or the legacy `review:` block of
feature.yaml), the checks on its findings and axes, and the `finding` command."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from lib import yamlio  # noqa: E402
from lib.yamlio import as_list, load_mapping  # noqa: E402
from lib.gitutil import head_sha  # noqa: E402
from lib.yamledit import block_end, edit, scalar  # noqa: E402

ACTIONS = ("fix", "wontfix")
SEVERITIES = ("blocker", "should-fix", "nit")
CONFIDENCES = ("high", "medium", "low")
SOURCES = ("spec-review", "standards-review", "correctness-review", "tests-review", "security-review",
           "pr-comment", "user")
LEGACY_SOURCE = "legacy"               # findings migrated from a feature.yaml review block, source unknown
AXES = tuple(s[:-len("-review")] for s in SOURCES if s.endswith("-review"))   # what a clean review ran
REQUIRED_AXES = ("spec", "standards")  # the two axes of the CLOSE review, for size M and L


def review_path(folder):
    return os.path.join(folder, "review.yaml")


def load_review(data, folder):
    """The review findings and where they live: (list or None, 'file' | 'legacy' | None).

    review.yaml beside feature.yaml wins; a `review:` block inside feature.yaml is the legacy place."""
    if folder and os.path.isfile(review_path(folder)):
        _, doc = load_mapping(review_path(folder))
        findings = doc.get("findings")
        return (findings if isinstance(findings, list) else None), "file"
    legacy = data.get("review")
    if isinstance(legacy, dict) and isinstance(legacy.get("findings"), list):
        return legacy["findings"], "legacy"
    return None, None


def validate_findings(findings, by_id, legacy, err, warn):
    """Check review findings: review.yaml ones carry an R-n id and may wait for an action; legacy ones need it."""
    seen_ids, seen_comments = set(), set()
    for i, finding in enumerate(findings):
        name = "review.findings[%d]" % i
        if not isinstance(finding, dict):
            err("%s needs 'text'" % name)
            continue
        if not legacy:
            fid = str(finding.get("id") or "")
            if not re.match(r"^R-[1-9][0-9]*$", fid):
                err("review.yaml: id %s must be R-<n>" % (fid or "(missing)"))
            elif fid in seen_ids:
                err("review.yaml: id %s is duplicated" % fid)
            seen_ids.add(fid)
            name = "review.yaml %s" % (fid or name)
        if not str(finding.get("text") or "").strip():
            err("%s needs 'text'" % name)
            continue
        action = finding.get("action")
        if action is not None or legacy:            # a review.yaml finding may still wait for its outcome
            if action not in ACTIONS:
                err("%s action must be one of %s" % (name, ", ".join(ACTIONS)))
            elif action == "fix" and finding.get("task") not in by_id:
                err("%s is a fix without an existing 'task'" % name)
            elif action == "wontfix" and not str(finding.get("reason") or "").strip():
                err("%s is a wontfix without a 'reason'" % name)
        source = finding.get("source")
        if source is None:
            (warn if legacy else err)("%s has no 'source' (%s)" % (name, ", ".join(SOURCES)))
        elif source not in SOURCES and not (source == LEGACY_SOURCE and not legacy):
            err("%s source must be one of %s" % (name, ", ".join(SOURCES)))
        elif source == "pr-comment" and not finding.get("comment_id"):
            err("%s is a pr-comment without a 'comment_id'" % name)
        for key, allowed in (("severity", SEVERITIES), ("confidence", CONFIDENCES)):
            if finding.get(key) is not None and finding.get(key) not in allowed:
                err("%s %s must be one of %s" % (name, key, ", ".join(allowed)))
        cid = finding.get("comment_id")
        if cid is not None:
            if cid in seen_comments:
                err("comment_id %s is recorded twice" % cid)
            seen_comments.add(cid)


def task_ids(data):
    return {str(t.get("id")) for t in as_list(data.get("tasks")) if isinstance(t, dict)}


def outcome_lines(args):
    """The review.yaml lines of a finding's outcome, in the indent flow.py writes findings with."""
    if args.action == "fix":
        return field_lines([("action", "fix"), ("task", args.task)])
    return field_lines([("action", "wontfix"), ("reason", args.reason)])


def field_lines(fields):
    """One `key: value` line per field, in the indent of a finding's keys; a multi-line value stays on one
    quoted line, so YAML reads back exactly the text given."""
    return ["    %s: %s\n" % (key, scalar(value)) for key, value in fields]


def finding_outcome_error(args, tasks):
    """Why --action/--task/--reason do not make a valid outcome, or None."""
    if args.action == "fix" and not args.task:
        return "a fix finding names the task that fixes it: --task T<n>"
    if args.action == "fix" and args.task not in tasks:
        return "task %s does not exist in feature.yaml" % args.task
    if args.action == "wontfix" and not args.reason:
        return "a wontfix finding needs --reason"
    if (args.task or args.reason) and not args.action:
        return "--task and --reason go with --action"
    return None


def describe_outcome(finding):
    action = finding.get("action")
    if action == "fix":
        return "fix %s" % finding.get("task")
    return action or "no action"


def set_outcome(path, data, args):
    """finding <feature> R-n --action ...: set or replace the outcome of one finding in review.yaml."""
    rpath = review_path(os.path.dirname(path))
    if not os.path.isfile(rpath):
        print("ERROR: %s has no review.yaml yet: record the finding first" % data.get("id"))
        return 1
    extra = [k for k in ("text", "source", "severity", "confidence", "file", "line", "hunk", "fix", "comment_id")
             if getattr(args, k) is not None] + (["none"] if args.none else [])
    if extra:
        print("ERROR: %s takes only --action with --task or --reason (not --%s)"
              % (args.target, ", --".join(k.replace("_", "-") for k in extra)))
        return 1
    if not args.action:
        print("ERROR: give the outcome: --action fix --task T<n> | --action wontfix --reason R")
        return 1
    tasks = task_ids(data)
    problem = finding_outcome_error(args, tasks)
    if problem:
        print("ERROR: " + problem)
        return 1
    text, doc = load_mapping(rpath)
    found = next((f for f in as_list(doc.get("findings"))
                  if isinstance(f, dict) and str(f.get("id")) == args.target), None)
    if found is None:
        print("ERROR: review.yaml has no finding %s" % args.target)
        return 1
    lines = text.splitlines(True)
    start = next((i for i, l in enumerate(lines)
                  if re.match(r"^  - id: %s\s*(#.*)?$" % re.escape(args.target), l.rstrip("\n"))), None)
    if start is None:
        print("ERROR: %s is not written in block form in review.yaml; rewrite it as `- id: %s` with one key per line"
              % (args.target, args.target))
        return 1
    outcome = outcome_lines(args)

    def change(lines):
        end = block_end(lines, start, 2)
        body = [l for l in lines[start + 1:end] if not re.match(r"^    (action|task|reason):", l)]
        lines[start + 1:end] = body + outcome

    def applied(d):
        f = next(f for f in as_list(d.get("findings")) if isinstance(f, dict) and str(f.get("id")) == args.target)
        return f.get("action") == args.action and (f.get("task") == args.task if args.action == "fix"
                                                   else f.get("reason") == args.reason and "task" not in f)

    old = describe_outcome(found)
    edit(rpath, text, change, applied)
    print("%s %s: %s -> %s" % (data.get("id"), args.target, old,
                               "fix %s" % args.task if args.action == "fix" else "wontfix"))
    return 0


def unknown_axes(axes):
    """The entries of a clean review's axes that are not review axes; all of it when it is not a list."""
    if not isinstance(axes, list):
        return [axes]
    return [a for a in axes if a not in AXES]


def axes_error(axes, size):
    """Why the axes of a clean review are not enough, else None."""
    if not axes:
        return ("a clean review names the axes that ran: --axes %s (one or more of %s)"
                % (",".join(REQUIRED_AXES), ", ".join(AXES)))
    unknown = unknown_axes(axes)
    if unknown:
        return "unknown axis %s (%s)" % (", ".join(unknown), ", ".join(AXES))
    missing = [a for a in REQUIRED_AXES if a not in axes] if size in ("M", "L") else []
    if missing:
        return ("size %s needs a review on both %s: %s did not run; run it, or record its findings"
                % (size, " and ".join(REQUIRED_AXES), ", ".join(missing)))
    return None


def cmd_finding(path, args, root):
    _, data = load_mapping(path)
    if isinstance(data.get("review"), dict):
        print("ERROR: feature.yaml holds a legacy review block: move it into review.yaml beside it first")
        return 1
    if args.target:
        return set_outcome(path, data, args)
    rpath = review_path(os.path.dirname(path))
    exists = os.path.isfile(rpath)
    if exists:
        text, doc = load_mapping(rpath)
        if not isinstance(doc.get("findings"), list):
            print("ERROR: review.yaml: findings must be a list ([] for a clean review); fix the file first")
            return 1
    else:
        sha = head_sha(root)
        text = "base: %s\nhead: %s\ncreated: %s\nfindings: []\n" % (
            json.dumps(str(data.get("base"))) if data.get("base") else "null",
            json.dumps(sha) if sha else "null", yamlio.today())
        doc = yamlio.parse(text, rpath)
    existing = as_list(doc.get("findings"))
    tasks = task_ids(data)

    axes = [a.strip() for a in (args.axes or "").split(",") if a.strip()]
    if args.none:
        if existing:
            print("ERROR: the review already has %d finding(s)" % len(existing))
            return 1
        problem = axes_error(axes, data.get("size"))
        if problem:
            print("ERROR: " + problem)
            return 1
        item = None
    elif args.axes:
        print("ERROR: --axes only goes with --none: each finding names its axis in --source")
        return 1
    else:
        problem = None
        if not args.text:
            problem = "a finding needs --text (or use --none for a clean review)"
        elif not args.source:
            problem = "a finding needs --source (%s)" % ", ".join(SOURCES)
        elif args.source == "pr-comment" and not args.comment_id:
            problem = "a pr-comment finding needs --comment-id"
        elif args.comment_id and args.source != "pr-comment":
            problem = "--comment-id only goes with --source pr-comment"
        elif args.comment_id and any(isinstance(f, dict) and str(f.get("comment_id")) == str(args.comment_id)
                                     for f in existing):
            problem = "comment %s is already recorded" % args.comment_id
        elif args.line is not None and args.line < 1:
            problem = "--line is a line number, 1 or more"
        else:
            problem = finding_outcome_error(args, tasks)
        if problem:
            print("ERROR: " + problem)
            return 1
        fid = yamlio.next_id([f.get("id") for f in existing if isinstance(f, dict)], "R")
        fields = [("text", args.text), ("source", args.source)]
        fields += [(key, getattr(args, key)) for key in ("severity", "confidence", "file", "hunk", "fix")
                   if getattr(args, key)]
        if args.line is not None:
            fields.append(("line", args.line))
        if args.comment_id:
            fields.append(("comment_id", args.comment_id))
        item = ["  - id: %s\n" % fid] + field_lines(fields)
        if args.action:
            item.extend(outcome_lines(args))

    def change(lines):
        top = next((i for i, l in enumerate(lines) if re.match(r"^findings:(\s|$)", l)), None)
        if top is None:
            lines.append("findings: []\n")
            top = len(lines) - 1
        # Axes belong to a clean review only: drop them, and write them again for --none.
        for i in reversed([i for i, l in enumerate(lines) if re.match(r"^axes:(\s|$)", l)]):
            del lines[i:block_end(lines, i, 0)]
            top -= 1 if i < top else 0
        if item is None:
            lines[top] = "findings: []\n"
            lines.insert(top, "axes: [%s]\n" % ", ".join(axes))
            return
        lines[top] = "findings:\n"
        at = block_end(lines, top, 0)
        lines[at:at] = item

    edit(rpath, text, change, lambda d: len(as_list(d.get("findings"))) == len(existing) + (0 if item is None else 1)
         and (item is not None or (d.get("findings") == [] and d.get("axes") == axes)))
    print("%s: %s" % (data.get("id"), "clean review recorded" if item is None else "%s recorded" % fid))
    return 0
