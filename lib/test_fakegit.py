"""The fake git answers what lib/gitutil.py asks the way real git does."""
import subprocess

import pytest

from lib import fakegit, gitutil


class RealGit:
    """Builds the history with real git."""

    def init(self, root, files):
        write_files(root, files)
        self.run(root, "init", "-q")
        self.run(root, "add", *files)
        self.run(root, "commit", "-qm", "init")

    def commit(self, root, subject):
        self.run(root, "commit", "-qam", subject)
        return gitutil.head_sha(str(root))

    @staticmethod
    def run(root, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false"]
                       + list(args), cwd=str(root), check=True, capture_output=True)


class FakeGit:
    """Builds the same history in the fake."""

    def __init__(self, monkeypatch):
        self.fake = fakegit.install(monkeypatch)

    def init(self, root, files):
        write_files(root, files)
        self.fake.init(root, list(files))

    def commit(self, root, subject):
        return self.fake.commit(root, subject)


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_files(root, files):
    for name, content in files.items():
        write(root, name, content)


def history(driver, tmp_path):
    """Run one history and every query flow.py makes; shas come back as their commit's name."""
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    driver.init(root, {"code.txt": "v1\n", "docs/a.md": "a\n", "task/b.md": "b\n"})
    first = gitutil.head_sha(str(root))
    write(root, "code.txt", "v1.1\n")
    second = driver.commit(root, "feat: second")
    write(root, "code.txt", "v1.2\n")
    third = driver.commit(root, "feat: third")
    names = {first: "first", second: "second", third: "third"}

    def name(sha):
        return names.get(sha, sha)

    r = str(root)
    answers = {
        "clean": gitutil.git(r, "status", "--porcelain"),
        "head": name(gitutil.head_sha(r)),
        "first by prefix": name(gitutil.head_sha(r, first[:5])),
        "unknown ref": gitutil.head_sha(r, "nope"),
        "exists": gitutil.commit_exists(r, second),
        "not exists": gitutil.commit_exists(r, "0" * 40),
        "subject": gitutil.git(r, "log", "-1", "--format=%s", second),
        "head subject": gitutil.git(r, "log", "-1", "--format=%s", "HEAD"),
    }
    write(root, "code.txt", "v2\n")
    write(root, "docs/a.md", "a2\n")
    write(root, "task/b.md", "b2\n")
    answers["dirty"] = gitutil.git(r, "status", "--porcelain", "--", "code.txt", "docs")
    answers["dirty excluding"] = gitutil.git(r, "status", "--porcelain", "--", ".", ":(exclude)task")
    answers["dirty in a folder"] = gitutil.git(r, "status", "--porcelain", "--", "task")
    outside = tmp_path / "outside"
    outside.mkdir()
    answers["outside"] = gitutil.git(str(outside), "status", "--porcelain")[0] != 0
    answers["outside sha"] = gitutil.head_sha(str(outside))
    return answers


def test_fake_answers_like_real_git(tmp_path, monkeypatch):
    real = history(RealGit(), tmp_path / "real")
    fake = history(FakeGit(monkeypatch), tmp_path / "fake")
    assert fake == real
    assert real["dirty"] == (0, "M code.txt\n M docs/a.md")  # git strips: the first line loses its space


def test_fake_starts_no_process(tmp_path, monkeypatch):
    fake = fakegit.install(monkeypatch)

    def spawn(*args, **kwargs):
        raise AssertionError("a process started")
    monkeypatch.setattr(subprocess, "run", spawn)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    (tmp_path / "f").write_text("x")
    fake.init(tmp_path, ["f"])
    assert gitutil.head_sha(str(tmp_path))


def test_fake_refuses_a_command_it_does_not_know(tmp_path, monkeypatch):
    fake = fakegit.install(monkeypatch)
    (tmp_path / "repo").mkdir()
    fake.init(tmp_path / "repo", [])
    with pytest.raises(fakegit.UnknownCommand, match="git branch"):
        gitutil.git(str(tmp_path / "repo"), "branch")
    with pytest.raises(fakegit.UnknownCommand, match="git branch"):  # outside any repository too
        gitutil.git(str(tmp_path), "branch")


def test_two_repositories_never_share_a_sha(tmp_path, monkeypatch):
    fake = fakegit.install(monkeypatch)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    fake.init(tmp_path / "a", [])
    fake.init(tmp_path / "b", [])
    assert gitutil.head_sha(str(tmp_path / "a")) != gitutil.head_sha(str(tmp_path / "b"))


def test_a_subfolder_belongs_to_its_repository(tmp_path, monkeypatch):
    fake = fakegit.install(monkeypatch)
    (tmp_path / "sub").mkdir()
    fake.init(tmp_path, [])
    assert gitutil.head_sha(str(tmp_path / "sub")) == gitutil.head_sha(str(tmp_path))
