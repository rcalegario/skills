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
