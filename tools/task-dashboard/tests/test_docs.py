"""docs.py: a task's Markdown files, listed and read only by their place in that list."""
import os

import docs
import state
from conftest import write

ALPHA = "tasks/skills/2026-11-12-0900-alpha/"


def add_docs(home):
    write(home, ALPHA + "brief.md", "---\ndate: 2026-11-12\n---\n\n# Brief of alpha\n\ntext\n")
    write(home, ALPHA + "context/now.md", "---\ncode: NOW\n---\n# NOW Facts\n")
    write(home, ALPHA + "Zeta.md", "no heading here\n## Second level only\n")
    write(home, ALPHA + ".specs/features/F1.1-x/spec.md", "# Spec x\n")
    write(home, ALPHA + "notes.txt", "# not markdown\n")
    write(home, ALPHA + "repos/skills/README.md", "# the worktree's\n")
    return os.path.join(str(home), *ALPHA.split("/"))


def test_listing_order_titles_and_exclusions(home):
    path = add_docs(home)
    listed = docs.listing(path)
    assert [d["path"] for d in listed] == [
        "README.md", "brief.md", "context/now.md", ".specs/features/F1.1-x/spec.md", "Zeta.md"]
    titles = {d["path"]: d["title"] for d in listed}
    assert titles == {"README.md": "alpha", "brief.md": "Brief of alpha", "context/now.md": "NOW Facts",
                      ".specs/features/F1.1-x/spec.md": "Spec x", "Zeta.md": "Zeta.md"}
    mtime = os.path.getmtime(os.path.join(path, "brief.md"))
    assert next(d for d in listed if d["path"] == "brief.md")["mtime"] == mtime


def test_text_drops_the_front_matter(home):
    path = add_docs(home)
    assert docs.text(path, "brief.md") == "\n# Brief of alpha\n\ntext\n"
    assert docs.text(path, "README.md").startswith("\n# alpha")
    assert docs.text(path, "Zeta.md") == "no heading here\n## Second level only\n"


def test_text_refuses_what_the_list_does_not_hold(home):
    path = add_docs(home)
    for rel in ("notes.txt", "repos/skills/README.md", "acs.yaml", "../2026-11-12-0900-alpha/brief.md",
                "context/../brief.md", "missing.md", "", "/etc/passwd"):
        assert docs.text(path, rel) is None, rel


def test_task_payload_carries_the_docs(home):
    add_docs(home)
    detail = state.task_detail(str(home), "skills", "2026-11-12-0900-alpha")
    assert [d["path"] for d in detail["docs"]][:2] == ["README.md", "brief.md"]


def test_task_doc_finds_current_tasks_only(home):
    add_docs(home)
    assert state.task_doc(str(home), "skills", "2026-11-12-0900-alpha", "brief.md").startswith("\n# Brief")
    assert state.task_doc(str(home), "iac", "2026-11-10-1000-old", "README.md") is None
    assert state.task_doc(str(home), "skills", "nope", "README.md") is None


def test_front_matter_is_a_yaml_mapping_only(home):
    path = os.path.join(str(home), *ALPHA.split("/"))
    write(home, ALPHA + "bom.md", "\ufeff---\ncode: X\n---\n# Bom title\n")
    write(home, ALPHA + "empty.md", "---\n---\n# Empty front\n")
    write(home, ALPHA + "rule.md", "---\n\nSome text between rules\n\n---\n# Rule title\n")
    assert docs.text(path, "bom.md") == "# Bom title\n"
    assert docs.text(path, "empty.md") == "# Empty front\n"
    assert docs.text(path, "rule.md") == "---\n\nSome text between rules\n\n---\n# Rule title\n"
    titles = {d["path"]: d["title"] for d in docs.listing(path)}
    assert titles["bom.md"] == "Bom title" and titles["empty.md"] == "Empty front"


def test_title_skips_code_blocks(home):
    path = os.path.join(str(home), *ALPHA.split("/"))
    write(home, ALPHA + "code.md", "Intro\n\n```bash\n# a shell comment\n```\n\n~~~\n# another\n~~~\n")
    write(home, ALPHA + "late.md", "```\n# comment\n```\n\n# Real title\n")
    titles = {d["path"]: d["title"] for d in docs.listing(path)}
    assert titles["code.md"] == "code.md" and titles["late.md"] == "Real title"
