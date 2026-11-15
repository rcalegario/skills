#!/usr/bin/env python3
"""spec-lite state tool: reads and changes .specs/ROADMAP.yaml and each feature's tasks.yaml.

Run `specs.py --help` for the commands. Exit code 0 = ok, 1 = a problem was reported.
"""
import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing. Install it: python3 -m pip install --user --break-system-packages pyyaml")

FEATURE_STATUSES = ["todo", "spec", "tasks", "doing", "done"]
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
AC_LINE_RE = re.compile(r"^\s*[-*]\s*\**(AC\d+)\**\s*[:\-–]\s*(.*)$")
AC_SHAPE_RE = re.compile(r"^(?:(?:WHEN|IF|WHILE)\b.*\bTHEN\b.+|ALWAYS\b.+)$")
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


class Problem(Exception):
    """A user-facing error: printed, exit 1."""


# ---------- yaml io ----------

class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _repr_list(dumper, data):
    flow = all(isinstance(x, (str, int)) for x in data) and len(data) <= 8
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _repr_list)


def load(path):
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise Problem(f"{path}: invalid YAML: {e}")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100))


# ---------- roadmap ----------

class Roadmap:
    def __init__(self, root):
        self.root = root
        self.path = root / ".specs" / "ROADMAP.yaml"
        if not self.path.exists():
            raise Problem(f"No {self.path}. Start with: specs.py init <project-name>")
        self.data = load(self.path)
        self.data.setdefault("milestones", [])

    def save(self):
        save(self.path, self.data)

    @property
    def milestones(self):
        return self.data["milestones"] or []

    def milestone(self, mid):
        for m in self.milestones:
            if m.get("id") == mid:
                return m
        raise Problem(f"Milestone {mid} is not in the roadmap. Existing: {[m.get('id') for m in self.milestones]}")

    def features(self):
        for m in self.milestones:
            for f in m.get("features") or []:
                yield m, f

    def problems(self):
        out = []
        seen_m, seen_f = set(), set()
        if not self.data.get("project"):
            out.append("ROADMAP.yaml: missing 'project'")
        for m in self.milestones:
            mid = m.get("id")
            if not re.fullmatch(r"m[1-9]\d*", str(mid)):
                out.append(f"milestone id '{mid}' must look like m1, m2, ...")
            if mid in seen_m:
                out.append(f"duplicate milestone id {mid}")
            seen_m.add(mid)
            if not m.get("title"):
                out.append(f"{mid}: missing 'title'")
            for f in m.get("features") or []:
                fid = f.get("id")
                if not re.fullmatch(rf"{mid}\.f[1-9]\d*", str(fid)):
                    out.append(f"feature id '{fid}' must be {mid}.f<N> (it sits under milestone {mid})")
                if fid in seen_f:
                    out.append(f"duplicate feature id {fid}")
                seen_f.add(fid)
                if not SLUG_RE.match(str(f.get("slug", ""))):
                    out.append(f"{fid}: slug '{f.get('slug')}' must be kebab-case")
                if not f.get("title"):
                    out.append(f"{fid}: missing 'title'")
                if f.get("status") not in FEATURE_STATUSES:
                    out.append(f"{fid}: status '{f.get('status')}' must be one of {FEATURE_STATUSES}")
        return out

    def resolve(self, key):
        """Return (feature dict, folder path) for 'm1.f2' or 'm1.f2.slug'."""
        for _, f in self.features():
            if key in (f.get("id"), f"{f.get('id')}.{f.get('slug')}"):
                return f, self.root / ".specs" / "features" / f"{f['id']}.{f['slug']}"
        raise Problem(f"Feature {key} is not in the roadmap. Run: specs.py status")


# ---------- spec.md ----------

def read_criteria(spec_path):
    """Return ([(ac_id, text)], problems)."""
    if not spec_path.exists():
        return [], [f"{spec_path} is missing"]
    criteria, problems, seen = [], [], set()
    text = spec_path.read_text()
    for line in text.splitlines():
        m = AC_LINE_RE.match(line)
        if not m:
            continue
        ac, body = m.group(1), m.group(2).strip()
        if ac in seen:
            problems.append(f"spec.md: duplicate {ac}")
        seen.add(ac)
        criteria.append((ac, body))
        if body.startswith("TODO"):
            continue
        if not AC_SHAPE_RE.match(body):
            problems.append(f"spec.md: {ac} must read 'WHEN/IF/WHILE ... THEN ...' or 'ALWAYS ...': {body!r}")
    if not criteria:
        problems.append("spec.md: no acceptance criteria (lines like '- **AC1**: WHEN ... THEN ...')")
    if re.search(r"\bTODO\b", re.sub(r"<!--.*?-->", "", text, flags=re.S)):
        problems.append("spec.md: still has TODO placeholders from the template")
    return criteria, problems


# ---------- tasks.yaml ----------

TASK_STATUSES = ["todo", "doing", "done"]
CHECK_STATUSES = ["pending", "pass", "fail"]


def is_blank(v):
    return not isinstance(v, str) or not v.strip() or v.strip().startswith("TODO")


def tasks_problems(path, ac_ids):
    if not path.exists():
        return [f"{path.name} is missing"]
    data = load(path)
    out = []
    tasks = data.get("tasks") or []
    checks = data.get("checks") or []
    if is_blank(data.get("test")):
        out.append("'test' must hold the command that runs the whole suite")
    if not tasks:
        out.append("tasks.yaml: no tasks")
    by_id = {}
    for t in tasks:
        tid = t.get("id")
        if not re.fullmatch(r"T[1-9]\d*", str(tid)):
            out.append(f"task id '{tid}' must look like T1, T2, ...")
        if tid in by_id:
            out.append(f"duplicate task {tid}")
        by_id[tid] = t
        if is_blank(t.get("title")):
            out.append(f"{tid}: missing title")
        if is_blank(t.get("commit")):
            out.append(f"{tid}: missing commit message")
        if t.get("status") not in TASK_STATUSES:
            out.append(f"{tid}: status '{t.get('status')}' must be one of {TASK_STATUSES}")
        if not t.get("covers"):
            out.append(f"{tid}: covers no AC")
        for ac in t.get("covers") or []:
            if ac not in ac_ids:
                out.append(f"{tid}: covers {ac}, which is not in spec.md")
    for t in tasks:
        for b in t.get("blocked_by") or []:
            if b not in by_id:
                out.append(f"{t.get('id')}: blocked_by {b}, which does not exist")
            elif t.get("status") == "done" and by_id[b].get("status") != "done":
                out.append(f"{t.get('id')} is done but its blocker {b} is not")
    cycle = find_cycle(by_id)
    if cycle:
        out.append(f"blocked_by cycle: {' -> '.join(cycle)}")
    covered = {ac for t in tasks for ac in t.get("covers") or []}
    checked = set()
    for c in checks:
        ac = c.get("ac")
        if ac not in ac_ids:
            out.append(f"check for {ac}, which is not in spec.md")
        checked.add(ac)
        kinds = [k for k in ("test", "manual") if c.get(k) is not None]
        if len(kinds) != 1:
            out.append(f"check {ac}: needs exactly one of 'test' or 'manual'")
        elif is_blank(c[kinds[0]]):
            out.append(f"check {ac}: '{kinds[0]}' is empty or TODO")
        if c.get("status") not in CHECK_STATUSES:
            out.append(f"check {ac}: status '{c.get('status')}' must be one of {CHECK_STATUSES}")
    for ac in ac_ids:
        if ac not in covered:
            out.append(f"{ac} is covered by no task")
        if ac not in checked:
            out.append(f"{ac} has no check")
    return [p if p.startswith("tasks.yaml") else f"tasks.yaml: {p}" for p in out]


def find_cycle(by_id):
    state = {}

    def visit(n, path):
        if state.get(n) == 1:
            return path[path.index(n):] + [n]
        if state.get(n) == 2 or n not in by_id:
            return None
        state[n] = 1
        for b in by_id[n].get("blocked_by") or []:
            c = visit(b, path + [n])
            if c:
                return c
        state[n] = 2
        return None

    for n in by_id:
        c = visit(n, [])
        if c:
            return c
    return None


def tasks_skeleton(f, criteria):
    return {
        "feature": f"{f['id']}.{f['slug']}",
        "test": "TODO: the command that runs the whole suite",
        "tasks": [{"id": "T1", "title": "TODO", "covers": [ac for ac, _ in criteria],
                   "blocked_by": [], "commit": "TODO", "status": "todo"}],
        "checks": [{"ac": ac, "test": "TODO: test file > test name, or replace with manual: <steps>",
                    "status": "pending"} for ac, _ in criteria],
    }


def feature_problems(rm, f, folder):
    if f["status"] == "todo":
        return []
    criteria, problems = read_criteria(folder / "spec.md")
    if f["status"] in ("tasks", "doing", "done"):
        problems += tasks_problems(folder / "tasks.yaml", [ac for ac, _ in criteria])
    if f["status"] == "done" and not problems:
        problems += unfinished(load(folder / "tasks.yaml"))
    return problems


def unfinished(data):
    out = [f"{t['id']} is '{t['status']}', not done" for t in data["tasks"] if t["status"] != "done"]
    out += [f"check {c['ac']} is '{c['status']}', not pass" for c in data["checks"] if c["status"] != "pass"]
    return out


def next_task(data):
    done = {t["id"] for t in data.get("tasks") or [] if t.get("status") == "done"}
    for t in data.get("tasks") or []:
        if t.get("status") != "done" and set(t.get("blocked_by") or []) <= done:
            return t
    return None


def load_tasks(rm, key, need_status="doing"):
    f, folder = rm.resolve(key)
    if need_status and f["status"] != need_status:
        raise Problem(f"{f['id']} is '{f['status']}'; this needs status {need_status} "
                      f"(approve the tasks first: specs.py approve {f['id']} tasks)")
    problems = feature_problems(rm, f, folder)
    if problems:
        report(problems)
    path = folder / "tasks.yaml"
    return f, path, load(path)


def today():
    return datetime.date.today().isoformat()


# ---------- commands ----------

def cmd_init(root, args):
    path = root / ".specs" / "ROADMAP.yaml"
    if path.exists():
        raise Problem(f"{path} already exists")
    save(path, {"project": args.project, "milestones": []})
    print(f"Created {path}")


def cmd_milestone(root, args):
    rm = Roadmap(root)
    n = max([int(m["id"][1:]) for m in rm.milestones if re.fullmatch(r"m\d+", str(m.get("id")))] or [0]) + 1
    m = {"id": f"m{n}", "title": args.title}
    if args.goal:
        m["goal"] = args.goal
    m["features"] = []
    rm.data["milestones"].append(m)
    rm.save()
    print(f"Added milestone m{n}: {args.title}")


def cmd_add(root, args):
    rm = Roadmap(root)
    m = rm.milestone(args.milestone)
    if not SLUG_RE.match(args.slug):
        raise Problem(f"slug '{args.slug}' must be kebab-case (e.g. export-csv)")
    feats = m.setdefault("features", []) or []
    m["features"] = feats
    nums = [int(str(f.get("id", "")).rsplit(".f", 1)[-1]) for f in feats
            if re.fullmatch(rf"{m['id']}\.f\d+", str(f.get("id")))]
    fid = f"{m['id']}.f{max(nums or [0]) + 1}"
    feats.append({"id": fid, "slug": args.slug, "title": args.title, "status": "todo"})
    rm.save()
    print(f"Added {fid} ({args.slug}): {args.title}")


def cmd_start(root, args):
    rm = Roadmap(root)
    f, folder = rm.resolve(args.feature)
    if f["status"] != "todo":
        raise Problem(f"{f['id']} is '{f['status']}'; start needs status todo")
    spec = folder / "spec.md"
    if not spec.exists():
        folder.mkdir(parents=True, exist_ok=True)
        spec.write_text((TEMPLATES / "spec.md").read_text().replace("{title}", f["title"]))
    f["status"] = "spec"
    rm.save()
    print(f"{f['id']} -> spec. Write {spec.relative_to(root)}")


def cmd_approve(root, args):
    rm = Roadmap(root)
    f, folder = rm.resolve(args.feature)
    need = {"spec": "spec", "tasks": "tasks"}[args.what]
    if f["status"] != need:
        raise Problem(f"{f['id']} is '{f['status']}'; approving the {args.what} needs status {need}")
    problems = feature_problems(rm, f, folder)
    if problems:
        report(problems)
    f.setdefault("approved", {})[args.what] = today()
    f["status"] = {"spec": "tasks", "tasks": "doing"}[args.what]
    rm.save()
    print(f"{f['id']}: {args.what} approved -> {f['status']}")
    tasks = folder / "tasks.yaml"
    if args.what == "spec" and not tasks.exists():
        criteria, _ = read_criteria(folder / "spec.md")
        save(tasks, tasks_skeleton(f, criteria))
        print(f"Wrote {tasks.relative_to(root)}: fill the TODOs, then specs.py check {f['id']}")
    if args.what == "tasks":
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
        if head.returncode == 0:
            data = load(tasks)
            data["base"] = head.stdout.strip()
            save(tasks, data)
            print(f"base {data['base'][:8]} recorded: the review compares against it")


def cmd_set(root, args):
    rm = Roadmap(root)
    f, path, data = load_tasks(rm, args.feature)
    if args.item.startswith("T"):
        if args.status not in TASK_STATUSES:
            raise Problem(f"task status '{args.status}' must be one of {TASK_STATUSES}")
        by_id = {t["id"]: t for t in data["tasks"]}
        if args.item not in by_id:
            raise Problem(f"{args.item} is not in tasks.yaml. Tasks: {list(by_id)}")
        if args.status == "done":
            open_ = [b for b in by_id[args.item].get("blocked_by") or [] if by_id[b]["status"] != "done"]
            if open_:
                raise Problem(f"{args.item} is blocked by {open_}, not done yet")
        by_id[args.item]["status"] = args.status
    else:
        if args.status not in CHECK_STATUSES:
            raise Problem(f"check status '{args.status}' must be one of {CHECK_STATUSES}")
        hits = [c for c in data["checks"] if c["ac"] == args.item]
        if not hits:
            raise Problem(f"no check for {args.item} in tasks.yaml")
        for c in hits:
            c["status"] = args.status
    save(path, data)
    print(f"{f['id']} {args.item} -> {args.status}")


def cmd_commit_msg(root, args):
    rm = Roadmap(root)
    _, _, data = load_tasks(rm, args.feature, need_status=None)
    for t in data["tasks"]:
        if t["id"] == args.task:
            print(t["commit"])
            return
    raise Problem(f"{args.task} is not in tasks.yaml")


def cmd_finish(root, args):
    rm = Roadmap(root)
    f, _, data = load_tasks(rm, args.feature)
    left = unfinished(data)
    if left:
        report(left)
    f["status"] = "done"
    f["done"] = today()
    rm.save()
    print(f"{f['id']} -> done")


def cmd_status(root, args):
    rm = Roadmap(root)
    print(rm.data.get("project", "?"))
    for m in rm.milestones:
        print(f"\n{m['id']}  {m.get('title', '')}")
        for f in m.get("features") or []:
            line = f"  {f['id']:<8} {f['status']:<6} {f['slug']}"
            path = rm.root / ".specs" / "features" / f"{f['id']}.{f['slug']}" / "tasks.yaml"
            if f["status"] in ("doing", "done") and path.exists():
                data = load(path)
                tasks, checks = data.get("tasks") or [], data.get("checks") or []
                n_done = sum(t.get("status") == "done" for t in tasks)
                n_pass = sum(c.get("status") == "pass" for c in checks)
                line += f"  tasks {n_done}/{len(tasks)}  checks {n_pass}/{len(checks)}"
                nxt = next_task(data)
                if f["status"] == "doing":
                    line += f"  next: {nxt['id']} {nxt['title']}" if nxt else "  next: validate, then finish"
            print(line)


def cmd_check(root, args):
    rm = Roadmap(root)
    problems = rm.problems()
    if args.feature:
        f, folder = rm.resolve(args.feature)
        problems += feature_problems(rm, f, folder)
    report(problems)


def report(problems):
    if problems:
        print("Problems:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("OK")


# ---------- cli ----------

def find_root(start):
    for d in [start, *start.parents]:
        if (d / ".specs").is_dir():
            return d
    return start


def main(argv=None):
    p = argparse.ArgumentParser(prog="specs.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, help="project root (default: nearest folder with .specs/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create .specs/ROADMAP.yaml")
    s.add_argument("project")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("milestone", help="append a milestone (next mN)")
    s.add_argument("title")
    s.add_argument("--goal")
    s.set_defaults(fn=cmd_milestone)

    s = sub.add_parser("add", help="append a feature to a milestone (next mN.fN), status todo")
    s.add_argument("milestone")
    s.add_argument("slug")
    s.add_argument("title")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("start", help="create the feature folder and spec.md; todo -> spec")
    s.add_argument("feature")
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("approve", help="record the user's approval: spec (spec -> tasks) or tasks (tasks -> doing)")
    s.add_argument("feature")
    s.add_argument("what", choices=["spec", "tasks"])
    s.set_defaults(fn=cmd_approve)

    s = sub.add_parser("set", help="set a task (T1: todo|doing|done) or a check (AC1: pending|pass|fail)")
    s.add_argument("feature")
    s.add_argument("item")
    s.add_argument("status")
    s.set_defaults(fn=cmd_set)

    s = sub.add_parser("commit-msg", help="print a task's prepared commit message")
    s.add_argument("feature")
    s.add_argument("task")
    s.set_defaults(fn=cmd_commit_msg)

    s = sub.add_parser("finish", help="doing -> done, once every task is done and every check passes")
    s.add_argument("feature")
    s.set_defaults(fn=cmd_finish)

    s = sub.add_parser("status", help="show the roadmap with progress and each feature's next task")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("check", help="validate the roadmap, and a feature's files if given")
    s.add_argument("feature", nargs="?")
    s.set_defaults(fn=cmd_check)

    args = p.parse_args(argv)
    root = (args.root or find_root(Path.cwd())).resolve()
    try:
        args.fn(root, args)
    except Problem as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
