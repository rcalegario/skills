"""Tests for the statuses kept per load (derive.py). Run: python -m pytest <skill-dir>/scripts -q"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import status  # noqa: E402


def test_each_status_is_computed_once_per_load(task, monkeypatch):
    # The one test here that counts calls instead of reading the CLI's output (TESTING.md, Habits):
    # how many times a status is computed shows in no output, so the rules derive.py keeps per load
    # (its compute_* methods) are counted while every Task entry point that reads them runs.
    derive = status.task_derive.Derived
    computed = collections.Counter()
    for rule in ("compute_req_status", "compute_item_status", "compute_missing", "compute_agenda"):
        real = getattr(derive, rule)

        def counting(self, *args, _rule=rule, _real=real):
            key = repr(args[0].get("id")) if args and isinstance(args[0], dict) else repr(args)
            computed[(_rule, key)] += 1
            return _real(self, *args)

        monkeypatch.setattr(derive, rule, counting)
    t = status.Task(str(task))
    t.check()
    t.gate("pr")
    t.report()
    t.collect()
    t.step()
    t.pr_notes()
    assert {rule for rule, _ in computed} == {"compute_req_status", "compute_item_status",
                                             "compute_missing", "compute_agenda"}
    assert {k: n for k, n in computed.items() if n > 1} == {}
