import shutil
import subprocess

import pytest

from lib import gitutil


@pytest.fixture(scope="session")
def template(tmp_path_factory):
    """A real repository with one commit, built once per session."""
    root = tmp_path_factory.mktemp("gitutil")

    def run(*args):
        subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"] + list(args),
                       check=True, capture_output=True)
    run("init", "-q")
    (root / "f").write_text("x")
    run("add", "f")
    run("commit", "-q", "-m", "one")
    return root


@pytest.fixture
def repo(tmp_path, template):
    """A copy of the session repository."""
    root = tmp_path / "repo"
    shutil.copytree(template, root)
    return str(root)


def test_git_returns_code_and_stripped_output(repo):
    root = repo
    code, out = gitutil.git(root, "log", "--format=%s")
    assert (code, out) == (0, "one")
    assert gitutil.git(root, "rev-parse", "nope")[0] != 0


def test_head_sha_and_commit_exists(repo):
    root = repo
    sha = gitutil.head_sha(root)
    assert sha and len(sha) >= 7
    assert gitutil.commit_exists(root, sha)
    assert not gitutil.commit_exists(root, "0" * 40)
    assert gitutil.head_sha(root, "nope") is None
