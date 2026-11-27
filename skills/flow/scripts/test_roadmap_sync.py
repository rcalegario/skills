"""Tests for writing the roadmap statuses. Run: python -m pytest <skill-dir>/scripts -q"""
import builtins
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_flow import fake, link_feature, repo, run, write_roadmap  # noqa: E402,F401  (fixtures and helpers)


def test_sync_leaves_a_right_roadmap_unwritten(repo, monkeypatch, capsys):
    write_roadmap(repo)
    link_feature(repo, "F1.1", status="building")
    assert run(repo, "roadmap") == 0  # writes every status once
    path = repo / ".specs" / "roadmap.yaml"
    before = path.read_bytes()
    writes = []
    real_open = builtins.open

    def recording_open(file, mode="r", *a, **kw):
        if os.path.normcase(os.path.abspath(str(file))) == os.path.normcase(str(path)) and "w" in mode:
            writes.append(mode)
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", recording_open)
    assert run(repo, "roadmap") == 0
    capsys.readouterr()
    assert writes == []
    assert path.read_bytes() == before
