"""feature.py - a /flow feature: finding its feature.yaml, the repo each task commits to, the checks
on feature.yaml and spec.md, what still blocks `finish`, and the frontier of tasks ready to start."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from lib.yamlio import as_list, list_errors, load_mapping  # noqa: E402
from lib.gitutil import commit_exists  # noqa: E402
from lib.graph import find_cycle  # noqa: E402
from roadmap import load_roadmap, roadmap_features, roadmap_path  # noqa: E402
from review import (AXES, REQUIRED_AXES, load_review, review_path, unknown_axes,  # noqa: E402
                    validate_findings)

SIZES = ("S", "M", "L")
STATUSES = ("draft", "approved", "building", "review", "done")
TASK_STATUSES = ("todo", "doing", "verifying", "done")
STARTED = ("verifying", "done")        # a task whose commit exists
CHECK_STATUSES = ("pending", "pass", "fail")
MAX_TASKS = 8


def default_specs(root):
    return os.path.join(root, ".specs")


def resolve(feature, specs):
    candidates = [
        feature,
        os.path.join(feature, "feature.yaml"),
        os.path.join(specs, "features", feature, "feature.yaml"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    sys.stderr.write("feature.yaml not found for '%s' (looked in: %s)\n" % (feature, ", ".join(candidates[1:])))
    sys.exit(2)


def task_root(root, task):
    """The repo a task's commit lives in: its optional 'repo' path, else --root.

    On Windows a Git Bash path (/c/projects/x) means C:/projects/x."""
    repo = task.get("repo")
    if not repo:
        return root
    repo = str(repo)
    if os.name == "nt":
        repo = re.sub(r"^/([A-Za-z])(?=/|$)", lambda m: m.group(1).upper() + ":", repo)
    return os.path.abspath(os.path.expanduser(repo))


def missing_repo(root, tid, task):
    """The error for a task whose 'repo' is not a directory, else None."""
    path = task_root(root, task)
    if task.get("repo") and not os.path.isdir(path):
        return "%s repo %s is not a directory (%s)" % (tid, task.get("repo"), path)
    return None


def validate(data, root, specs=None, folder=None):
    specs = specs or default_specs(root)
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    for key in ("id", "title"):
        if not isinstance(data.get(key), str) or not data.get(key).strip():
            err("'%s' is required" % key)
    size = data.get("size")
    if size not in SIZES:
        err("'size' must be one of %s" % ", ".join(SIZES))
    status = data.get("status")
    if status not in STATUSES:
        err("'status' must be one of %s" % ", ".join(STATUSES))

    approved = data.get("approved") or {}
    if status in STATUSES and status != "draft":
        if not isinstance(approved, dict) or not approved.get("spec") or not approved.get("tasks"):
            err("status '%s' needs approved.spec and approved.tasks (run `approve` after the user approves)" % status)
        if not data.get("base"):
            err("status '%s' needs 'base' (recorded by `approve`)" % status)

    if folder and size in ("M", "L") and status != "draft":
        spec = os.path.join(folder, "spec.md")
        if not os.path.isfile(spec):
            err("spec.md is missing next to feature.yaml")
        else:
            with open(spec, encoding="utf-8") as fh:
                if "TODO" in fh.read():
                    err("spec.md still has a TODO")

    for e in list_errors(data, ("acceptance", "tasks", "checks", "deferred"), "feature.yaml: "):
        err(e)
    for task in as_list(data.get("tasks")):
        if isinstance(task, dict):
            for e in list_errors(task, ("covers", "blocked_by"), "feature.yaml: %s " % task.get("id")):
                err(e)

    acs = as_list(data.get("acceptance"))
    if not acs:
        err("'acceptance' needs at least one criterion")
    ac_ids = []
    for i, ac in enumerate(acs):
        if not isinstance(ac, dict) or not ac.get("id") or not str(ac.get("text") or "").strip():
            err("acceptance[%d] needs 'id' and 'text'" % i)
            continue
        if ac["id"] in ac_ids:
            err("acceptance id %s is duplicated" % ac["id"])
        ac_ids.append(ac["id"])

    tasks = as_list(data.get("tasks"))
    if not tasks and status != "draft":
        err("'tasks' is empty")
    if len(tasks) > MAX_TASKS:
        warn("%d tasks (> %d): suggest splitting the feature or escalating" % (len(tasks), MAX_TASKS))

    task_ids, by_id, covered, shas = [], {}, set(), {}
    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or not task.get("id"):
            err("tasks[%d] needs an 'id'" % i)
            continue
        tid = task["id"]
        if tid in by_id:
            err("task id %s is duplicated" % tid)
        task_ids.append(tid)
        by_id[tid] = task
        if not str(task.get("title") or "").strip():
            err("%s needs a 'title'" % tid)
        if not str(task.get("verify") or "").strip():
            err("%s needs a 'verify' command" % tid)
        if not str(task.get("commit") or "").strip():
            err("%s needs a 'commit' message" % tid)
        covers = as_list(task.get("covers"))
        if not covers:
            err("%s needs 'covers' with at least one acceptance id" % tid)
        for ac in covers:
            if ac not in ac_ids:
                err("%s covers unknown criterion %s" % (tid, ac))
            covered.add(ac)
        tstatus = task.get("status")
        if tstatus not in TASK_STATUSES:
            err("%s status must be one of %s" % (tid, ", ".join(TASK_STATUSES)))
        sha = task.get("sha")
        repo_error = missing_repo(root, tid, task)
        if repo_error:
            err(repo_error)
        elif tstatus in STARTED:
            if not sha:
                err("%s is %s without a 'sha'" % (tid, tstatus))
            elif not commit_exists(task_root(root, task), str(sha)):
                err("%s sha %s is not in this repository" % (tid, sha))
            else:
                shas.setdefault((task_root(root, task), str(sha)), []).append(tid)
        elif sha:
            err("%s has a sha but status '%s'" % (tid, tstatus))

    for (_, sha), tids in shas.items():
        if len(tids) > 1:
            err("tasks %s share commit %s (one commit per task)" % (", ".join(tids), sha))

    for tid, task in by_id.items():
        for dep in as_list(task.get("blocked_by")):
            if dep == tid:
                err("%s is blocked by itself" % tid)
            elif dep not in by_id:
                err("%s is blocked by unknown task %s" % (tid, dep))
            elif task.get("status") in ("doing",) + STARTED and by_id[dep].get("status") not in STARTED:
                err("%s is %s but its blocker %s is not verifying or done" % (tid, task.get("status"), dep))
    cycle = find_cycle({t: as_list(task.get("blocked_by")) for t, task in by_id.items()})
    if cycle:
        err("blocked_by cycle: %s" % " -> ".join(cycle))

    checks = [c for c in as_list(data.get("checks")) if isinstance(c, dict)]
    if tasks:
        for ac in ac_ids:
            if ac not in covered:
                err("criterion %s is not covered by any task" % ac)
            if not any(c.get("ac") == ac for c in checks):
                err("criterion %s has no check" % ac)
    for c in checks:
        name = c.get("ac")
        if name not in ac_ids:
            err("check for unknown criterion %s" % name)
        if bool(str(c.get("test") or "").strip()) == bool(str(c.get("manual") or "").strip()):
            err("check %s needs exactly one of 'test' or 'manual'" % name)
        if c.get("status") not in CHECK_STATUSES:
            err("check %s status must be one of %s" % (name, ", ".join(CHECK_STATUSES)))
    for tid, task in by_id.items():
        if task.get("status") == "done":
            for c in checks:
                if c.get("ac") in as_list(task.get("covers")) and c.get("status") != "pass":
                    err("%s is done but check %s is %s" % (tid, c.get("ac"), c.get("status")))
                    break
    if any(str(c.get("test") or "").strip() for c in checks) and not str(data.get("test") or "").strip():
        err("'test' (the suite command) is required when a check names a test")

    findings, where = load_review(data, folder)
    if where == "file" and isinstance(data.get("review"), dict):
        err("the review is in both feature.yaml and review.yaml: move the feature.yaml block into review.yaml")
    elif where == "legacy":
        warn("the review block in feature.yaml is legacy: new reviews go to review.yaml beside it")
    if where == "file" and findings is None:
        err("review.yaml: findings must be a list ([] for a clean review)")
    validate_findings(findings or [], by_id, where == "legacy", err, warn)
    if where == "file" and findings == []:
        _, review = load_mapping(review_path(folder))
        axes = review.get("axes")
        if not axes:
            if size in ("M", "L"):
                warn("review.yaml: the clean review names no axes (record it with `finding --none --axes %s`)"
                     % ",".join(REQUIRED_AXES))
        elif unknown_axes(axes):
            err("review.yaml: axes must be a list of %s" % ", ".join(AXES))

    pr = data.get("pr")
    if pr is not None and not re.match(r"^https?://\S+$", str(pr)):
        err("'pr' must be a URL")

    if status == "done":
        err_list = finish_blockers(data, folder)
        errors.extend("status 'done' but %s" % e for e in err_list)

    link = data.get("roadmap")
    if link is not None:
        roadmap = load_roadmap(specs)
        if roadmap is None:
            err("roadmap: %s, but %s does not exist" % (link, roadmap_path(specs)))
        elif str(link) not in roadmap_features(roadmap):
            err("roadmap: %s is not a feature in %s" % (link, roadmap_path(specs)))

    return errors, warnings


def finish_blockers(data, folder=None):
    """What keeps a feature from being done."""
    out = []
    tasks = [t for t in as_list(data.get("tasks")) if isinstance(t, dict)]
    open_tasks = [str(t.get("id")) for t in tasks if t.get("status") != "done"]
    if open_tasks:
        out.append("tasks are open: %s" % ", ".join(open_tasks))
    for c in as_list(data.get("checks")):
        if isinstance(c, dict) and c.get("status") != "pass":
            out.append("check %s is %s" % (c.get("ac"), c.get("status")))
    findings, where = load_review(data, folder)
    if data.get("size") in ("M", "L") and findings is None:
        out.append("size %s needs review.yaml (record the review with `finding`, or `finding --none` when it is clean)"
                   % data.get("size"))
    if where == "file":
        for f in findings:
            if isinstance(f, dict) and f.get("action") is None:
                out.append("review finding %s has no action" % f.get("id"))
    return out


def frontier(tasks):
    done = {t.get("id") for t in tasks if t.get("status") in STARTED}
    ready, blocked = [], []
    for task in tasks:
        if task.get("status") in STARTED:
            continue
        waiting = [d for d in as_list(task.get("blocked_by")) if d not in done]
        (blocked if waiting else ready).append((task, waiting))
    return ready, blocked
