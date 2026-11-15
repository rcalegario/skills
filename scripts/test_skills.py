"""Tests for skills.py. They drive the CLI on a temp repo. Run: python -m pytest scripts -q"""
import os
import subprocess
import sys
import textwrap

import pytest

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


def run(root, *args):
    return subprocess.run(
        [sys.executable, SCRIPT, "--root", str(root), *args],
        capture_output=True, text=True,
    )


def test_good_manifest_passes(tmp_path):
    root = make_repo(tmp_path)
    out = run(root, "validate")
    assert out.returncode == 0, out.stdout + out.stderr


def test_folder_without_entry_fails(tmp_path):
    root = make_repo(tmp_path, folders=("alpha", "beta", "delta"))
    out = run(root, "validate")
    assert out.returncode == 1
    assert "delta" in out.stdout


def test_entry_without_folder_fails(tmp_path):
    root = make_repo(tmp_path, folders=("alpha",))
    out = run(root, "validate")
    assert out.returncode == 1
    assert "beta" in out.stdout


@pytest.mark.parametrize("relation", [None, "copied"])
def test_bad_relation_fails(tmp_path, relation):
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
def test_external_commit_rules(tmp_path, commit_line, ok):
    manifest = GOOD.replace("        commit: abc1234\n", commit_line)
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "validate")
    assert (out.returncode == 0) == ok, out.stdout
    if not ok:
        assert "commit" in out.stdout


def test_external_without_repo_fails(tmp_path):
    manifest = GOOD.replace("      - repo: https://github.com/acme/skills\n        path:", "      - path:")
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "validate")
    assert out.returncode == 1
    assert "repo" in out.stdout


def test_unknown_internal_skill_fails(tmp_path):
    manifest = GOOD.replace("skill: beta", "skill: omega")
    root = make_repo(tmp_path, manifest=manifest)
    out = run(root, "validate")
    assert out.returncode == 1
    assert "omega" in out.stdout


def test_test_command_prints_for_a_skill(tmp_path):
    root = make_repo(tmp_path)
    out = run(root, "test-cmd", "alpha")
    assert out.returncode == 0
    assert out.stdout.strip() == "true"


HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".githooks", "pre-commit")


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True, text=True,
    )


def hooked_repo(tmp_path, alpha_test):
    manifest = GOOD.replace('test: "true"', f'test: "{alpha_test}"', 1)
    root = make_repo(tmp_path, manifest=manifest)
    (root / "scripts").mkdir()
    (root / "scripts" / "skills.py").write_text(open(SCRIPT).read())
    (root / ".githooks").mkdir()
    (root / ".githooks" / "pre-commit").write_text(open(HOOK).read())
    os.chmod(root / ".githooks" / "pre-commit", 0o755)
    git(root, "init", "-q")
    git(root, "config", "core.hooksPath", ".githooks")
    git(root, "add", ".")
    assert git(root, "commit", "-q", "--no-verify", "-m", "base").returncode == 0
    return root


@pytest.mark.parametrize("alpha_test, passes", [("true", True), ("false", False)])
def test_hook_runs_staged_skill_tests(tmp_path, alpha_test, passes):
    root = hooked_repo(tmp_path, alpha_test)
    (root / "skills" / "alpha" / "SKILL.md").write_text("# alpha v2\n")
    git(root, "add", "skills/alpha/SKILL.md")
    out = git(root, "commit", "-q", "-m", "touch alpha")
    assert (out.returncode == 0) == passes, out.stderr
    if not passes:
        assert "alpha" in out.stderr


def test_hook_skips_tests_of_untouched_skills(tmp_path):
    root = hooked_repo(tmp_path, "false")
    (root / "skills" / "beta" / "SKILL.md").write_text("# beta v2\n")
    git(root, "add", "skills/beta/SKILL.md")
    assert git(root, "commit", "-q", "-m", "touch beta").returncode == 0


def test_hook_blocks_an_invalid_manifest(tmp_path):
    root = hooked_repo(tmp_path, "true")
    (root / "skills" / "delta").mkdir()
    (root / "skills" / "delta" / "SKILL.md").write_text("# delta\n")
    git(root, "add", "skills/delta/SKILL.md")
    out = git(root, "commit", "-q", "-m", "add delta")
    assert out.returncode != 0
    assert "delta" in out.stderr
