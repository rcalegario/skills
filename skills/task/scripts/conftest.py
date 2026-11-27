"""Shared fixtures of the task scripts' tests."""
import pytest

FILES = {
    "README.md": "---\nid: 2026-11-20-1000-x\ntitle: X\nrepos:\n  - name: app\n    main: true\n---\n\n# X\n",
    "acs.yaml": ("- id: AC-1\n  text: t\n  status: decided\n  requirements:\n"
                 "    - id: AC-1.1\n      text: r\n      status: decided\n      decision: D-01\n      validations: [V-01]\n"),
    "decisions/D-01-source.yaml": ("id: D-01\ntitle: T\nstatus: decided\ndate: 2026-11-20\nborn_from: []\n"
                                   "discuss_with: [me]\nquestion: Q?\ndecision: A\nwhy: W\n"),
    "decisions/D-02-name.yaml": "id: D-02\ntitle: N\nstatus: open\nborn_from: [D-01]\ndiscuss_with: [me]\nquestion: Q?\n",
    "validations/V-01-seen.yaml": "id: V-01\ntitle: S\nstatus: pending\nhow: look\n",
    "journal.yaml": "- id: J-001\n  date: 2026-11-20\n  type: note\n  text: see NOW-1 and D-01\n  refs: [D-01]\n",
    "pending.yaml": "- id: P-1\n  status: open\n  with: [me]\n  action: ask about D-02\n  refs: [D-02]\n",
    "context/now.md": "---\ncode: NOW\ntitle: Now\nread_on: 2026-11-20\n---\n\n# Now\r\n\r\n## NOW-1 Fact\r\n",
    "brief.md": ("---\ncode: BRIEF\ndate: 2026-11-20\nsources:\n  context: \"x\"\n  acs: \"y\"\n  decisions: \"z\"\n---\n\n"
                 "## BRIEF-2 Target\n\nD-01 and NOW-1\n\n## BRIEF-4 Open items\n"),
    ".specs/roadmap.yaml": ("vision: v\nmilestones:\n  - id: M1\n    title: M\n    status: building\n    features:\n"
                            "      - id: F1.1\n        title: F\n        status: building\n        decisions: [D-01]\n"
                            "        blocked_by: []\n"),
    ".specs/features/F1.1-a/feature.yaml": ("id: F1.1-a\ntitle: A\nroadmap: F1.1\nrepo: app\nsize: M\nstatus: building\n"
                                            "story:\n  decisions: [D-01]\n  validations: [V-01]\n"),
    ".specs/features/F1.1-a/spec.md": "# A\n\nBuilds D-01.\n",
}


@pytest.fixture
def task(tmp_path):
    root = tmp_path / "app" / "2026-11-20-1000-x"
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return root
