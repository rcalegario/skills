"""progress.py - the `set` command of /flow: a task's state (doing, verifying with its commit) and the
result of a criterion's checks, which turns the tasks covering it done."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from lib.yamlio import as_list, load_mapping  # noqa: E402
from lib.gitutil import git, head_sha  # noqa: E402
from lib.yamledit import edit, item_blocks, set_key, set_top  # noqa: E402
from feature import STARTED, frontier, missing_repo, task_root  # noqa: E402


def cmd_set(path, root, specs, target, value, commit):
    text, data = load_mapping(path)
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
        repo_error = missing_repo(root, tid, tasks[tid])
        if repo_error:
            print("ERROR: " + repo_error)
            return 1
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
        expected = str(tasks[tid].get("commit") or "").strip().splitlines()
        if commit == "HEAD" and expected:
            _, subject = git(root, "log", "-1", "--format=%s", sha)
            if subject.strip() != expected[0].strip():
                print('ERROR: HEAD %s is "%s", but %s commits as "%s": commit this task first, '
                      "or pass --commit <sha> with its commit" % (sha, subject.strip(), tid, expected[0].strip()))
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
