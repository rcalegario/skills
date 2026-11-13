"""Tests for scripts/specs.py, driven through its CLI only."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "specs.py"


class Project(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
            capture_output=True, text=True,
        )

    def ok(self, *args):
        r = self.run_cli(*args)
        self.assertEqual(r.returncode, 0, f"{args} failed:\n{r.stdout}{r.stderr}")
        return r.stdout

    def fails(self, *args, msg=None):
        r = self.run_cli(*args)
        self.assertNotEqual(r.returncode, 0, f"{args} should fail:\n{r.stdout}")
        if msg:
            self.assertIn(msg, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def roadmap(self):
        return yaml.safe_load((self.root / ".specs/ROADMAP.yaml").read_text())

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text))

    def feature(self, rel):
        return self.root / ".specs/features" / rel


class RoadmapTest(Project):
    def test_init_creates_an_empty_roadmap_that_checks_clean(self):
        self.ok("init", "my-app")
        self.assertEqual(self.roadmap(), {"project": "my-app", "milestones": []})
        self.ok("check")

    def test_init_refuses_to_overwrite(self):
        self.ok("init", "my-app")
        self.fails("init", "my-app", msg="already exists")

    def test_add_milestone_and_features_numbers_them(self):
        self.ok("init", "my-app")
        self.ok("milestone", "MVP", "--goal", "users can list items")
        self.ok("milestone", "Sharing")
        out = self.ok("add", "m1", "export-csv", "Export items as CSV")
        self.assertIn("m1.f1", out)
        self.ok("add", "m1", "import-csv", "Import items")
        self.ok("add", "m2", "share-link", "Share a link")
        rm = self.roadmap()
        self.assertEqual([m["id"] for m in rm["milestones"]], ["m1", "m2"])
        self.assertEqual(rm["milestones"][0]["goal"], "users can list items")
        self.assertEqual(
            [(f["id"], f["slug"], f["status"]) for f in rm["milestones"][0]["features"]],
            [("m1.f1", "export-csv", "todo"), ("m1.f2", "import-csv", "todo")],
        )
        self.assertEqual(rm["milestones"][1]["features"][0]["id"], "m2.f1")
        self.ok("check")

    def test_add_rejects_unknown_milestone_and_bad_slug(self):
        self.ok("init", "my-app")
        self.ok("milestone", "MVP")
        self.fails("add", "m9", "x", "X", msg="m9")
        self.fails("add", "m1", "Bad Slug", "X", msg="slug")

    def test_check_reports_hand_edit_mistakes(self):
        self.write(".specs/ROADMAP.yaml", """\
            project: my-app
            milestones:
              - id: m1
                title: MVP
                features:
                  - {id: m1.f1, slug: a, title: A, status: todo}
                  - {id: m1.f1, slug: b, title: B, status: wip}
                  - {id: m2.f3, slug: c, title: C, status: todo}
            """)
        out = self.fails("check")
        self.assertIn("duplicate", out)
        self.assertIn("wip", out)
        self.assertIn("m2.f3", out)

    def test_missing_roadmap_says_how_to_start(self):
        self.fails("check", msg="init")


GOOD_SPEC = """\
    # Export items as CSV

    ## Problem
    Users copy rows by hand.

    ## Acceptance criteria
    - **AC1**: WHEN the user clicks "Export" THEN a CSV of the filtered rows downloads
    - **AC2**: IF the list is empty THEN the page shows "Nothing to export"
    - **AC3**: ALWAYS amounts are written in cents

    ## Out of scope
    - Excel format
    """


class SpecTest(Project):
    def setUp(self):
        super().setUp()
        self.ok("init", "my-app")
        self.ok("milestone", "MVP")
        self.ok("add", "m1", "export-csv", "Export items as CSV")
        self.spec = self.feature("m1.f1.export-csv/spec.md")

    def status(self):
        return self.roadmap()["milestones"][0]["features"][0]["status"]

    def test_start_creates_spec_from_template_and_moves_to_spec(self):
        out = self.ok("start", "m1.f1")
        self.assertTrue(self.spec.exists())
        self.assertIn("## Acceptance criteria", self.spec.read_text())
        self.assertIn("spec.md", out)
        self.assertEqual(self.status(), "spec")
        self.fails("start", "m1.f1", msg="todo")

    def test_feature_accepts_full_folder_name_and_rejects_unknown(self):
        self.ok("start", "m1.f1.export-csv")
        self.fails("check", "m1.f9", msg="m1.f9")

    def test_template_spec_cannot_be_approved(self):
        self.ok("start", "m1.f1")
        self.fails("approve", "m1.f1", "spec", msg="TODO")

    def test_approve_spec_records_date_and_moves_to_tasks(self):
        self.ok("start", "m1.f1")
        self.write(".specs/features/m1.f1.export-csv/spec.md", GOOD_SPEC)
        self.ok("check", "m1.f1")
        self.ok("approve", "m1.f1", "spec")
        f = self.roadmap()["milestones"][0]["features"][0]
        self.assertEqual(f["status"], "tasks")
        self.assertIn("spec", f["approved"])
        self.fails("approve", "m1.f1", "spec", msg="status")

    def test_criteria_must_use_a_keyword_and_be_unique(self):
        self.ok("start", "m1.f1")
        self.write(".specs/features/m1.f1.export-csv/spec.md", GOOD_SPEC.replace(
            "- **AC3**: ALWAYS amounts are written in cents",
            "- **AC3**: export works well\n    - **AC2**: WHEN x THEN y\n    - **AC4**: WHEN x happens"))
        out = self.fails("check", "m1.f1")
        self.assertIn("AC3", out)
        self.assertIn("duplicate AC2", out)
        self.assertIn("AC4", out)

    def test_spec_without_criteria_fails(self):
        self.ok("start", "m1.f1")
        self.write(".specs/features/m1.f1.export-csv/spec.md", "# X\n\n## Problem\nY\n")
        self.fails("check", "m1.f1", msg="no acceptance criteria")


GOOD_TASKS = """\
    feature: m1.f1.export-csv
    test: npm test
    tasks:
      - id: T1
        title: Download filtered rows as CSV
        covers: [AC1, AC3]
        blocked_by: []
        commit: "feat(export): let users download the filtered list as CSV"
        status: todo
      - id: T2
        title: Empty-list message
        covers: [AC2]
        blocked_by: [T1]
        commit: "feat(export): tell users when there is nothing to export"
        status: todo
    checks:
      - {ac: AC1, test: "export.test.ts > downloads filtered rows", status: pending}
      - {ac: AC2, manual: "Clear the list, click Export, read the message", status: pending}
      - {ac: AC3, test: "export.test.ts > writes cents", status: pending}
    """


class TasksTest(Project):
    def setUp(self):
        super().setUp()
        self.ok("init", "my-app")
        self.ok("milestone", "MVP")
        self.ok("add", "m1", "export-csv", "Export items as CSV")
        self.ok("start", "m1.f1")
        self.write(".specs/features/m1.f1.export-csv/spec.md", GOOD_SPEC)
        self.ok("approve", "m1.f1", "spec")
        self.tasks_path = self.feature("m1.f1.export-csv/tasks.yaml")

    def tasks(self):
        return yaml.safe_load(self.tasks_path.read_text())

    def put_tasks(self, text):
        self.write(".specs/features/m1.f1.export-csv/tasks.yaml", text)

    def test_approving_spec_writes_a_tasks_skeleton_with_one_check_per_ac(self):
        t = self.tasks()
        self.assertEqual(t["feature"], "m1.f1.export-csv")
        self.assertEqual([c["ac"] for c in t["checks"]], ["AC1", "AC2", "AC3"])
        self.fails("approve", "m1.f1", "tasks", msg="TODO")

    def test_good_tasks_check_and_approve(self):
        self.put_tasks(GOOD_TASKS)
        self.ok("check", "m1.f1")
        self.ok("approve", "m1.f1", "tasks")
        f = self.roadmap()["milestones"][0]["features"][0]
        self.assertEqual(f["status"], "doing")
        self.assertEqual(set(f["approved"]), {"spec", "tasks"})

    def test_approving_tasks_records_git_base_for_review(self):
        git = ["git", "-C", str(self.root)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "base"], check=True)
        head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.put_tasks(GOOD_TASKS)
        self.ok("approve", "m1.f1", "tasks")
        self.assertEqual(self.tasks()["base"], head)

    def test_every_ac_needs_a_task_and_a_check(self):
        self.put_tasks(GOOD_TASKS
                       .replace("covers: [AC1, AC3]", "covers: [AC1]")
                       .replace('      - {ac: AC2, manual: "Clear the list, click Export, read the message", status: pending}\n', ""))
        out = self.fails("check", "m1.f1")
        self.assertIn("AC3 is covered by no task", out)
        self.assertIn("AC2 has no check", out)

    def test_references_must_exist_and_have_no_cycle(self):
        self.put_tasks(GOOD_TASKS
                       .replace("covers: [AC2]", "covers: [AC2, AC9]")
                       .replace("blocked_by: []", "blocked_by: [T2]")
                       .replace("{ac: AC3,", "{ac: AC7,"))
        out = self.fails("check", "m1.f1")
        self.assertIn("AC9", out)
        self.assertIn("AC7", out)
        self.assertIn("cycle", out)

    def test_field_mistakes_are_reported(self):
        self.put_tasks(GOOD_TASKS
                       .replace("id: T2", "id: T1")
                       .replace('commit: "feat(export): tell users when there is nothing to export"', "commit: ''")
                       .replace("status: todo\n      - id", "status: started\n      - id")
                       .replace('manual: "Clear the list, click Export, read the message"',
                                'manual: "x", test: "y"'))
        out = self.fails("check", "m1.f1")
        self.assertIn("duplicate task T1", out)
        self.assertIn("commit", out)
        self.assertIn("started", out)
        self.assertIn("exactly one of", out)

    def test_suite_command_is_required(self):
        self.put_tasks(GOOD_TASKS.replace("test: npm test", "test: 'TODO: command'"))
        self.fails("check", "m1.f1", msg="suite")

    def test_done_task_with_open_blocker_is_inconsistent(self):
        self.put_tasks(GOOD_TASKS.replace("status: todo\n    checks", "status: done\n    checks"))
        self.fails("check", "m1.f1", msg="T1")


class ExecuteTest(Project):
    def setUp(self):
        super().setUp()
        self.ok("init", "my-app")
        self.ok("milestone", "MVP")
        self.ok("add", "m1", "export-csv", "Export items as CSV")
        self.ok("add", "m1", "import-csv", "Import items")
        self.ok("start", "m1.f1")
        self.write(".specs/features/m1.f1.export-csv/spec.md", GOOD_SPEC)
        self.ok("approve", "m1.f1", "spec")
        self.write(".specs/features/m1.f1.export-csv/tasks.yaml", GOOD_TASKS)

    def tasks(self):
        return yaml.safe_load(self.feature("m1.f1.export-csv/tasks.yaml").read_text())

    def test_tasks_cannot_move_before_tasks_are_approved(self):
        self.fails("set", "m1.f1", "T1", "doing", msg="doing")

    def test_task_lifecycle_respects_blockers(self):
        self.ok("approve", "m1.f1", "tasks")
        self.fails("set", "m1.f1", "T2", "done", msg="T1")
        self.ok("set", "m1.f1", "T1", "doing")
        self.ok("set", "m1.f1", "T1", "done")
        self.ok("set", "m1.f1", "T2", "done")
        self.assertEqual([t["status"] for t in self.tasks()["tasks"]], ["done", "done"])
        self.fails("set", "m1.f1", "T9", "done", msg="T9")
        self.fails("set", "m1.f1", "T1", "finished", msg="finished")

    def test_commit_msg_prints_the_prepared_message(self):
        out = self.ok("commit-msg", "m1.f1", "T2")
        self.assertEqual(out.strip(), "feat(export): tell users when there is nothing to export")

    def test_status_shows_progress_and_next_task(self):
        self.ok("approve", "m1.f1", "tasks")
        self.ok("set", "m1.f1", "T1", "done")
        out = self.ok("status")
        self.assertIn("m1.f1", out)
        self.assertIn("doing", out)
        self.assertIn("1/2", out)
        self.assertIn("next: T2", out)
        self.assertIn("m1.f2", out)

    def test_finish_needs_every_task_done_and_check_passed(self):
        self.ok("approve", "m1.f1", "tasks")
        self.ok("set", "m1.f1", "T1", "done")
        self.ok("set", "m1.f1", "T2", "done")
        self.ok("set", "m1.f1", "AC1", "pass")
        self.ok("set", "m1.f1", "AC3", "fail")
        out = self.fails("finish", "m1.f1")
        self.assertIn("AC2", out)
        self.assertIn("AC3", out)
        self.ok("set", "m1.f1", "AC2", "pass")
        self.ok("set", "m1.f1", "AC3", "pass")
        self.ok("finish", "m1.f1")
        f = self.roadmap()["milestones"][0]["features"][0]
        self.assertEqual(f["status"], "done")
        self.assertIn("done", f)
        self.ok("check", "m1.f1")

    def test_finish_refuses_open_tasks(self):
        self.ok("approve", "m1.f1", "tasks")
        for ac in ("AC1", "AC2", "AC3"):
            self.ok("set", "m1.f1", ac, "pass")
        self.fails("finish", "m1.f1", msg="T1")


if __name__ == "__main__":
    unittest.main()
