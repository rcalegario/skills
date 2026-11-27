import datetime

import pytest

from lib import yamlio


def test_load_returns_the_document(tmp_path):
    path = tmp_path / "a.yaml"
    path.write_text("a: 1\nb: [x, y]\n", encoding="utf-8")
    assert yamlio.load(str(path)) == {"a": 1, "b": ["x", "y"]}


@pytest.mark.parametrize("content", [None, "", "# only a comment\n"])
def test_load_gives_the_default_for_a_missing_or_empty_file(tmp_path, content):
    path = tmp_path / "a.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert yamlio.load(str(path), []) == []


def test_invalid_yaml_raises_one_error_naming_the_file(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("a: [\n", encoding="utf-8")
    with pytest.raises(yamlio.YamlError) as err:
        yamlio.load(str(path))
    assert str(err.value).startswith("%s is not valid YAML: " % path)


def test_load_error_points_at_the_file_not_a_string(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("[\n", encoding="utf-8")
    with pytest.raises(yamlio.YamlError) as err:
        yamlio.load(str(path))
    assert 'in "%s", line' % path in str(err.value)
    assert "<unicode string>" not in str(err.value)


def test_parse_reads_text_without_a_file():
    assert yamlio.parse("- 1\n- 2\n", "x.yaml") == [1, 2]


@pytest.mark.parametrize("text, expected", [
    ("---\ncode: NOW\nn: 2\n---\n# Title\n", {"code": "NOW", "n": 2}),
    ("---\r\ncode: NOW\r\n---\r\nbody\r\n", {"code": "NOW"}),
    ("---\n---\nbody\n", {}),
    ("# no header\n", {}),
])
def test_frontmatter(text, expected):
    assert yamlio.frontmatter(text) == expected


def test_today_is_the_iso_date():
    assert yamlio.today() == datetime.date.today().isoformat()


@pytest.mark.parametrize("ids, prefix, width, expected", [
    ([], "J", 3, "J-001"),
    (["J-001", "J-009"], "J", 3, "J-010"),
    (["D-01", "D-07", "V-09"], "D", 2, "D-08"),
    (["P-1", "P-12", "P-x", None], "P", 1, "P-13"),
    (["R-2"], "R", 1, "R-3"),
    (["D-99"], "D", 2, "D-100"),
])
def test_next_id(ids, prefix, width, expected):
    assert yamlio.next_id(ids, prefix, width) == expected


@pytest.mark.parametrize("value, expected", [
    (["T1", "T2"], ["T1", "T2"]),
    ([], []),
    (None, []),
    ("T1", []),
    (7, []),
    ({"a": 1}, []),
])
def test_as_list_returns_lists_only(value, expected):
    assert yamlio.as_list(value) == expected


def test_as_list_returns_the_same_list():
    value = ["T1"]
    assert yamlio.as_list(value) is value


@pytest.mark.parametrize("value, expected", [
    (None, False), ([], False), (["T1"], False), ("T1", True), (7, True), ({"a": 1}, True),
])
def test_not_a_list_flags_a_value_that_is_neither_a_list_nor_null(value, expected):
    assert yamlio.not_a_list(value) is expected


@pytest.mark.parametrize("content, message", [
    ("a: [\n", "is not valid YAML: "),
    ("- 1\n- 2\n", "must be a mapping at the top level"),
])
def test_load_mapping_exits_on_bad_yaml_or_non_mapping(tmp_path, capsys, content, message):
    path = tmp_path / "f.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as exit_:
        yamlio.load_mapping(str(path))
    assert exit_.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: %s " % path)
    assert message in err


def test_load_mapping_returns_the_text_and_the_mapping(tmp_path):
    path = tmp_path / "f.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    assert yamlio.load_mapping(str(path)) == ("a: 1\n", {"a": 1})


def test_list_errors_names_each_field_holding_a_single_value():
    entry = {"a": "T1", "b": ["T2"], "c": None, "d": {"x": 1}}
    assert yamlio.list_errors(entry, ("a", "b", "c", "d", "e"), "f.yaml: T1 ") == [
        "f.yaml: T1 a must be a list ([T1])",
        "f.yaml: T1 d must be a list ([{'x': 1}])",
    ]
