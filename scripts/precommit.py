"""Runs the tests a commit can affect, several suites at once. Started by .githooks/pre-commit.

Usage: python scripts/precommit.py [--root DIR] < staged paths, one per line

Selection: scripts/ staged runs the scripts suite, a staged skill or tool runs its suite, a
staged lib/<m>.py runs lib's test.cmd and the suites importing it, and any other staged lib/ file
runs lib's test.cmd and every skill's and tool's suite. Up to
SKILLS_PRECOMMIT_JOBS suites run at once (default 4). Only failing suites are printed, each one
whole. Suites on xdist (-n auto) get CPUs // pool workers each, through
PYTEST_XDIST_AUTO_NUM_WORKERS, so the suites at once do not start more processes than the machine
has CPUs; a preset value wins.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPTS_CMD = ("uv run -q --no-project --with pytest --with pytest-xdist --with pyyaml"
               " python -m pytest -q -n auto scripts")
DEFAULT_JOBS = 4
LIB_MODULE = re.compile(r"^lib/(\w+)\.py$")
# "skills", "task", "scripts" or skills/task/scripts: code loading another skill's scripts by path
SCRIPTS_PATH = re.compile(r"""skills['"\s,/\\]+([\w-]+)['"\s,/\\]+scripts\b""")


def skill_test_cmds(root):
    """Every own skill's test command, from one skills.py call with this interpreter (no uv start)."""
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "skills.py"), "--root", str(root), "test-cmds"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    if out.returncode != 0:
        raise SystemExit("pre-commit: skills.py test-cmds failed\n" + out.stdout + out.stderr)
    return json.loads(out.stdout)


def touched_folders(staged, area):
    """Names of the folders under area/ that hold a staged file."""
    return sorted({p.split("/")[1] for p in staged if p.startswith(area + "/") and p.count("/") >= 2})


def folder_names(folder):
    if not folder.is_dir():
        return []
    return sorted(d.name for d in folder.iterdir() if d.is_dir() and not d.name.startswith("."))


def imports_of(text, package=""):
    """The modules a Python source imports anywhere in it, dotted: import a.b gives a.b, from a
    import x gives a and a.x (x may be a module of a), and a bare import lib or from lib import *
    gives lib.*. A relative import resolves against package. None when the source does not parse."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update("lib.*" if alias.name == "lib" else alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ".".join(p for p in (package if node.level else "", node.module or "") if p)
            found.add(base)
            found.update(".".join(p for p in (base, alias.name) if p) for alias in node.names)
    return found - {""}


def uses_lib(imports, modules):
    """Whether the imports (from imports_of) reach one of the lib modules. A source that does not
    parse, a bare import lib or from lib import * reaches them all."""
    if imports is None:
        return True
    used = {name.split(".")[1] for name in imports if name.startswith("lib.")}
    return "*" in used or bool(used & modules)


def staged_lib_modules(staged):
    """The lib modules among the staged lib/ files, or None when any of them is not a module."""
    matches = [LIB_MODULE.match(p) for p in staged if p.startswith("lib/")]
    if not all(m and m.group(1) != "__init__" for m in matches):
        return None
    return {m.group(1) for m in matches}


def top_level_imports(imports):
    """The top-level names of the imports (from imports_of), to find code using another skill's scripts."""
    return {name.split(".")[0] for name in imports or ()}


def read_py(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


def folder_sources(root):
    """Each skill and tool folder, as (area, name), mapped to the text of its .py files."""
    sources = {}
    for area in ("skills", "tools"):
        for name in folder_names(root / area):
            folder = root / area / name
            sources[(area, name)] = [
                read_py(py) for py in sorted(folder.rglob("*.py"))
                if not any(part.startswith(".") or part == "__pycache__" for part in py.relative_to(folder).parts)
            ]
    return sources


def with_lib_importers(root, modules):
    """The modules plus every lib module that imports one of them, directly or through another."""
    lib_imports = {py.stem: imports_of(read_py(py), "lib") for py in (root / "lib").glob("*.py")}
    modules = set(modules)
    while True:
        more = {m for m, imports in lib_imports.items() if m not in modules and uses_lib(imports, modules)}
        if not more:
            return modules
        modules |= more


def skills_used(root, sources, parsed):
    """Each folder, as (area, name), mapped to the other skills whose scripts/ its code uses: by
    importing one of their modules by name (one its own scripts/ lacks) or by naming the folder in a path."""
    script_modules = {name: {py.stem for py in (root / "skills" / name / "scripts").glob("*.py")}
                      for area, name in sources if area == "skills"}
    used = {}
    for (area, name), texts in sources.items():
        own = script_modules[name] if area == "skills" else set()
        imports = set().union(*map(top_level_imports, parsed[(area, name)]))
        paths = set().union(*(SCRIPTS_PATH.findall(text) for text in texts))
        used[(area, name)] = {skill for skill, modules in script_modules.items()
                              if (area, name) != ("skills", skill) and ((modules - own) & imports or skill in paths)}
    return used


def lib_users(root, modules):
    """The skill and tool folders, as {"skills": names, "tools": names}, whose code can break when the
    lib modules change: a .py importing one of them (through other lib modules too), or using a skill
    that does, by importing a module of its scripts/ or by naming that folder in a path."""
    modules = with_lib_importers(root, modules)
    sources = folder_sources(root)
    parsed = {key: [imports_of(text) for text in texts] for key, texts in sources.items()}
    users = {key for key, found in parsed.items() if any(uses_lib(imports, modules) for imports in found)}
    used = skills_used(root, sources, parsed)
    while True:
        broken = {name for area, name in users if area == "skills"}
        more = {key for key in sources if key not in users and used[key] & broken}
        if not more:
            return {area: {name for a, name in users if a == area} for area in ("skills", "tools")}
        users |= more


def read_cmd(path):
    return path.read_text(encoding="utf-8").strip()


def select(root, staged, cmds):
    """The suites to run, as (name, folder, command); a command of None is a suite that cannot run."""
    suites = []
    if any(p.startswith("scripts/") for p in staged):
        suites.append(("scripts", root, SCRIPTS_CMD))
    skills, tools = touched_folders(staged, "skills"), touched_folders(staged, "tools")
    # lib/ is shared by the skills' scripts: a change there runs its own tests, then the suites of the
    # code importing the staged modules; any other lib/ file (__init__.py, test.cmd) runs every suite.
    if any(p.startswith("lib/") for p in staged):
        if (root / "lib" / "test.cmd").is_file():
            suites.append(("lib", root / "lib", read_cmd(root / "lib" / "test.cmd")))
        modules = staged_lib_modules(staged)
        if modules is None:
            skills, tools = folder_names(root / "skills"), folder_names(root / "tools")
        else:
            users = lib_users(root, modules)
            skills = sorted(set(skills) | users["skills"])
            tools = sorted(set(tools) | users["tools"])
    for name in skills:
        folder = root / "skills" / name
        if not folder.is_dir():
            continue
        if name not in cmds:
            suites.append((name, folder, None))
        elif cmds[name]:
            suites.append((name, folder, cmds[name]))
    # A tool (tools/<name>/) is not a skill: its one-line test command lives in its test.cmd.
    for name in tools:
        cmd_file = root / "tools" / name / "test.cmd"
        if cmd_file.is_file():
            suites.append(("tools/" + name, cmd_file.parent, read_cmd(cmd_file)))
    return suites


def run_suite(suite, env):
    name, folder, cmd = suite
    if cmd is None:
        return False, ("%s: not an own skill" % name).encode()
    out = subprocess.run(["sh", "-c", cmd], cwd=folder, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return out.returncode == 0, out.stdout


def pool_size():
    try:
        return max(1, int(os.environ.get("SKILLS_PRECOMMIT_JOBS", DEFAULT_JOBS)))
    except ValueError:
        return DEFAULT_JOBS


def suite_env(jobs):
    env = dict(os.environ)
    env.setdefault("PYTEST_XDIST_AUTO_NUM_WORKERS", str(max(1, (os.cpu_count() or 1) // jobs)))
    return env


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    args = parser.parse_args(argv)
    staged = [line.strip() for line in sys.stdin if line.strip()]
    suites = select(args.root, staged, skill_test_cmds(args.root))
    if not suites:
        return 0
    jobs = pool_size()
    env = suite_env(jobs)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda suite: run_suite(suite, env), suites))
    status = 0
    # Suite order, not finish order, so the output does not depend on which suite was faster.
    for (name, _, _), (ok, out) in zip(suites, results):
        if not ok:
            sys.stderr.buffer.write(b"pre-commit: tests of %s failed\n" % name.encode() + out.rstrip(b"\r\n") + b"\n")
            status = 1
    sys.stderr.flush()
    return status


if __name__ == "__main__":
    sys.exit(main())
