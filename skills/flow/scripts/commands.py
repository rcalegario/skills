"""commands.py - the /flow commands that read a feature or move it along its life:
status, check, approve, review, finish, pr and new."""
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from lib import yamlio  # noqa: E402
from lib.yamlio import as_list, load_mapping  # noqa: E402
from lib.gitutil import head_sha  # noqa: E402
from lib.yamledit import edit, set_child, set_top  # noqa: E402
from roadmap import load_roadmap, roadmap_features, roadmap_path, sync_roadmap  # noqa: E402
from review import load_review  # noqa: E402
from feature import STARTED, finish_blockers, frontier, validate  # noqa: E402


def cmd_status(path, root, specs):
    _, data = load_mapping(path)
    tasks = [t for t in as_list(data.get("tasks")) if isinstance(t, dict)]
    done = [t for t in tasks if t.get("status") == "done"]
    print("%s - %s [%s, %s]" % (data.get("id"), data.get("title"), data.get("size"), data.get("status")))
    verifying = [t for t in tasks if t.get("status") == "verifying"]
    print("Tasks: %d/%d done%s" % (len(done), len(tasks), ", %d verifying" % len(verifying) if verifying else ""))
    for task in verifying:
        print("  %-8s %s  %s" % ("verifying", task.get("id"), task.get("title")))
    ready, blocked = frontier(tasks)
    for task, _ in ready:
        state = "doing" if task.get("status") == "doing" else "ready"
        print("  %-8s %s  %s" % (state, task.get("id"), task.get("title")))
    for task, waiting in blocked:
        print("  blocked  %s  %s (by %s)" % (task.get("id"), task.get("title"), ", ".join(waiting)))
    checks = [c for c in as_list(data.get("checks")) if isinstance(c, dict)]
    if checks:
        print("Checks: %d/%d pass" % (sum(1 for c in checks if c.get("status") == "pass"), len(checks)))
    findings, where = load_review(data, os.path.dirname(path))
    if findings:
        waiting = sum(1 for f in findings if isinstance(f, dict) and f.get("action") is None and where == "file")
        print("Review findings: %d%s%s" % (len(findings), " (%d without action)" % waiting if waiting else "",
                                           " (legacy block in feature.yaml)" if where == "legacy" else ""))
    errors, warnings = validate(data, root, specs, os.path.dirname(path))
    for w in warnings:
        print("WARNING: %s" % w)
    if errors:
        print("%d structural error(s): run `flow.py check`" % len(errors))
    return 0


def report(errors, warnings):
    for w in warnings:
        print("WARNING: %s" % w)
    for e in errors:
        print("ERROR: %s" % e)
    return 1 if errors else 0


def cmd_check(path, root, specs):
    _, data = load_mapping(path)
    if report(*validate(data, root, specs, os.path.dirname(path))):
        return 1
    print("OK: %s" % os.path.relpath(path, root))
    return 0


def cmd_approve(path, root, specs, step):
    text, data = load_mapping(path)
    size = data.get("size")
    approved = data.get("approved") if isinstance(data.get("approved"), dict) else {}
    if data.get("status") != "draft":
        print("ERROR: feature status is '%s'; approvals happen while it is draft" % data.get("status"))
        return 1
    if step == "tasks" and size != "L":
        print("ERROR: size %s approves spec and tasks together: run `approve <feature> spec`" % size)
        return 1
    if step == "tasks" and not approved.get("spec"):
        print("ERROR: approve the spec first")
        return 1
    if step == "spec" and size == "L" and approved.get("spec"):
        print("ERROR: the spec is already approved; next is `approve <feature> tasks`")
        return 1

    today = yamlio.today()
    complete = step == "tasks" or size != "L"
    planned = dict(data)
    planned["approved"] = dict(approved, spec=approved.get("spec") or today)
    if complete:
        base = head_sha(root)
        if base is None:
            print("ERROR: no commit to record as base in %s" % root)
            return 1
        planned["approved"]["tasks"] = today
        planned.update(status="approved", base=base)
    if report(*validate(planned, root, specs, os.path.dirname(path))):
        return 1

    def change(lines):
        if not approved.get("spec"):
            set_child(lines, "approved", "spec", today, after="status")
        if complete:
            set_child(lines, "approved", "tasks", today, after="status")
            set_top(lines, "status", "approved")
            set_top(lines, "base", planned["base"], after="approved")

    edit(path, text, change, lambda d: d.get("status") == planned["status"])
    if complete:
        print("Approved: %s is ready to build from base %s" % (data.get("id"), planned["base"]))
    else:
        print("Spec approved: write the tasks and checks, then `approve <feature> tasks`")
    return 0


def cmd_review(path, root, specs):
    text, data = load_mapping(path)
    if data.get("status") != "building":
        print("ERROR: feature status is '%s'; review starts from building" % data.get("status"))
        return 1
    open_tasks = [str(t.get("id")) for t in as_list(data.get("tasks"))
                  if isinstance(t, dict) and t.get("status") not in STARTED]
    if open_tasks:
        print("ERROR: tasks have no commit yet: %s" % ", ".join(open_tasks))
        return 1
    edit(path, text, lambda lines: set_top(lines, "status", "review"), lambda d: d.get("status") == "review")
    print("%s in review: diff since base %s" % (data.get("id"), data.get("base")))
    return 0


def cmd_finish(path, root, specs):
    text, data = load_mapping(path)
    if data.get("status") != "review":
        print("ERROR: feature status is '%s'; finish comes after `review`" % data.get("status"))
        return 1
    blockers = finish_blockers(data, os.path.dirname(path))
    if blockers:
        print("ERROR: not done yet:\n  " + "\n  ".join(blockers))
        return 1
    planned = dict(data, status="done")
    if report(*validate(planned, root, specs, os.path.dirname(path))):
        return 1
    edit(path, text, lambda lines: set_top(lines, "status", "done"), lambda d: d.get("status") == "done")
    print("%s done" % data.get("id"))
    return 0


def cmd_pr(path, url):
    if not re.match(r"^https?://\S+$", url):
        print("ERROR: --url must be the pull request URL")
        return 1
    text, data = load_mapping(path)
    edit(path, text, lambda lines: set_top(lines, "pr", url), lambda d: d.get("pr") == url)
    print("%s: pr recorded" % data.get("id"))
    return 0


# The shape of each list, commented under its empty value in a new feature.yaml: replace `[]` with it.
NEW_EXAMPLES = {
    "acceptance": (
        "# acceptance:\n"
        "#   - id: AC1\n"
        "#     text: WHEN the user clicks \"Export\" THEN a CSV of the filtered rows downloads\n"),
    "tasks": (
        "# tasks:\n"
        "#   - id: T1\n"
        "#     title: CSV writer with header and rows\n"
        "#     covers: [AC1]\n"
        "#     blocked_by: []\n"
        "#     verify: npm test -- export\n"
        "#     commit: \"feat(export): let users download the report as CSV\"\n"
        "#     status: todo\n"),
    "checks": (
        "# checks:\n"
        "#   - ac: AC1\n"
        "#     manual: \"Export a report and open it in a spreadsheet\"  # or test: \"file > test name\","
        " with a top-level test: suite command\n"
        "#     status: pending\n"),
}


def cmd_new(specs, args):
    folder = os.path.join(specs, "features", args.feature)
    if os.path.exists(folder):
        print("ERROR: %s already exists" % folder)
        return 1
    if args.roadmap:
        data = load_roadmap(specs)
        if data is None or args.roadmap not in roadmap_features(data):
            print("ERROR: roadmap: %s is not a feature of %s" % (args.roadmap, roadmap_path(specs)))
            return 1
    fields = {"id": args.feature, "title": args.title}
    if args.roadmap:
        fields["roadmap"] = args.roadmap
    if args.repo:
        fields["repo"] = args.repo
    fields.update(size=args.size, status="draft", approved={"spec": None, "tasks": None}, base=None)
    if args.test:
        fields["test"] = args.test
    story = {k: [i.strip() for i in v.split(",") if i.strip()]
             for k, v in (("decisions", args.decisions), ("validations", args.validations)) if v}
    if story:
        fields["story"] = story
    fields.update(acceptance=[], tasks=[], checks=[])
    text = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, default_flow_style=None)
    for key, example in NEW_EXAMPLES.items():
        line = "%s: []\n" % key
        assert text.count(line) == 1, line
        text = text.replace(line, line + example)
    os.makedirs(folder)
    with open(os.path.join(folder, "feature.yaml"), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    template = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "templates", "spec.md")
    with open(template, encoding="utf-8") as fh:
        spec = fh.read().replace("{title}", args.title)
    with open(os.path.join(folder, "spec.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write(spec)
    sync_roadmap(specs)
    print("Created %s: write the criteria in spec.md and feature.yaml, then `check`" % folder)
    return 0
