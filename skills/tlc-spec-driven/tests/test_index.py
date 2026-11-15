#!/usr/bin/env python3
"""Tests for scripts/index.py, driven through its CLI on throwaway projects.

Run: python3 -m unittest discover -s tests   (from the skill directory)
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "index.py")


def adr_text(num, title, decision, scope, status="active"):
    return (
        f"# AD-{num:03d}: {title}\n\n"
        f"- **Decision**: {decision}\n"
        f"- **Reason**: because\n"
        f"- **Trade-off**: something\n"
        f"- **Scope**: {scope}\n"
        f"- **Date**: 2026-10-11\n"
        f"- **Status**: {status}\n"
    )


class IndexTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, body):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        return path

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    def run_index(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args, "--root", self.root],
            capture_output=True, text=True,
        )


class AdrIndexTest(IndexTestBase):
    def seed(self):
        self.write("docs/adr/AD-001-use-sqlite.md", adr_text(1, "Use SQLite", "Store data in SQLite", "persistence", "superseded by AD-003"))
        self.write("docs/adr/AD-002-ears.md", adr_text(2, "EARS notation", "Write ACs in EARS", "specs"))
        self.write("docs/adr/AD-003-use-postgres.md", adr_text(3, "Use Postgres", "Store data in Postgres", "persistence"))

    def test_generates_active_table_and_superseded_section(self):
        self.seed()
        r = self.run_index("adr")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        idx = self.read("docs/adr/AGENTS.md")
        self.assertIn("## Active", idx)
        self.assertIn("| [AD-002](AD-002-ears.md) | specs | Write ACs in EARS |", idx)
        self.assertIn("| [AD-003](AD-003-use-postgres.md) | persistence | Store data in Postgres |", idx)
        self.assertNotIn("| [AD-001]", idx)
        self.assertIn("## Superseded", idx)
        self.assertIn("- AD-001 → AD-003", idx)
        self.assertLess(idx.index("AD-002"), idx.index("AD-003"))

    def test_creates_claude_md_importing_the_index(self):
        self.seed()
        self.run_index("adr")
        self.assertEqual(self.read("docs/adr/CLAUDE.md").strip(), "@AGENTS.md")

    def test_existing_claude_md_is_not_overwritten(self):
        self.seed()
        self.write("docs/adr/CLAUDE.md", "custom\n")
        self.run_index("adr")
        self.assertEqual(self.read("docs/adr/CLAUDE.md"), "custom\n")

    def test_adr_without_decision_fails_naming_the_file(self):
        self.write("docs/adr/AD-001-bad.md", "# AD-001: Bad\n\n- **Scope**: x\n- **Status**: active\n")
        r = self.run_index("adr")
        self.assertEqual(r.returncode, 1)
        self.assertIn("AD-001-bad.md", r.stdout + r.stderr)
        self.assertFalse(self.exists("docs/adr/AGENTS.md"))

    def test_adr_with_invalid_status_fails(self):
        self.write("docs/adr/AD-001-x.md", adr_text(1, "X", "d", "s", "maybe"))
        r = self.run_index("adr")
        self.assertEqual(r.returncode, 1)

    def test_check_detects_stale_index(self):
        self.seed()
        self.run_index("adr")
        self.assertEqual(self.run_index("adr", "--check").returncode, 0)
        self.write("docs/adr/AD-004-new.md", adr_text(4, "New", "A new thing", "api"))
        r = self.run_index("adr", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("AD-004", self.read("docs/adr/AGENTS.md"))

    def test_missing_adr_dir_is_a_noop(self):
        r = self.run_index("adr")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.exists("docs/adr"))
        self.assertEqual(self.run_index("adr", "--check").returncode, 0)


SPEC_FILLED = "# T\n\n## Problem Statement\n\nUsers cannot label transactions. They want tags too.\n\n## Out of Scope\n"
SPEC_PLACEHOLDER = "# T\n\n## Problem Statement\n\n[Describe the problem in 1-3 sentences]\n\n## Out of Scope\n"
VERIFICATION_PASS = "# A verification\n\n**Verdict**: PASS\n\n## Findings\n\nNone - probed it\n"
VERIFICATION_FAIL = "# A verification\n\n**Verdict**: FAIL\n"
TASKS_OPEN = "### T1: one\n\n- [x] done\n\n### T2: two\n\n- [ ] todo\n"
TASKS_DONE = "### T1: one\n\n- [x] done\n"


class FeatureIndexTest(IndexTestBase):
    def feature(self, name, spec=SPEC_FILLED, **files):
        base = f".specs/features/{name}/"
        if spec is not None:
            self.write(base + "spec.md", spec)
        for fname, body in files.items():
            self.write(base + fname.replace("_", ".", 1), body)

    def names(self):
        return [ln.split("](")[0].lstrip("| [") for ln in self.rows()]

    def rows(self):
        idx = self.read(".specs/features/AGENTS.md")
        return [ln for ln in idx.splitlines() if ln.startswith("| [")]

    def test_each_state_is_derived_from_the_files(self):
        self.feature("m1.f1.done", verification_md=VERIFICATION_PASS, tasks_md=TASKS_DONE)
        self.feature("m1.f2.failing", verification_md=VERIFICATION_FAIL, tasks_md=TASKS_DONE)
        self.feature("m1.f3.open", tasks_md=TASKS_OPEN)
        self.feature("m1.f4.unverified", tasks_md=TASKS_DONE)
        self.feature("m1.f5.specified")
        r = self.run_index("features")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.rows()
        self.assertIn("| [m1.f1.done](m1.f1.done/) | done |", rows[0])
        self.assertIn("| [m1.f2.failing](m1.f2.failing/) | failing |", rows[1])
        self.assertIn("| [m1.f3.open](m1.f3.open/) | in progress |", rows[2])
        self.assertIn("| [m1.f4.unverified](m1.f4.unverified/) | in progress |", rows[3])
        self.assertIn("| [m1.f5.specified](m1.f5.specified/) | specified |", rows[4])

    def test_a_verification_without_a_verdict_line_is_still_open(self):
        self.feature("m1.f1.a", verification_md="# A verification\n\n**Verdict**: [PASS | FAIL]\n", tasks_md=TASKS_DONE)
        self.run_index("features")
        self.assertIn("| in progress |", self.rows()[0])

    def test_summary_is_first_sentence_of_problem_statement(self):
        self.feature("m1.f1.a")
        r = self.run_index("features")
        self.assertIn("| Users cannot label transactions. |", self.rows()[0])
        self.assertNotIn("They want tags", self.read(".specs/features/AGENTS.md"))

    def test_placeholder_problem_statement_is_marked_not_filled(self):
        self.feature("m1.f1.a", spec=SPEC_PLACEHOLDER)
        self.feature("m1.f2.b", spec=None, tasks_md=TASKS_OPEN)
        self.run_index("features")
        rows = self.rows()
        self.assertIn("(spec not filled)", rows[0])
        self.assertIn("(spec not filled)", rows[1])

    def test_orders_by_milestone_then_feature_numerically(self):
        for name in ["m10.f1.j", "m4.f10.z", "m4.f2.y", "m2.f1.a", "m4.f1.x"]:
            self.feature(name)
        self.run_index("features")
        self.assertEqual(self.names(), ["m2.f1.a", "m4.f1.x", "m4.f2.y", "m4.f10.z", "m10.f1.j"])

    def test_legacy_folders_sit_inside_their_milestone_before_new_features_and_uncoded_last(self):
        for name in ["m5.f1.n", "m4.f1.x", "m4.1-b", "legacy-x", "m4-c", "m3-old"]:
            self.feature(name)
        self.run_index("features")
        self.assertEqual(self.names(), ["m3-old", "m4-c", "m4.1-b", "m4.f1.x", "m5.f1.n", "legacy-x"])

    def test_creates_claude_md_once(self):
        self.feature("m1.f1.a")
        self.run_index("features")
        self.assertEqual(self.read(".specs/features/CLAUDE.md").strip(), "@AGENTS.md")
        self.write(".specs/features/CLAUDE.md", "custom\n")
        self.run_index("features")
        self.assertEqual(self.read(".specs/features/CLAUDE.md"), "custom\n")

    def test_check_detects_stale_index(self):
        self.feature("m1.f1.a")
        self.run_index("features")
        self.assertEqual(self.run_index("features", "--check").returncode, 0)
        self.feature("m1.f2.b")
        self.assertEqual(self.run_index("features", "--check").returncode, 1)

    def test_missing_features_dir_is_a_noop(self):
        r = self.run_index("features")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.exists(".specs/features"))
        self.assertEqual(self.run_index("features", "--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
