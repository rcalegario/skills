"""detail.py - one task folder read whole, for its own page.

status.py's Task already loads the decisions, validations, features, pending items and journal; this module
turns them into plain data (dates as text) and adds what status.py does not read: each feature's review.yaml.
"""
import datetime
import os

import yaml


def plain(value):
    """YAML data as JSON-ready data: dates become ISO text, mappings and lists are copied."""
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def entries(by_id):
    """A decisions/ or validations/ folder as a list, each entry with the name of its file."""
    out = []
    for data in by_id.values():
        entry = plain({k: v for k, v in data.items() if k != "_file"})
        entry["file"] = data.get("_file")
        out.append(entry)
    return out


def review(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return plain(yaml.safe_load(fh))


def features(task):
    """Each feature.yaml with its folder name and its review.yaml (None before the review)."""
    out = []
    for folder, data in task.features.items():
        feature = plain(data)
        feature["folder"] = folder
        feature["review"] = review(task.path(".specs", "features", folder, "review.yaml"))
        out.append(feature)
    return out


def read(task):
    """What the task page shows beyond collect(): every file of the folder, whole."""
    fm = task.readme()
    return {
        "readme": plain({"title": fm.get("title"), "link": fm.get("link"), "repos": task.repos()}),
        "decisions": entries(task.decisions),
        "validations": entries(task.validations),
        "features": features(task),
        "pending": plain([p for p in task.pending if isinstance(p, dict)]),
        "journal": plain([n for n in task.journal if isinstance(n, dict)]),
    }
