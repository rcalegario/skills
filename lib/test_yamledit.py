import datetime

import pytest
import yaml

from lib import yamledit as ye


def L(text):
    return ye.split_lines(text)


def test_block_end_skips_blanks_and_comments():
    lines = L("a:\n  b: 1\n\n  # note\n  c: 2\nd: 3\n")
    assert ye.block_end(lines, 0, 0) == 5


def test_item_blocks_finds_quoted_and_plain_ids():
    lines = L("- id: X-1\n  text: a\n- id: \"X-2\"  # c\n  text: b\n")
    assert ye.item_blocks(lines, "id", "X-1") == [(0, 2, 2)]
    assert ye.item_blocks(lines, "id", "X-2") == [(2, 4, 2)]


def test_set_key_replaces_keeping_the_comment_and_inserts_after_an_anchor():
    lines = L("- id: A\n  status: old  # why\n  text: t\n")
    assert ye.set_key(lines, 0, 3, 2, "status", "new") == 0
    assert lines[1] == "  status: new  # why\n"
    assert ye.set_key(lines, 0, 3, 2, "date", "2026-01-01", after="status") == 1
    assert lines[2] == "  date: 2026-01-01\n"


def test_set_key_refuses_a_key_written_twice():
    with pytest.raises(AssertionError):
        ye.set_key(L("a: 1\na: 2\n"), 0, 2, 0, "a", "3")


def test_set_top_and_set_child():
    lines = L("id: F\napproved: {spec: null}\nbase: null\n")
    ye.set_top(lines, "base", "abc")
    ye.set_child(lines, "approved", "spec", "2026-01-01")
    data = yaml.safe_load("".join(lines))
    assert data == {"id": "F", "approved": {"spec": datetime.date(2026, 1, 1)}, "base": "abc"}


def test_set_child_creates_a_missing_parent_after_an_anchor():
    lines = L("id: F\nsize: M\n")
    ye.set_child(lines, "approved", "tasks", "null", after="id")
    assert "".join(lines) == "id: F\napproved:\n  tasks: null\nsize: M\n"


@pytest.mark.parametrize("value, line", [
    ([], "[]"), (["D-01", "a b"], '[D-01, "a b"]'), (None, "null"), (True, "true"), (3, "3"),
    ("2026-11-23", "2026-11-23"), ("plain-word_1.x", "plain-word_1.x"), ("yes", '"yes"'),
    ("12", '"12"'), ("has: colon", '"has: colon"'), ("ação", '"ação"'),
])
def test_scalar(value, line):
    assert ye.scalar(value) == line


def test_render_block_text_dict_and_quoted():
    assert ye.render("t", "one\ntwo\n") == ["t: |\n", "  one\n", "  two\n"]
    assert ye.render("m", {"a": 1, "b": "x y"}) == ["m:\n", "  a: 1\n", '  b: "x y"\n']
    assert ye.render("h", ye.Quoted("0123")) == ['h: "0123"\n']


def test_put_replaces_a_whole_block_and_its_unindented_list():
    lines = L("a: 1  # keep\nlist:\n- x\n- y\nz: 2\n")
    ye.put(lines, "list", ["q"])
    ye.put(lines, "a", 5)
    ye.put(lines, "new", "v", after="a")
    assert "".join(lines) == "a: 5  # keep\nnew: v\nlist: [q]\nz: 2\n"


def test_item_lines():
    assert ye.item_lines([("id", "J-001"), ("refs", [])]) == ["- id: J-001\n", "  refs: []\n"]


def test_append_item_replaces_an_empty_list(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("[]\n", encoding="utf-8")
    ye.append_item(str(path), ye.item_lines([("id", "P-1")]), [])
    ye.append_item(str(path), ye.item_lines([("id", "P-2")]), [{"id": "P-1"}])
    assert path.read_text(encoding="utf-8") == "- id: P-1\n\n- id: P-2\n"


def test_edit_writes_only_a_verified_change(tmp_path):
    path = tmp_path / "f.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    data = ye.edit(str(path), None, lambda ls: ye.set_top(ls, "a", "2"), lambda d: d["a"] == 2)
    assert data == {"a": 2} and path.read_text(encoding="utf-8") == "a: 2\n"
    with pytest.raises(ye.EditError, match="did not apply"):
        ye.edit(str(path), "a: 2", lambda ls: None, lambda d: d["a"] == 3)
    assert path.read_text(encoding="utf-8") == "a: 2\n"


@pytest.mark.parametrize("text, end", [
    ("---\na: 1\n---\nbody\n", 2), ("---\na: 1\n", -1), ("body\n", None), ("", None),
])
def test_header_end(text, end):
    assert ye.header_end(L(text)) == end


def test_edit_keeps_lf_endings(tmp_path):
    path = tmp_path / "f.yaml"
    ye.write_lines(str(path), ["a: 1\n"], lambda d: True)
    assert path.read_bytes() == b"a: 1\n"
