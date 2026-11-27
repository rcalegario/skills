"""Tests for skills.py and the pre-commit hook (precommit.py), in process on files under tmp_path; only the
hooked commits and the UTF-8 mode test start processes. Run: python -m pytest scripts -q"""
import io
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time

import pytest

import precommit
import skills

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills.py")

GOOD = """\
own:
  - name: alpha
    test: "true"
    references:
      - skill: beta
        relation: derived
        took: The gates
      - repo: https://github.com/acme/skills
        path: skills/gamma
        commit: abc1234
        license: MIT
        relation: inspired
        took: Visuals
  - name: beta
    test: "true"
    references: []
installed: []
"""


def make_repo(tmp_path, manifest=GOOD, folders=("alpha", "beta"), readme=None):
    for name in folders:
        (tmp_path / "skills" / name).mkdir(parents=True)
        (tmp_path / "skills" / name / "SKILL.md").write_text("# " + name + "\n")
    (tmp_path / "skills.yaml").write_text(manifest)
    if readme is None:
        readme = "# repo\n\n<!-- credits:start -->\n<!-- credits:end -->\n"
    (tmp_path / "README.md").write_text(readme)
    return tmp_path


class Result:
    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def run(capsys):
    """Runs skills.main in process: run(root, *args) gives its exit code and what it printed."""
    def call(root, *args):
        capsys.readouterr()
        try:
            code = skills.main(["--root", str(root), *args])
        except SystemExit as e:
            code = e.code
        out = capsys.readouterr()
        return Result(code or 0, out.out, out.err)
    return call


def write_credits(root):
    assert skills.main(["--root", str(root), "credits", "--write"]) == 0


def test_good_manifest_passes(tmp_path, run):
    root = make_repo(tmp_path)
    write_credits(root)
    out = run(root, "validate")
    assert out.returncode == 0, out.stdout + out.stderr


def test_folder_without_entry_fails(tmp_path, run):
    root = make_repo(tmp_path, folders=("alpha", "beta", "delta"))
    out = run(root, "validate")
    assert out.returncode == 1
    assert "delta" in out.stdout


def test_entry_without_folder_fails(tmp_path, run):
    root = make_repo(tmp_path, folders=("alpha",))
    out = run(root, "validate")
    assert out.returncode == 1
    assert "beta" in out.stdout


@pytest.mark.parametrize("relation", [None, "copied"])
def test_bad_relation_fails(tmp_path, relation, run):
    line = "" if relation is None else f"        relation: {relation}\n"
    manifest = GOOD.replace("        relation: inspired\n", line)
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "validate")
    assert out.returncode == 1
    assert "alpha" in out.stdout and "relation" in out.stdout


@pytest.mark.parametrize("commit_line, ok", [
    ("        commit: abc1234\n", True),
    ("        commit: unknown\n", True),
    ("        commit: " + "a" * 40 + "\n", True),
    ("", False),
    ("        commit: main\n", False),
    ("        commit: abc12\n", False),
])
def test_external_commit_rules(tmp_path, commit_line, ok, run):
    manifest = GOOD.replace("        commit: abc1234\n", commit_line)
    root = make_repo(tmp_path, manifest=manifest)
    write_credits(root)
    out = run(root, "validate")
    assert (out.returncode == 0) == ok, out.stdout
    if not ok:
        assert "commit" in out.stdout


def test_external_without_repo_fails(tmp_path, run):
    manifest = GOOD.replace("      - repo: https://github.com/acme/skills\n        path:", "      - path:")
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "validate")
    assert out.returncode == 1
    assert "repo" in out.stdout


def test_unknown_internal_skill_fails(tmp_path, run):
    manifest = GOOD.replace("skill: beta", "skill: omega")
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "validate")
    assert out.returncode == 1
    assert "omega" in out.stdout


def test_test_command_prints_for_a_skill(tmp_path, run):
    root = make_repo(tmp_path)
    out = run(root, "test-cmd", "alpha")
    assert out.returncode == 0
    assert out.stdout.strip() == "true"


def test_test_cmds_prints_every_skill_as_json(tmp_path, run):
    manifest = GOOD.replace('  - name: beta\n    test: "true"', '  - name: beta\n    test: ""')
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "test-cmds")
    assert out.returncode == 0
    assert json.loads(out.stdout) == {"alpha": "true", "beta": ""}


HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".githooks", "pre-commit")


RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precommit.py")


def git(root, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True, text=True, env=env,
    )


@pytest.fixture(scope="session")
def hooked_base(tmp_path_factory):
    """A repository with this hook, skills.py and precommit.py, committed once for the session."""
    root = make_repo(tmp_path_factory.mktemp("hooked"))
    (root / "scripts").mkdir()
    shutil.copy(SCRIPT, root / "scripts" / "skills.py")
    shutil.copy(RUNNER, root / "scripts" / "precommit.py")
    (root / ".githooks").mkdir()
    shutil.copy(HOOK, root / ".githooks" / "pre-commit")
    os.chmod(root / ".githooks" / "pre-commit", 0o755)
    write_credits(root)
    git(root, "init", "-q")
    git(root, "config", "core.hooksPath", ".githooks")
    git(root, "add", ".")
    assert git(root, "commit", "-q", "--no-verify", "-m", "base").returncode == 0
    return root


@pytest.fixture
def hooked(tmp_path, hooked_base):
    """A copy of the hooked repository, for one test's commit through the hook."""
    root = tmp_path / "repo"
    shutil.copytree(hooked_base, root)
    return root


def test_hook_blocks_a_failing_staged_suite(hooked):
    (hooked / "skills.yaml").write_text(GOOD.replace('  - name: alpha\n    test: "true"', '  - name: alpha\n    test: "false"'))
    (hooked / "skills" / "alpha" / "SKILL.md").write_text("# alpha v2\n")
    git(hooked, "add", "skills.yaml", "skills/alpha/SKILL.md")
    out = git(hooked, "commit", "-q", "-m", "touch alpha")
    assert out.returncode != 0
    assert "pre-commit: tests of alpha failed" in out.stderr


CMDS = {"alpha": "alpha suite", "beta": "beta suite"}


def suite_repo(tmp_path):
    """A repo with the skills alpha and beta, lib/yamlio.py, lib/graph.py, lib's test.cmd and the tool gamma."""
    root = make_repo(tmp_path)
    (root / "lib").mkdir()
    (root / "lib" / "test.cmd").write_text("lib suite\n")
    for module in ("yamlio", "graph"):
        (root / "lib" / (module + ".py")).write_text("X = 1\n")
    (root / "tools" / "gamma").mkdir(parents=True)
    (root / "tools" / "gamma" / "test.cmd").write_text("gamma suite\n")
    return root


def selected(root, *staged):
    """The names of the suites precommit selects for the staged paths. Selection is tested at select(), not
    through a commit, so a case starts no process; the hooked commits below cover the hook around it."""
    return sorted(name for name, _, _ in precommit.select(root, list(staged), CMDS))


def test_select_runs_the_scripts_suite_for_a_staged_script(tmp_path):
    root = suite_repo(tmp_path)
    assert selected(root, "scripts/skills.py") == ["scripts"]


def test_select_runs_only_the_staged_skills_suite(tmp_path):
    root = suite_repo(tmp_path)
    assert selected(root, "skills/alpha/SKILL.md") == ["alpha"]


def test_select_runs_a_staged_tools_suite(tmp_path):
    root = suite_repo(tmp_path)
    write_py(root, "tools/gamma/state.py", "X = 1\n")
    assert selected(root, "tools/gamma/state.py") == ["tools/gamma"]


def test_select_runs_every_suite_when_lib_is_staged(tmp_path):
    root = suite_repo(tmp_path)
    assert selected(root, "lib/__init__.py") == ["alpha", "beta", "lib", "tools/gamma"]


@pytest.mark.parametrize("line", [
    "from lib import yamlio",
    "from lib import graph, yamlio",
    "from lib.yamlio import X",
    "import lib.yamlio",
    "from lib import (\n    graph,\n    yamlio,\n)",
    "from lib import graph, \\\n    yamlio",
    "import os, lib.yamlio",
    "import lib.graph, lib.yamlio",
    "from lib import yamlio as y",
    "import lib.yamlio as y",
    "from lib import *",
    "import lib",
    "def load():\n    from lib import yamlio",
    "x = 1; import lib.yamlio",
])
def test_select_runs_only_users_of_a_staged_lib_module(tmp_path, line):
    root = suite_repo(tmp_path)
    write_py(root, "skills/alpha/scripts/run.py", "import os\n" + line + "\n")
    write_py(root, "skills/beta/scripts/run.py", "from lib import graph\n")
    assert selected(root, "lib/yamlio.py") == ["alpha", "lib"]


def test_select_runs_only_lib_for_a_module_nobody_imports(tmp_path):
    root = suite_repo(tmp_path)
    assert selected(root, "lib/graph.py") == ["lib"]


def write_py(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_select_counts_a_source_it_cannot_parse_as_a_lib_user(tmp_path):
    root = suite_repo(tmp_path)
    write_py(root, "skills/alpha/scripts/run.py", "def broken(:\n")
    assert selected(root, "lib/yamlio.py") == ["alpha", "lib"]


@pytest.mark.parametrize("line", ["from lib import yamlio", "from . import yamlio", "from .yamlio import X"])
def test_select_follows_users_through_lib_modules(tmp_path, line):
    root = suite_repo(tmp_path)
    write_py(root, "lib/graph.py", line + "\n")
    write_py(root, "skills/beta/scripts/run.py", "from lib import graph\n")
    assert selected(root, "lib/yamlio.py") == ["beta", "lib"]


@pytest.mark.parametrize("line", [
    "import alpha_tool", "from alpha_tool import X", "import os, alpha_tool", "from . import alpha_tool",
    "if True:\n    import alpha_tool",
])
def test_select_follows_users_through_another_skills_scripts(tmp_path, line):
    root = suite_repo(tmp_path)
    write_py(root, "skills/alpha/scripts/alpha_tool.py", "from lib import yamlio\nX = 1\n")
    write_py(root, "skills/beta/scripts/run.py", line + "\n")
    assert selected(root, "lib/yamlio.py") == ["alpha", "beta", "lib"]


def test_select_follows_users_two_lib_modules_away(tmp_path):
    root = suite_repo(tmp_path)
    write_py(root, "lib/graph.py", "from lib import yamlio\n")
    write_py(root, "lib/chain.py", "from lib import graph\n")
    write_py(root, "skills/beta/scripts/run.py", "from lib import chain\n")
    assert selected(root, "lib/yamlio.py") == ["beta", "lib"]


def test_select_follows_users_two_skills_away(tmp_path):
    root = suite_repo(tmp_path)
    write_py(root, "skills/alpha/scripts/alpha_tool.py", "from lib import yamlio\n")
    write_py(root, "skills/beta/scripts/beta_tool.py", "import alpha_tool\n")
    write_py(root, "tools/gamma/state.py", "import beta_tool\n")
    assert selected(root, "lib/yamlio.py") == ["alpha", "beta", "lib", "tools/gamma"]


def test_select_ignores_a_skills_own_module_named_like_anothers(tmp_path):
    root = suite_repo(tmp_path)
    write_py(root, "skills/alpha/scripts/status.py", "from lib import yamlio\n")
    write_py(root, "skills/beta/scripts/status.py", "X = 1\n")
    write_py(root, "skills/beta/scripts/run.py", "import status\n")
    assert selected(root, "lib/yamlio.py") == ["alpha", "lib"]


@pytest.mark.parametrize("line", [
    'STATUS = os.path.join(REPO, "skills", "alpha", "scripts", "alpha_tool.py")',
    'STATUS = REPO + "/skills/alpha/scripts/alpha_tool.py"',
])
def test_select_follows_users_through_a_path_to_another_skills_scripts(tmp_path, line):
    root = suite_repo(tmp_path)
    write_py(root, "skills/alpha/scripts/alpha_tool.py", "from lib import yamlio\n")
    write_py(root, "tools/gamma/state.py", "import os\n" + line + "\n")
    assert selected(root, "lib/yamlio.py") == ["alpha", "lib", "tools/gamma"]


BOTH_SKILLS = ("skills/alpha/SKILL.md", "skills/beta/SKILL.md")


def run_precommit(tmp_path, monkeypatch, capsys, staged, suite):
    """Runs precommit.main on the staged paths, each suite run by suite(name, env) -> (ok, output).
    Gives the exit code and what it printed to stderr. The stub stands in for run_suite's sh -c and for
    skill_test_cmds' skills.py process; the hooked commits below run both for real."""
    root = make_repo(tmp_path)
    monkeypatch.setattr(precommit, "skill_test_cmds", lambda root: CMDS)
    monkeypatch.setattr(precommit, "run_suite", lambda s, env: suite(s[0], env))
    monkeypatch.setattr(sys, "stdin", io.StringIO("".join(p + "\n" for p in staged)))
    code = precommit.main(["--root", str(root)])
    return code, capsys.readouterr().err


@pytest.mark.parametrize("jobs, passes", [("2", True), ("1", False)])
def test_main_runs_suites_at_once_within_the_pool(tmp_path, monkeypatch, capsys, jobs, passes):
    monkeypatch.setenv("SKILLS_PRECOMMIT_JOBS", jobs)
    meeting = threading.Barrier(2, timeout=2)

    def meet(name, env):
        """Passes only when the other suite runs at the same time."""
        try:
            meeting.wait()
            return True, b""
        except threading.BrokenBarrierError:
            return False, b"ran alone"

    code, err = run_precommit(tmp_path, monkeypatch, capsys, BOTH_SKILLS, meet)
    assert (code == 0) == passes, err


def test_main_prints_only_failing_suites_whole(tmp_path, monkeypatch, capsys):
    finished = []

    def suite(name, env):
        if name == "alpha":
            return False, b"alpha line 1\nalpha line 2\n"
        time.sleep(0.5)
        finished.append(name)
        return True, b"beta said this\n"

    code, err = run_precommit(tmp_path, monkeypatch, capsys, BOTH_SKILLS, suite)
    assert code == 1
    assert err == "pre-commit: tests of alpha failed\nalpha line 1\nalpha line 2\n"
    assert finished == ["beta"]                 # the passing suite ran to its end before main returned


def workers_given(tmp_path, monkeypatch, capsys):
    """The xdist worker count a staged alpha's suite gets."""
    given = []

    def suite(name, env):
        given.append(env.get("PYTEST_XDIST_AUTO_NUM_WORKERS"))
        return True, b""

    code, err = run_precommit(tmp_path, monkeypatch, capsys, ["skills/alpha/SKILL.md"], suite)
    assert code == 0, err
    return given[0]


@pytest.mark.parametrize("jobs", ["1", "2", "4"])
def test_main_sizes_xdist_workers_to_the_pool(tmp_path, monkeypatch, capsys, jobs):
    monkeypatch.setenv("SKILLS_PRECOMMIT_JOBS", jobs)
    monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
    assert workers_given(tmp_path, monkeypatch, capsys) == str(max(1, os.cpu_count() // int(jobs)))


def test_main_keeps_a_preset_xdist_worker_count(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SKILLS_PRECOMMIT_JOBS", "2")
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "97")
    assert workers_given(tmp_path, monkeypatch, capsys) == "97"


def test_hook_starts_uv_twice_whatever_the_skills(hooked, tmp_path):
    root = hooked
    for name in ("gamma", "delta"):
        (root / "skills" / name).mkdir()
        (root / "skills" / name / "SKILL.md").write_text("# %s\n" % name)
    extra = "".join('  - name: %s\n    test: "true"\n    references: []\n' % n for n in ("gamma", "delta"))
    (root / "skills.yaml").write_text(GOOD.replace("installed: []\n", extra + "installed: []\n"))
    write_credits(root)
    (root / "lib").mkdir()
    (root / "lib" / "test.cmd").write_text("true\n")
    (root / "lib" / "__init__.py").write_text("# touched\n")
    bin_dir, log = tmp_path / "fakebin", tmp_path / "uv.log"
    bin_dir.mkdir()
    python = sys.executable.replace("\\", "/")
    # Logs each start, then runs the command after `python` with this interpreter, which has pyyaml.
    (bin_dir / "uv").write_text(
        '#!/bin/sh\necho uv >> "%s"\nwhile [ "$1" != python ]; do shift; done\nshift\nexec "%s" "$@"\n'
        % (str(log).replace("\\", "/"), python), newline="\n")
    os.chmod(bin_dir / "uv", 0o755)
    git(root, "add", ".")
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
    out = git(root, "commit", "-q", "-m", "more skills, touch lib", env=env)
    assert out.returncode == 0, out.stderr
    assert log.read_text().split() == ["uv", "uv"]


def test_hook_blocks_an_invalid_manifest(hooked):
    (hooked / "skills" / "delta").mkdir()
    (hooked / "skills" / "delta" / "SKILL.md").write_text("# delta\n")
    git(hooked, "add", "skills/delta/SKILL.md")
    out = git(hooked, "commit", "-q", "-m", "add delta")
    assert out.returncode != 0
    assert "delta" in out.stderr


def test_credits_write_lists_references(tmp_path):
    root = make_repo(tmp_path)
    write_credits(root)
    readme = (root / "README.md").read_text(encoding="utf-8")
    section = readme.split("<!-- credits:start -->")[1].split("<!-- credits:end -->")[0]
    assert "### alpha" in section and "### beta" in section
    assert "derived from [beta](skills/beta)" in section
    assert "inspired by [acme/skills · gamma](https://github.com/acme/skills/tree/abc1234/skills/gamma)" in section
    assert "MIT" in section and "`abc1234`" in section
    assert readme.startswith("# repo\n")


def test_credits_write_keeps_utf8_and_lf_outside_utf8_mode(tmp_path):
    root = make_repo(tmp_path)
    readme = root / "README.md"
    readme.write_bytes("# repo · café\n\n<!-- credits:start -->\n<!-- credits:end -->\n".encode("utf-8"))
    env = dict(os.environ, PYTHONUTF8="0")
    for cmd in (["credits", "--write"], ["validate"]):
        out = subprocess.run([sys.executable, "-X", "utf8=0", SCRIPT, "--root", str(root), *cmd],
                             capture_output=True, text=True, env=env)
        assert out.returncode == 0, out.stdout + out.stderr
    data = readme.read_bytes()
    assert b"\r\n" not in data
    text = data.decode("utf-8")
    assert text.startswith("# repo · café\n")
    assert "[acme/skills · gamma]" in text


def test_unknown_commit_links_to_the_default_branch(tmp_path):
    root = make_repo(tmp_path, manifest=GOOD.replace("commit: abc1234", "commit: unknown"))
    write_credits(root)
    section = (root / "README.md").read_text(encoding="utf-8")
    assert "https://github.com/acme/skills/tree/HEAD/skills/gamma" in section
    assert "commit unknown" in section


def test_stale_credits_fail_validate(tmp_path, run):
    root = make_repo(tmp_path)
    write_credits(root)
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("Visuals", "Pictures"), encoding="utf-8")
    out = run(root, "validate")
    assert out.returncode == 1
    assert "credits --write" in out.stdout


def test_missing_credits_markers_fail_validate(tmp_path, run):
    root = make_repo(tmp_path, readme="# repo\n")
    out = run(root, "validate")
    assert out.returncode == 1
    assert "credits" in out.stdout


def with_installed(block):
    return GOOD.replace("installed: []\n", "installed:\n" + block)


GOOD_INSTALLED = """\
  - name: tdd
    repo: https://github.com/acme/skills
    path: skills/tdd
    commit: abc1234def56
  - name: lost
    origin: unknown
"""


def test_good_installed_passes(tmp_path, run):
    root = make_repo(tmp_path, manifest=with_installed(GOOD_INSTALLED))
    write_credits(root)
    out = run(root, "validate")
    assert out.returncode == 0, out.stdout + out.stderr


@pytest.mark.parametrize("entry", [
    "  - repo: https://github.com/acme/skills\n    path: p\n    commit: abc1234\n",
    "  - name: x\n    path: p\n    commit: abc1234\n",
    "  - name: x\n    repo: https://github.com/acme/skills\n    commit: abc1234\n",
    "  - name: x\n    repo: https://github.com/acme/skills\n    path: p\n",
    "  - name: x\n    repo: https://github.com/acme/skills\n    path: p\n    commit: main\n",
    "  - name: x\n    repo: https://github.com/acme/skills\n    path: p\n    commit: unknown\n",
    "  - name: x\n",
], ids=["no-name", "no-repo", "no-path", "no-commit", "bad-sha", "unknown-commit", "no-origin"])
def test_installed_entry_without_origin_or_commit_fails(tmp_path, entry, run):
    root = make_repo(tmp_path, manifest=with_installed(entry))
    write_credits(root)
    out = run(root, "validate")
    assert out.returncode == 1, out.stdout
    assert "installed" in out.stdout


@pytest.mark.parametrize("block, culprit", [
    ("  - name: x\n    origin: unknown\n  - name: x\n    origin: unknown\n", "x"),
    ("  - name: alpha\n    origin: unknown\n", "alpha"),
])
def test_installed_duplicate_or_own_name_fails(tmp_path, block, culprit, run):
    root = make_repo(tmp_path, manifest=with_installed(block))
    write_credits(root)
    out = run(root, "validate")
    assert out.returncode == 1, out.stdout
    assert culprit in out.stdout


def test_hidden_folder_is_not_a_skill(tmp_path, run):
    root = make_repo(tmp_path)
    (root / "skills" / ".pytest_cache").mkdir()
    write_credits(root)
    out = run(root, "validate")
    assert out.returncode == 0, out.stdout + out.stderr
