"""home.py - where the home is, and which folders under <home>/tasks/<repo>/ are tasks.

A task folder holds an acs.yaml, or is legacy. A legacy one (the format before the task skill's decisions/ folder)
holds diario.yaml or decisoes/ and no decisions/.
"""
import collections
import os
import sys

import yaml

TOOL = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(TOOL))
TASK_CONFIG = os.path.join(REPO, "skills", "task", "config.yaml")
NO_HOME = "no home: pass --home or set home in skills/task/config.yaml"

TaskFolder = collections.namedtuple("TaskFolder", "repo id path legacy")


def resolve_home(given, config=TASK_CONFIG):
    """The home to read: --home when given, else `home:` of the task skill's config; exit 2 without one."""
    if given:
        return given
    data = {}
    if os.path.isfile(config):
        with open(config, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    home = data.get("home") if isinstance(data, dict) else None
    if not home:
        sys.stderr.write(NO_HOME + "\n")
        raise SystemExit(2)
    return os.path.expanduser(str(home))


def is_legacy(path):
    has = lambda name: os.path.exists(os.path.join(path, name))  # noqa: E731
    return (has("diario.yaml") or has("decisoes")) and not has("decisions")


def task_folders(home):
    """Every task folder under <home>/tasks/<repo>/, sorted by repo then folder name."""
    tasks = os.path.join(home, "tasks")
    found = []
    if not os.path.isdir(tasks):
        return found
    for repo in sorted(os.listdir(tasks)):
        repo_dir = os.path.join(tasks, repo)
        if not os.path.isdir(repo_dir):
            continue
        for name in sorted(os.listdir(repo_dir)):
            path = os.path.join(repo_dir, name)
            if os.path.isfile(os.path.join(path, "acs.yaml")) or is_legacy(path):
                found.append(TaskFolder(repo, name, path, is_legacy(path)))
    return found
