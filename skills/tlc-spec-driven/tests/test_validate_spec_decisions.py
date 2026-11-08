#!/usr/bin/env python3
"""Tests for where validate_spec.py finds the active decision that approves a departure from a
binding source: docs/adr/AD-*.md (Status: active), with .specs/STATE.md as the legacy fallback.

Run: python3 -m unittest discover -s tests   (from the skill directory)
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

SPEC = """# Billing

## Problem Statement

Users cannot update their card.

## Out of Scope

- Invoices

## Assumptions & Open Questions

| Assumption | Chosen default | Rationale |
| --- | --- | --- |
| Card form is one screen | one screen | simplest |

**Open questions: none**

## Sources

- the billing frame from the design file - binding - the card form

## Differences from the source

| Source says | Product does | Confirmed |
| --- | --- | --- |
| Update card | Atualizar cartao | y - %s |

## User Stories

### P1: Update the card

**Acceptance Criteria**

1. WHEN the user submits a new card THEN the system SHALL store it

## Requirement Traceability

| Requirement ID | Story | Status |
| --- | --- | --- |
| BIL-01 | P1 | pending |
"""


def adr(num, status):
    return (f"# AD-{num:03d}: Billing copy is Portuguese\n\n- **Decision**: Copy is Portuguese\n"
            f"- **Reason**: asked, answered\n- **Trade-off**: none\n- **Scope**: billing\n"
            f"- **Date**: 2026-11-08\n- **Status**: {status}\n")


class DecisionLookupTest(unittest.TestCase):
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

    def validate(self, cites="AD-002"):
        self.write(".specs/features/m1.f1.billing/spec.md", SPEC % cites)
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "validate_spec.py"), "--root", self.root,
             os.path.join(self.root, ".specs", "features", "m1.f1.billing")],
            capture_output=True, text=True,
        )

    def test_active_adr_file_approves_the_departure(self):
        self.write("docs/adr/AD-002-copy-in-portuguese.md", adr(2, "active"))
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_superseded_adr_file_does_not_approve_it(self):
        self.write("docs/adr/AD-002-copy-in-portuguese.md", adr(2, "superseded by AD-003"))
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("AD-NNN", r.stdout)

    def test_citing_an_id_with_no_adr_fails(self):
        self.write("docs/adr/AD-001-other.md", adr(1, "active"))
        r = self.validate()
        self.assertEqual(r.returncode, 1)

    def test_legacy_state_md_decision_still_approves_it(self):
        self.write(".specs/STATE.md", "## Decisions\n\n| AD-002 | copy is Portuguese | active | 2026-10-23 |\n")
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_adr_filename_id_is_what_counts_not_a_mention_in_the_body(self):
        self.write("docs/adr/AD-005-x.md", adr(5, "active").replace("Copy is Portuguese", "see AD-002"))
        r = self.validate()
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
