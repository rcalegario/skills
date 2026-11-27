"""state.py - the state of each task, as the task skill's status.py computes it.

status.py is loaded once from this repo (skills/task/scripts); each call re-reads the task folders,
so a row always reflects the files on disk. A folder that makes status.py fail gets an error row
instead of hiding the others.
"""
import collections
import datetime
import importlib.util
import os

import detail
import docs
import graph
import home as homemod
import summary

STATUS_PY = os.path.join(homemod.REPO, "skills", "task", "scripts", "status.py")
_status = None


def status_module():
    global _status
    if _status is None:
        spec = importlib.util.spec_from_file_location("task_status", STATUS_PY)
        _status = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_status)
    return _status


def collect(path):
    """status.py's Task for one task folder and its collect(), after its checks."""
    task = status_module().Task(path)
    task.check()
    return task, task.collect()


def last_activity(path):
    """The newest modification time of the task's own files; the worktrees under repos/ are not the task's."""
    newest = None
    for root, dirs, files in os.walk(path):
        if os.path.normcase(os.path.abspath(root)) == os.path.normcase(os.path.abspath(path)):
            dirs[:] = [d for d in dirs if d != "repos"]
        for name in files:
            mtime = os.path.getmtime(os.path.join(root, name))
            newest = mtime if newest is None or mtime > newest else newest
    return datetime.datetime.fromtimestamp(newest).isoformat(timespec="seconds") if newest else None


def last_note(journal):
    notes = [n for n in journal if isinstance(n, dict)]
    if not notes:
        return None
    note = notes[-1]
    return {"id": note.get("id"), "date": str(note.get("date")), "text": note.get("text")}


def progress(task, data):
    """What the macro view shows of one task without a second call."""
    by_status = collections.Counter(item["status"] for item in data["items"])
    decisions = collections.Counter(dec.get("status") for dec in task.decisions.values())
    return {
        "items": {"total": len(data["items"]), "by_status": dict(by_status)},
        "features": {"done": sum(f["status"] == "done" for f in data["features"]), "total": len(data["features"])},
        "decisions": {"open": decisions["open"], "proposed": decisions["proposed"]},
        "pending_open": sum(isinstance(p, dict) and p.get("status") == "open" for p in task.pending),
        "last_note": last_note(task.journal),
        "open_requirements": [{k: req[k] for k in ("id", "item", "text", "status", "missing")}
                              for req in data["requirements"] if req["status"] != "concluded"],
    }


def task_row(home, folder):
    rel = os.path.relpath(folder.path, home).replace(os.sep, "/")
    row = {"repo": folder.repo, "id": folder.id, "path": rel, "legacy": folder.legacy}
    if folder.legacy:
        return row
    try:
        task, data = collect(folder.path)
    except (Exception, SystemExit) as exc:  # status.py exits on invalid YAML
        row.update(title=None, step=None, counts=None, error=str(exc) or type(exc).__name__)
        return row
    return full_row(row, folder, task, data)


def full_row(row, folder, task, data):
    row.update(title=data["task"]["title"], step=data["step"], reason=summary.reason(data["step"], data["failures"]),
               counts={"failures": len(data["failures"]), "warnings": len(data["warnings"])}, error=None,
               last_activity=last_activity(folder.path), **progress(task, data))
    return row


def task_detail(home, repo, task_id):
    """Everything of one task for its page; None for an unknown, legacy or broken task."""
    folder = current_folder(home, repo, task_id)
    if folder is None:
        return None
    try:
        task, data = collect(folder.path)
    except (Exception, SystemExit):
        return None
    rel = os.path.relpath(folder.path, home).replace(os.sep, "/")
    row = full_row({"repo": folder.repo, "id": folder.id, "path": rel, "legacy": False}, folder, task, data)
    return {"row": row, "status": data, "graph": graph.build(task, data), "docs": docs.listing(folder.path),
            "next": summary.next_actions(data["step"], titles(task, data), roadmap_ids(data)),
            "checks": summary.check_groups(data["failures"], data["warnings"]),
            **detail.read(task)}


def titles(task, data):
    """The task's title for each id a blocker can name: roadmap features, features, items, decisions, validations."""
    out = {}
    for ms in data["roadmap"]:
        out.update((f["id"], f.get("title")) for f in ms.get("features", []))
    out.update((f["id"], f.get("title")) for f in data["features"])
    out.update((i["id"], i.get("text")) for i in data["items"])
    for by_id in (task.decisions, task.validations):
        out.update((ident, entry.get("title")) for ident, entry in by_id.items())
    return {k: v for k, v in out.items() if v}


def roadmap_ids(data):
    """Each feature folder with the roadmap feature it builds."""
    return {f["id"]: f["roadmap"] for f in data["features"] if f.get("roadmap")}


def current_folder(home, repo, task_id):
    """The home's task folder with this repo and id, or None for an unknown or legacy one.

    The task is looked up among the home's task folders, never built from the names given,
    so no name reaches outside <home>/tasks.
    """
    folder = next((f for f in homemod.task_folders(home) if f.repo == repo and f.id == task_id), None)
    return None if folder is None or folder.legacy else folder


def task_doc(home, repo, task_id, rel):
    """The text of one listed Markdown file of a task; None for an unknown or legacy task or an unlisted file."""
    folder = current_folder(home, repo, task_id)
    return docs.text(folder.path, rel) if folder else None


def task_rows(home):
    return [task_row(home, f) for f in homemod.task_folders(home)]


def snapshot(home):
    """The /api/tasks payload: the home, when it was read, and one row per task."""
    return {"home": os.path.abspath(home).replace(os.sep, "/"),
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "tasks": task_rows(home)}
