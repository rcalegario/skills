"""A fake git for tests: answers what gitutil.py asks, in memory, without starting a process.

    fake = fakegit.install(monkeypatch)   # gitutil.git now talks to the fake
    fake.init(tmp_path, ["code.txt"])     # a repository tracking code.txt, with one commit "init"
    sha = fake.commit(tmp_path, "feat: x")  # commit -a: snapshots the tracked files

Answers `status --porcelain [-- <pathspec>...]` (a tracked file whose content on disk changed;
plain paths and `:(exclude)<path>`), `rev-parse --short <ref>^{commit}`,
`rev-parse --verify --quiet <ref>^{commit}` and `log -1 --format=%s <ref>`, where <ref> is HEAD or a
sha prefix. Any other command raises UnknownCommand, inside a repository or not, so a new git
call fails its test instead of getting a wrong answer. Not modelled: untracked files, ignores and
deleted files (a tracked file missing on disk raises), which a test checking them leaves to real git.
"""
import hashlib
import os
import subprocess
import types

from lib import gitutil

NOT_A_REPO = 128


class UnknownCommand(Exception):
    pass


class _Repo:
    def __init__(self, root):
        self.root = root
        self.commits = []  # (full sha, subject), oldest first
        self.tracked = {}  # path relative to root, with "/" -> content at the last commit


class FakeGit:
    def __init__(self):
        self.repos = {}
        self.counter = 0

    # ------------------------------------------------------------ building history

    def init(self, root, files=(), subject="init"):
        """Make `root` a repository tracking `files` (paths relative to it) and commit them."""
        root = _key(root)
        repo = self.repos[root] = _Repo(root)
        for name in files:
            repo.tracked[name.replace("\\", "/")] = None
        self.commit(root, subject)
        return repo

    def commit(self, root, subject):
        """`git commit -a`: record every tracked file as it is on disk; return the short sha."""
        repo = self._repo(_key(root))
        for name in repo.tracked:
            repo.tracked[name] = _read(repo.root, name)
        self.counter += 1
        sha = hashlib.sha1(("%s\0%d" % (repo.root, self.counter)).encode("utf-8")).hexdigest()
        repo.commits.append((sha, subject))
        return sha[:7]

    def _repo(self, root):
        if root not in self.repos:
            raise KeyError("not a fake repository: %s" % root)
        return self.repos[root]

    # ------------------------------------------------------------ answering

    def run(self, args, cwd=None, **_):
        args = list(args)
        answer = self._answer(args[1:]) if args[:1] == ["git"] else None
        if answer is None:
            raise UnknownCommand(" ".join(args))
        cwd = _key(cwd or os.getcwd())
        repo = self._find(cwd)
        if repo is None:
            return _result(NOT_A_REPO, "", "fatal: not a git repository")
        return answer(repo, cwd)

    def _answer(self, rest):
        """The function answering `git <rest>` from (repo, cwd), or None for a command the fake does not know."""
        if rest[:2] == ["status", "--porcelain"]:
            return lambda repo, cwd: _result(0, self._status(repo, cwd, rest[2:]))
        if rest[:2] == ["rev-parse", "--short"] and len(rest) == 3:
            return lambda repo, cwd: self._found(repo, rest[2], 0)
        if rest[:3] == ["rev-parse", "--verify", "--quiet"] and len(rest) == 4:
            return lambda repo, cwd: _result(0 if self._resolve(repo, rest[3]) else 1, "")
        if rest[:3] == ["log", "-1", "--format=%s"] and len(rest) == 4:
            return lambda repo, cwd: self._found(repo, rest[3], 1)
        return None

    def _found(self, repo, ref, field):
        """The short sha (field 0) or the subject (field 1) of `ref`, or exit 128 when it names no commit."""
        found = self._resolve(repo, ref)
        if not found:
            return _result(NOT_A_REPO, "", "unknown revision")
        return _result(0, (found[0][:7] if field == 0 else found[1]) + "\n")

    def _find(self, cwd):
        path = cwd
        while True:
            if path in self.repos:
                return self.repos[path]
            parent = os.path.dirname(path)
            if parent == path:
                return None
            path = parent

    @staticmethod
    def _resolve(repo, ref):
        if ref.endswith("^{commit}"):
            ref = ref[:-len("^{commit}")]
        if ref == "HEAD":
            return repo.commits[-1] if repo.commits else None
        if len(ref) < 4 or any(c not in "0123456789abcdef" for c in ref.lower()):
            return None
        matches = [c for c in repo.commits if c[0].startswith(ref.lower())]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _status(repo, cwd, rest):
        prefix = os.path.relpath(cwd, repo.root).replace("\\", "/")
        prefix = "" if prefix == "." else prefix + "/"
        specs = rest[1:] if rest[:1] == ["--"] else rest
        include = [_norm(prefix + s) for s in specs if not s.startswith(":(exclude)")]
        exclude = [_norm(prefix + s[len(":(exclude)"):]) for s in specs if s.startswith(":(exclude)")]
        if not include:
            include = [_norm(prefix or ".")]
        lines = []
        for name in sorted(repo.tracked):
            if not any(_under(name, p) for p in include) or any(_under(name, p) for p in exclude):
                continue
            if _read(repo.root, name) != repo.tracked[name]:
                lines.append(" M %s" % name)
        return "".join(line + "\n" for line in lines)


def install(monkeypatch):
    """Point gitutil at a new FakeGit for this test; return the fake."""
    fake = FakeGit()
    monkeypatch.setattr(gitutil, "subprocess", types.SimpleNamespace(run=fake.run, PIPE=subprocess.PIPE))
    return fake


def _result(code, out, err=""):
    return types.SimpleNamespace(returncode=code, stdout=out, stderr=err)


def _key(path):
    return os.path.normcase(os.path.realpath(str(path)))


def _norm(path):
    path = os.path.normpath(path).replace("\\", "/")
    return "" if path == "." else path


def _under(name, path):
    return path == "" or name == path or name.startswith(path + "/")


def _read(root, name):
    with open(os.path.join(root, name), "rb") as f:
        return f.read()
