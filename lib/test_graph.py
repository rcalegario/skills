import pytest

from lib.graph import find_cycle


@pytest.mark.parametrize("edges, expected", [
    ({}, None),
    ({"a": ["b"], "b": []}, None),
    ({"a": ["a"]}, None),                      # a self edge is ignored
    ({"a": ["zz"]}, None),                     # an edge to an unknown node is ignored
    ({"a": ["b"], "b": ["a"]}, ["a", "b", "a"]),
    ({"x": [], "a": ["b"], "b": ["c"], "c": ["b"]}, ["b", "c", "b"]),
])
def test_find_cycle(edges, expected):
    assert find_cycle(edges) == expected
