"""Running git in a repo."""
import subprocess


def git(root, *args):
    """(exit code, stripped stdout) of `git <args>` run in `root`."""
    proc = subprocess.run(["git"] + list(args), cwd=root, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, universal_newlines=True)
    return proc.returncode, proc.stdout.strip()


def head_sha(root, commit="HEAD"):
    """The short sha of `commit` in `root`, or None when it is not a commit there."""
    code, sha = git(root, "rev-parse", "--short", "%s^{commit}" % commit)
    return sha if code == 0 else None


def commit_exists(root, sha):
    code, _ = git(root, "rev-parse", "--verify", "--quiet", "%s^{commit}" % sha)
    return code == 0
