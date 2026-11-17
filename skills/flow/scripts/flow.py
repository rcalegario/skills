#!/usr/bin/env python3
"""flow.py - state changes and structure checks for a /flow feature.

Commands:
  status  <feature>                         progress and the frontier (tasks ready to start)
  check   <feature>                         validate feature.yaml and spec.md; exit 1 on any error
  approve <feature> spec|tasks              record the user's approval (M: `spec` approves both)
  set     <feature> T<n> doing|verifying [--commit X]
                                            start a task, or record its commit (HEAD by default): it then waits for its checks
  set     <feature> AC<n> pass|fail         record the result of a criterion's checks; a task is done once every
                                            check of the criteria it covers passes (never set by hand)
  finding <feature> --text T --source S [--comment-id N] --action fix --task T3 | --action wontfix --reason R | --none
                                            record a review finding (or a clean review)
  pr      <feature> --url U                 record the pull request that delivers the feature
  review  <feature>                         every task verifying or done: building -> review
  finish  <feature>                         every check pass and review recorded: review -> done
  roadmap [--approve]                       validate <specs>/roadmap.yaml, write the status of every feature and milestone
                                            into it, show progress and the features ready to start;
                                            --approve stamps today as `approved` once it is valid
  new     <feature> --title T --size S|M|L [--roadmap F] [--repo R] [--decisions D-1,D-2] [--validations V-1] [--test CMD]
                                            create the draft feature.yaml and spec.md

<feature> is a folder name under <specs>/features/, a folder path, or a path to feature.yaml.
<specs> is --specs, default <root>/.specs; --root is the git repository the task commits live in.
A feature's roadmap status comes from the feature.yaml whose `roadmap:` names it, and the script writes it
back into roadmap.yaml (with the milestone status) after every command that changes a feature.
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("flow.py needs PyYAML (pip install pyyaml). Without it, check the file by reading it.\n")
    sys.exit(2)

SIZES = ("S", "M", "L")
STATUSES = ("draft", "approved", "building", "review", "done")
TASK_STATUSES = ("todo", "doing", "verifying", "done")
STARTED = ("verifying", "done")        # a task whose commit exists
CHECK_STATUSES = ("pending", "pass", "fail")
ACTIONS = ("fix", "wontfix")
SOURCES = ("spec-review", "standards-review", "correctness-review", "tests-review", "security-review",
           "pr-comment", "user")
MAX_TASKS = 8


# ---------------------------------------------------------------- loading

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


def load(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        sys.stderr.write("ERROR: %s is not valid YAML: %s\n" % (path, exc))
        sys.exit(1)
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %s must be a mapping at the top level\n" % path)
        sys.exit(1)
    return text, data


def git(root, *args):
    proc = subprocess.run(["git"] + list(args), cwd=root, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    return proc.returncode, proc.stdout.strip()


def task_root(root, task):
    """The repo a task's commit lives in: its optional 'repo' path, else --root."""
    repo = task.get("repo")
    return os.path.abspath(os.path.expanduser(str(repo))) if repo else root


def commit_exists(root, sha):
    code, _ = git(root, "rev-parse", "--verify", "--quiet", "%s^{commit}" % sha)
    return code == 0


def as_list(value):
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------- check

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
        if tstatus in STARTED:
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
    cycle = find_cycle(by_id)
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

    review = data.get("review")
    findings = as_list(review.get("findings")) if isinstance(review, dict) else []
    seen_comments = set()
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict) or not str(finding.get("text") or "").strip():
            err("review.findings[%d] needs 'text'" % i)
            continue
        action = finding.get("action")
        if action not in ACTIONS:
            err("review.findings[%d] action must be one of %s" % (i, ", ".join(ACTIONS)))
        elif action == "fix" and finding.get("task") not in by_id:
            err("review.findings[%d] is a fix without an existing 'task'" % i)
        elif action == "wontfix" and not str(finding.get("reason") or "").strip():
            err("review.findings[%d] is a wontfix without a 'reason'" % i)
        source = finding.get("source")
        if source is None:
            warn("review.findings[%d] has no 'source' (%s)" % (i, ", ".join(SOURCES)))
        elif source not in SOURCES:
            err("review.findings[%d] source must be one of %s" % (i, ", ".join(SOURCES)))
        elif source == "pr-comment" and not finding.get("comment_id"):
            err("review.findings[%d] is a pr-comment without a 'comment_id'" % i)
        cid = finding.get("comment_id")
        if cid is not None:
            if cid in seen_comments:
                err("comment_id %s is recorded twice" % cid)
            seen_comments.add(cid)

    pr = data.get("pr")
    if pr is not None and not re.match(r"^https?://\S+$", str(pr)):
        err("'pr' must be a URL")

    if status == "done":
        err_list = finish_blockers(data)
        errors.extend("status 'done' but %s" % e for e in err_list)

    link = data.get("roadmap")
    if link is not None:
        roadmap = load_roadmap(specs)
        if roadmap is None:
            err("roadmap: %s, but %s does not exist" % (link, roadmap_path(specs)))
        elif str(link) not in roadmap_features(roadmap):
            err("roadmap: %s is not a feature in %s" % (link, roadmap_path(specs)))

    return errors, warnings


def finish_blockers(data):
    """What keeps a feature from being done."""
    out = []
    tasks = [t for t in as_list(data.get("tasks")) if isinstance(t, dict)]
    open_tasks = [str(t.get("id")) for t in tasks if t.get("status") != "done"]
    if open_tasks:
        out.append("tasks are open: %s" % ", ".join(open_tasks))
    for c in as_list(data.get("checks")):
        if isinstance(c, dict) and c.get("status") != "pass":
            out.append("check %s is %s" % (c.get("ac"), c.get("status")))
    review = data.get("review")
    if data.get("size") in ("M", "L") and not (isinstance(review, dict) and isinstance(review.get("findings"), list)):
        out.append("size %s needs review.findings (an empty list when the review is clean)" % data.get("size"))
    return out


def find_cycle(by_id):
    state = {}

    def visit(tid, path):
        state[tid] = 1
        for dep in as_list(by_id[tid].get("blocked_by")):
            if dep not in by_id or dep == tid:
                continue
            if state.get(dep) == 1:
                return path + [tid, dep]
            if dep not in state:
                found = visit(dep, path + [tid])
                if found:
                    return found
        state[tid] = 2
        return None

    for tid in by_id:
        if tid not in state:
            found = visit(tid, [])
            if found:
                return found[found.index(found[-1]):]
    return None


# ---------------------------------------------------------------- status

def frontier(tasks):
    done = {t.get("id") for t in tasks if t.get("status") in STARTED}
    ready, blocked = [], []
    for task in tasks:
        if task.get("status") in STARTED:
            continue
        waiting = [d for d in as_list(task.get("blocked_by")) if d not in done]
        (blocked if waiting else ready).append((task, waiting))
    return ready, blocked


def cmd_status(path, root, specs):
    _, data = load(path)
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
    review = data.get("review")
    findings = as_list(review.get("findings")) if isinstance(review, dict) else []
    if findings:
        print("Review findings: %d" % len(findings))
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
    _, data = load(path)
    if report(*validate(data, root, specs, os.path.dirname(path))):
        return 1
    print("OK: %s" % os.path.relpath(path, root))
    return 0


# ---------------------------------------------------------------- editing

def set_key(lines, start, end, indent, key, value, after=None):
    """Replace `key:` inside lines[start:end] at the given indent, or insert it after `after:`."""
    pattern = re.compile(r"^%s%s:(\s|$)" % (" " * indent, re.escape(key)))
    hits = [i for i in range(start, end) if pattern.match(lines[i])]
    assert len(hits) <= 1, "key %s appears %d times in the block" % (key, len(hits))
    new = "%s%s: %s\n" % (" " * indent, key, value)
    if hits:
        comment = re.search(r"\s+#.*$", lines[hits[0]].rstrip("\n"))
        if comment:
            new = new.rstrip("\n") + comment.group(0) + "\n"
        lines[hits[0]] = new
        return 0
    anchor = [i for i in range(start, end) if after and re.match(r"^%s%s:" % (" " * indent, after), lines[i])]
    pos = min(block_end(lines, anchor[0], indent), end) if anchor else end
    lines.insert(pos, new)
    return 1


def block_end(lines, start, indent):
    """First line after `start` that is not blank, not a comment and indented at most `indent`."""
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= indent:
            break
        end += 1
    return end


def set_top(lines, key, value, after=None):
    set_key(lines, 0, len(lines), 0, key, value, after=after)


def set_child(lines, parent, key, value, after=None):
    """Set `parent.key`, turning `parent:` into a block when it is missing or inline."""
    hits = [i for i, l in enumerate(lines) if re.match(r"^%s:(\s|$)" % re.escape(parent), l)]
    if not hits:
        anchor = [i for i, l in enumerate(lines) if after and re.match(r"^%s:" % after, l)]
        pos = block_end(lines, anchor[0], 0) if anchor else len(lines)
        lines.insert(pos, "%s:\n" % parent)
        hits = [pos]
    start = hits[0]
    if re.sub(r"\s+#.*$", "", lines[start]).strip() != "%s:" % parent:
        lines[start] = "%s:\n" % parent
    set_key(lines, start + 1, block_end(lines, start, 0), 2, key, value)


def item_blocks(lines, key, value):
    """(start, end, indent) of every list item that opens with `- key: value`."""
    pattern = re.compile(r"^(\s*)-\s+%s:\s*['\"]?%s['\"]?\s*(#.*)?$" % (re.escape(key), re.escape(value)))
    out = []
    for i, line in enumerate(lines):
        m = pattern.match(line.rstrip("\n"))
        if m:
            dash = len(m.group(1))
            out.append((i, block_end(lines, i, dash), dash + 2))
    return out


def edit(path, text, change, verify):
    """Apply change(lines) to the file text, check the parsed result with verify(data), then write."""
    lines = text.splitlines(True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    change(lines)
    new_text = "".join(lines)
    updated = yaml.safe_load(new_text)
    assert verify(updated), "the edit to %s did not apply" % path
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text)
    return updated


def head_sha(root, commit="HEAD"):
    code, sha = git(root, "rev-parse", "--short", "%s^{commit}" % commit)
    return sha if code == 0 else None


# ---------------------------------------------------------------- approve

def cmd_approve(path, root, specs, step):
    text, data = load(path)
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

    today = datetime.date.today().isoformat()
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


# ---------------------------------------------------------------- set

def cmd_set(path, root, specs, target, value, commit):
    text, data = load(path)
    tasks = {t.get("id"): t for t in as_list(data.get("tasks")) if isinstance(t, dict)}
    acs = [a.get("id") for a in as_list(data.get("acceptance")) if isinstance(a, dict)]
    if target in tasks:
        if value == "done":
            print("ERROR: a task is not set to done: it is done once the checks of its criteria pass "
                  "(`set <feature> AC<n> pass`)")
            return 1
        if value not in ("doing", "verifying"):
            print("ERROR: a task is set to doing or verifying")
            return 1
        return set_task(path, root, specs, text, data, tasks, target, value, commit)
    if target in acs:
        if value not in ("pass", "fail"):
            print("ERROR: a criterion's checks are set to pass or fail")
            return 1
        return set_check(path, text, data, tasks, target, value)
    print("ERROR: %s is neither a task nor a criterion of %s" % (target, data.get("id")))
    return 1


def set_task(path, root, specs, text, data, tasks, tid, value, commit):
    if data.get("status") not in ("approved", "building", "review"):
        print("ERROR: feature status is '%s'; tasks are built after approval" % data.get("status"))
        return 1
    open_blockers = [d for d in as_list(tasks[tid].get("blocked_by")) if tasks.get(d, {}).get("status") not in STARTED]
    if open_blockers:
        print("ERROR: %s is blocked by %s" % (tid, ", ".join(open_blockers)))
        return 1
    current = tasks[tid].get("status")
    if current in STARTED or (value == "doing" and current == "doing"):
        print("ERROR: %s is already %s" % (tid, current))
        return 1

    sha = None
    if value == "verifying":
        root = task_root(root, tasks[tid])
        if commit is None:
            try:
                rel = os.path.relpath(specs, root).replace("\\", "/")
            except ValueError:  # another drive on Windows
                rel = ".."
            inside = rel != ".." and not rel.startswith("../")
            # Specs inside the repo: check only the folder that holds them (a task folder among others).
            scope = os.path.dirname(rel) or "."
            pathspec = ["--", scope, ":(exclude)%s" % rel] if inside else []
            code, porcelain = git(root, "status", "--porcelain", *pathspec)
            if code != 0:
                print("ERROR: not a git repository: %s" % root)
                return 1
            dirty = porcelain.splitlines()
            if dirty:
                print("ERROR: uncommitted changes; commit the task first:\n  " + "\n  ".join(dirty))
                return 1
            commit = "HEAD"
        sha = head_sha(root, commit)
        if sha is None:
            print("ERROR: commit %s not found" % commit)
            return 1
        for other_id, other in tasks.items():
            if (other_id != tid and other.get("sha") and task_root(root, other) == root
                    and head_sha(root, str(other["sha"])) == sha):
                print("ERROR: %s is already recorded for %s; commit this task first" % (sha, other_id))
                return 1

    def change(lines):
        blocks = item_blocks(lines, "id", tid)
        assert len(blocks) == 1, "expected one '- id: %s' line, found %d" % (tid, len(blocks))
        start, end, indent = blocks[0]
        end += set_key(lines, start, end, indent, "status", value)
        if sha:
            # Quoted: a short sha of octal digits with a leading 0 would load as a number.
            set_key(lines, start, end, indent, "sha", '"%s"' % sha, after="status")
        if data.get("status") == "approved":
            set_top(lines, "status", "building")

    def applied(d):
        task = [t for t in d["tasks"] if t.get("id") == tid][0]
        return task.get("status") == value and (sha is None or str(task.get("sha")) == sha)

    updated = edit(path, text, change, applied)
    if value == "doing":
        print("%s doing" % tid)
        return 0
    print("%s verifying in %s: run its checks (`set <feature> AC<n> pass|fail`)" % (tid, sha))
    ready, _ = frontier([t for t in updated["tasks"] if isinstance(t, dict)])
    if ready:
        print("Next: " + ", ".join("%s %s" % (t.get("id"), t.get("title")) for t, _ in ready))
    else:
        print("All tasks have a commit: run the suite, then `review <feature>`.")
    return 0


def set_check(path, text, data, tasks, ac, value):
    if data.get("status") not in ("building", "review"):
        print("ERROR: feature status is '%s'; checks are recorded while building or in review" % data.get("status"))
        return 1
    open_tasks = [tid for tid, t in tasks.items() if ac in as_list(t.get("covers")) and t.get("status") not in STARTED]
    if open_tasks:
        print("ERROR: %s is covered by task %s, which has no commit yet (`set <feature> T<n> verifying`)"
              % (ac, ", ".join(open_tasks)))
        return 1

    checks = [c for c in as_list(data.get("checks")) if isinstance(c, dict)]
    after = {}
    for c in checks:
        after.setdefault(c.get("ac"), []).append(value if c.get("ac") == ac else c.get("status"))
    passed = {name for name, states in after.items() if all(s == "pass" for s in states)}
    wanted = {}
    for tid, t in tasks.items():
        if t.get("status") in STARTED:
            covers = as_list(t.get("covers"))
            wanted[tid] = "done" if covers and all(c in passed for c in covers) else "verifying"

    def change(lines):
        blocks = item_blocks(lines, "ac", ac)
        assert blocks, "no '- ac: %s' line" % ac
        for start, end, indent in reversed(blocks):
            set_key(lines, start, end, indent, "status", value)
        for tid, state in wanted.items():
            start, end, indent = item_blocks(lines, "id", tid)[0]
            set_key(lines, start, end, indent, "status", state)

    def applied(d):
        by_id = {t.get("id"): t for t in d["tasks"] if isinstance(t, dict)}
        return (all(c.get("status") == value for c in d["checks"] if isinstance(c, dict) and c.get("ac") == ac)
                and all(by_id[tid].get("status") == state for tid, state in wanted.items()))

    edit(path, text, change, applied)
    print("%s %s" % (ac, value))
    for tid, state in wanted.items():
        if tasks[tid].get("status") != state:
            print("%s %s" % (tid, state))
    return 0


# ---------------------------------------------------------------- review and finish

def cmd_review(path, root, specs):
    text, data = load(path)
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
    text, data = load(path)
    if data.get("status") != "review":
        print("ERROR: feature status is '%s'; finish comes after `review`" % data.get("status"))
        return 1
    blockers = finish_blockers(data)
    if blockers:
        print("ERROR: not done yet:\n  " + "\n  ".join(blockers))
        return 1
    planned = dict(data, status="done")
    if report(*validate(planned, root, specs, os.path.dirname(path))):
        return 1
    edit(path, text, lambda lines: set_top(lines, "status", "done"), lambda d: d.get("status") == "done")
    print("%s done" % data.get("id"))
    return 0


# ---------------------------------------------------------------- roadmap

def roadmap_path(specs):
    return os.path.join(specs, "roadmap.yaml")


def load_roadmap(specs):
    path = roadmap_path(specs)
    if not os.path.isfile(path):
        return None
    _, data = load(path)
    return data


def roadmap_features(data):
    """Feature id -> (milestone id, feature dict), in file order."""
    found = {}
    for milestone in as_list(data.get("milestones")):
        if not isinstance(milestone, dict):
            continue
        for feature in as_list(milestone.get("features")):
            if isinstance(feature, dict) and feature.get("id") is not None:
                found.setdefault(str(feature["id"]), (str(milestone.get("id")), feature))
    return found


def linked_features(specs):
    """Roadmap id -> list of (folder name, feature.yaml status)."""
    links = {}
    pattern = os.path.join(specs, "features", "*", "feature.yaml")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and data.get("roadmap") is not None:
            folder = os.path.basename(os.path.dirname(path))
            links.setdefault(str(data["roadmap"]), []).append((folder, data.get("status")))
    return links


def validate_roadmap(data, links):
    errors, warnings = [], []
    err = errors.append
    if not isinstance(data.get("vision"), str) or not data.get("vision").strip():
        err("'vision' is required")
    milestones = as_list(data.get("milestones"))
    if not milestones:
        err("'milestones' needs at least one milestone")

    milestone_ids, feature_ids = {}, {}
    for i, milestone in enumerate(milestones):
        if not isinstance(milestone, dict) or milestone.get("id") is None:
            err("milestones[%d] needs an 'id'" % i)
            continue
        mid = str(milestone["id"])
        if mid in milestone_ids:
            err("milestone id %s is duplicated" % mid)
        milestone_ids[mid] = []
        for key in ("title", "outcome"):
            if not str(milestone.get(key) or "").strip():
                err("%s needs '%s'" % (mid, key))
        features = as_list(milestone.get("features"))
        if not features:
            err("%s needs at least one feature" % mid)
        for j, feature in enumerate(features):
            if not isinstance(feature, dict) or feature.get("id") is None:
                err("%s features[%d] needs an 'id'" % (mid, j))
                continue
            fid = str(feature["id"])
            if fid in feature_ids or fid in milestone_ids:
                err("id %s is duplicated" % fid)
            feature_ids[fid] = feature
            milestone_ids[mid].append(fid)
            for key in ("title", "goal", "done_when"):
                if not str(feature.get(key) or "").strip():
                    err("%s needs '%s'" % (fid, key))

    graph = {}
    for fid, feature in feature_ids.items():
        deps = []
        for dep in as_list(feature.get("blocked_by")):
            dep = str(dep)
            if dep in milestone_ids:
                deps.extend(d for d in milestone_ids[dep] if d != fid)
            elif dep in feature_ids:
                deps.append(dep)
            else:
                err("%s is blocked by unknown id %s" % (fid, dep))
            if dep == fid:
                err("%s is blocked by itself" % fid)
        graph[fid] = {"blocked_by": deps}
    cycle = find_cycle(graph)
    if cycle:
        err("blocked_by cycle: %s" % " -> ".join(cycle))

    for rid, folders in links.items():
        if rid not in feature_ids:
            err("%s links roadmap: %s, which is not in the roadmap" % (folders[0][0], rid))
        if len(folders) > 1:
            err("roadmap feature %s is linked by several features: %s (split it in the roadmap)"
                % (rid, ", ".join(f for f, _ in folders)))
    return errors, warnings, graph


def roadmap_status(rid, links):
    folders = links.get(rid)
    return folders[0][1] if folders else "planned"


def milestone_status(statuses):
    if all(s == "planned" for s in statuses):
        return "planned"
    return "done" if all(s == "done" for s in statuses) else "building"


def sync_roadmap(specs, data=None, links=None):
    """Write the status of every roadmap feature and milestone into roadmap.yaml (nothing when it is invalid)."""
    data = data or load_roadmap(specs)
    if data is None:
        return
    links = links or linked_features(specs)
    if validate_roadmap(data, links)[0]:
        return
    path = roadmap_path(specs)
    text, _ = load(path)
    wanted = {}
    for milestone in as_list(data.get("milestones")):
        fids = [str(f["id"]) for f in as_list(milestone.get("features"))]
        states = [roadmap_status(f, links) for f in fids]
        wanted[str(milestone["id"])] = milestone_status(states)
        wanted.update(zip(fids, states))

    def change(lines):
        for ident, state in wanted.items():
            start, end, indent = item_blocks(lines, "id", ident)[0]
            set_key(lines, start, end, indent, "status", state, after="title")

    edit(path, text, change, lambda d: True)


def cmd_roadmap(specs, approve=False):
    data = load_roadmap(specs)
    if data is None:
        print("ERROR: %s does not exist" % roadmap_path(specs))
        return 1
    links = linked_features(specs)
    errors, warnings, graph = validate_roadmap(data, links)
    for w in warnings:
        print("WARNING: %s" % w)
    for e in errors:
        print("ERROR: %s" % e)
    if errors:
        return 1
    if approve:
        today = datetime.date.today().isoformat()
        text, _ = load(roadmap_path(specs))
        edit(roadmap_path(specs), text, lambda lines: set_top(lines, "approved", today, after="vision"),
             lambda d: str(d.get("approved")) == today)
        print("Roadmap approved %s" % today)

    sync_roadmap(specs, data, links)
    features = roadmap_features(data)
    status = {fid: roadmap_status(fid, links) for fid in features}
    for milestone in as_list(data.get("milestones")):
        fids = [str(f["id"]) for f in as_list(milestone.get("features"))]
        done = sum(1 for f in fids if status[f] == "done")
        print("%s - %s: %d/%d done" % (milestone.get("id"), milestone.get("title"), done, len(fids)))
        for fid in fids:
            folder = links.get(fid, [("", "")])[0][0]
            print("  %-9s %-6s %s%s" % (status[fid], fid, features[fid][1].get("title"),
                                        "  [%s]" % folder if folder else ""))
    ready = [fid for fid in features if status[fid] == "planned"
             and all(status[d] == "done" for d in graph[fid]["blocked_by"])]
    if ready:
        print("Ready to start: " + ", ".join("%s %s" % (f, features[f][1].get("title")) for f in ready))
    elif all(s == "done" for s in status.values()):
        print("Roadmap complete.")
    return 0


# ---------------------------------------------------------------- finding

def cmd_finding(path, args):
    text, data = load(path)
    review = data.get("review") if isinstance(data.get("review"), dict) else {}
    existing = as_list(review.get("findings"))
    if args.none:
        if existing:
            print("ERROR: the review already has %d finding(s)" % len(existing))
            return 1
        item = None
    else:
        if not args.text or not args.action:
            print("ERROR: a finding needs --text and --action (or use --none for a clean review)")
            return 1
        if args.action == "fix" and not args.task:
            print("ERROR: a fix finding names the task that fixes it: --task T<n>")
            return 1
        if args.action == "wontfix" and not args.reason:
            print("ERROR: a wontfix finding needs --reason")
            return 1
        if not args.source:
            print("ERROR: a finding needs --source (%s)" % ", ".join(SOURCES))
            return 1
        if args.source == "pr-comment" and not args.comment_id:
            print("ERROR: a pr-comment finding needs --comment-id")
            return 1
        if args.comment_id and args.source != "pr-comment":
            print("ERROR: --comment-id only goes with --source pr-comment")
            return 1
        if args.comment_id and any(isinstance(f, dict) and str(f.get("comment_id")) == str(args.comment_id)
                                   for f in existing):
            print("ERROR: comment %s is already recorded" % args.comment_id)
            return 1
        item = ["    - text: %s\n" % json.dumps(args.text, ensure_ascii=False),
                "      action: %s\n" % args.action]
        if args.task:
            item.append("      task: %s\n" % args.task)
        if args.reason:
            item.append("      reason: %s\n" % json.dumps(args.reason, ensure_ascii=False))
        item.append("      source: %s\n" % args.source)
        if args.comment_id:
            item.append("      comment_id: %d\n" % args.comment_id)

    def change(lines):
        top = next((i for i, l in enumerate(lines) if re.match(r"^review:(\s|$)", l)), None)
        if top is None:
            lines.append("review:\n")
            top = len(lines) - 1
        elif lines[top].split("#")[0].strip() != "review:":
            lines[top] = "review:\n"
        end = block_end(lines, top, 0)
        found = next((i for i in range(top + 1, end) if re.match(r"^  findings:(\s|$)", lines[i])), None)
        if found is None:
            lines.insert(top + 1, "  findings:\n")
            found = top + 1
        elif lines[found].split("#")[0].strip() != "findings:":
            lines[found] = "  findings:\n" if item else "  findings: []\n"
        if item is None:
            lines[found] = "  findings: []\n"
            return
        lines[block_end(lines, found, 2):block_end(lines, found, 2)] = item

    edit(path, text, change, lambda d: len(as_list((d.get("review") or {}).get("findings"))) ==
         len(existing) + (0 if item is None else 1))
    print("%s: %s" % (data.get("id"), "clean review recorded" if item is None else "finding recorded"))
    return 0


# ---------------------------------------------------------------- pr

def cmd_pr(path, url):
    if not re.match(r"^https?://\S+$", url):
        print("ERROR: --url must be the pull request URL")
        return 1
    text, data = load(path)
    edit(path, text, lambda lines: set_top(lines, "pr", url), lambda d: d.get("pr") == url)
    print("%s: pr recorded" % data.get("id"))
    return 0


# ---------------------------------------------------------------- new

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
    os.makedirs(folder)
    with open(os.path.join(folder, "feature.yaml"), "w", encoding="utf-8", newline="") as fh:
        fh.write(yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, default_flow_style=None))
    template = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "templates", "spec.md")
    with open(template, encoding="utf-8") as fh:
        spec = fh.read().replace("{title}", args.title)
    with open(os.path.join(folder, "spec.md"), "w", encoding="utf-8", newline="") as fh:
        fh.write(spec)
    sync_roadmap(specs)
    print("Created %s: write the criteria in spec.md and feature.yaml, then `check`" % folder)
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="git repository of the task commits (default: current directory)")
    parser.add_argument("--specs", help="folder holding roadmap.yaml and features/ (default: <root>/.specs)")
    sub = parser.add_subparsers(dest="command")
    sub.required = True
    for name in ("status", "check", "review", "finish"):
        sub.add_parser(name).add_argument("feature")
    approve = sub.add_parser("approve")
    approve.add_argument("feature")
    approve.add_argument("step", choices=("spec", "tasks"))
    set_ = sub.add_parser("set")
    set_.add_argument("feature")
    set_.add_argument("target", help="a task id (T1) or a criterion id (AC1)")
    set_.add_argument("value", help="doing | verifying for a task, pass | fail for a criterion")
    set_.add_argument("--commit", help="with verifying: record this commit instead of HEAD (for resume)")
    roadmap = sub.add_parser("roadmap")
    roadmap.add_argument("--approve", action="store_true", help="stamp today as the approval date, once the roadmap is valid")
    finding = sub.add_parser("finding")
    finding.add_argument("feature")
    finding.add_argument("--text")
    finding.add_argument("--action", choices=("fix", "wontfix"))
    finding.add_argument("--task", help="with fix: the task that fixes it")
    finding.add_argument("--reason", help="with wontfix: why, as the user agreed")
    finding.add_argument("--none", action="store_true", help="record a clean review (findings: [])")
    finding.add_argument("--source", choices=SOURCES, help="where the finding comes from")
    finding.add_argument("--comment-id", type=int, help="with pr-comment: the id of the PR comment")
    pr = sub.add_parser("pr")
    pr.add_argument("feature")
    pr.add_argument("--url", required=True, help="the pull request that delivers the feature")
    new = sub.add_parser("new")
    new.add_argument("feature", help="the folder name and id, e.g. F1.1-csv-export")
    new.add_argument("--title", required=True)
    new.add_argument("--size", required=True, choices=SIZES)
    new.add_argument("--roadmap", help="the roadmap feature id this delivers")
    new.add_argument("--repo", help="repo name, when the work is a /task story")
    new.add_argument("--decisions", help="task decisions it builds on, comma separated")
    new.add_argument("--validations", help="task validations that prove it, comma separated")
    new.add_argument("--test", help="the whole-suite command")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    specs = os.path.abspath(args.specs) if args.specs else default_specs(root)
    if args.command == "roadmap":
        return cmd_roadmap(specs, args.approve)
    if args.command == "new":
        return cmd_new(specs, args)
    path = resolve(args.feature, specs)
    if args.command == "finding":
        return cmd_finding(path, args)
    if args.command == "pr":
        return cmd_pr(path, args.url)
    if args.command == "approve":
        code = cmd_approve(path, root, specs, args.step)
    elif args.command == "set":
        code = cmd_set(path, root, specs, args.target, args.value, args.commit)
    else:
        code = {"status": cmd_status, "check": cmd_check, "review": cmd_review,
                "finish": cmd_finish}[args.command](path, root, specs)
    if code == 0 and args.command in ("approve", "set", "review", "finish"):
        sync_roadmap(specs)
    return code


if __name__ == "__main__":
    sys.exit(main())
