#!/usr/bin/env python3
"""Tests for the feature-folder-name gate in validate_spec.py, driven through its CLI on
throwaway projects.

Folder name: m<N>.f<N>.<slug>  (milestone, feature inside it, kebab-case slug).

Run: python3 -m unittest discover -s tests   (from the skill directory)
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

SPEC = """# Tags

## Problem Statement

Users cannot label transactions.

## Out of Scope

- Nested tags

## Assumptions & Open Questions

| Assumption | Chosen default | Rationale |
| --- | --- | --- |
| Tags are flat | flat list | simplest |

**Open questions: none**

## User Stories

### P1: Add a tag

**Acceptance Criteria**

1. WHEN the user adds a tag THEN the system SHALL store it

## Requirement Traceability

| Requirement ID | Story | Status |
| --- | --- | --- |
| TAG-01 | P1 | pending |
"""


def run(*args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "validate_spec.py"), *args],
        capture_output=True, text=True,
    )


class FeatureFolderGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def spec_in(self, name):
        fdir = os.path.join(self.root, ".specs", "features", name)
        os.makedirs(fdir)
        with open(os.path.join(fdir, "spec.md"), "w", encoding="utf-8") as f:
            f.write(SPEC)
        return fdir

    def test_milestone_and_feature_code_passes(self):
        r = run(self.spec_in("m2.f1.tags"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_multi_digit_codes_and_hyphenated_slug_pass(self):
        r = run(self.spec_in("m12.f10.recurring-sort"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_milestone_only_folder_fails_and_names_the_format(self):
        r = run(self.spec_in("m2-tags"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("m<N>.f<N>.<slug>", r.stdout)

    def test_old_sub_milestone_folder_fails(self):
        r = run(self.spec_in("m4.1-recurrence-sorting"))
        self.assertEqual(r.returncode, 1)

    def test_folder_without_any_code_fails(self):
        r = run(self.spec_in("tags"))
        self.assertEqual(r.returncode, 1)

    def test_feature_zero_fails(self):
        r = run(self.spec_in("m2.f0.tags"))
        self.assertEqual(r.returncode, 1)

    def test_uppercase_code_fails(self):
        r = run(self.spec_in("M2.F1.tags"))
        self.assertEqual(r.returncode, 1)

    def test_allow_legacy_downgrades_old_names_to_a_warning(self):
        r = run(self.spec_in("m2-tags"), "--allow-legacy")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("WARN", r.stdout)
        self.assertIn("legacy folder name", r.stdout)

    def test_allow_legacy_still_fails_a_malformed_new_name(self):
        r = run(self.spec_in("m2.f0.tags"), "--allow-legacy")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
