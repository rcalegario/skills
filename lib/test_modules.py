import sys

from lib import modules


def write(tmp_path, folder, text):
    path = tmp_path / folder / "commands.py"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_load_by_path_leaves_sys_path_alone(tmp_path, monkeypatch):
    path = write(tmp_path, "other", "WHO = 'other'\n")
    monkeypatch.delitem(sys.modules, "commands", raising=False)
    before = list(sys.path)
    module = modules.load(path, "other_commands")
    assert module.WHO == "other"
    assert sys.path == before
    assert "commands" not in sys.modules


def test_a_module_named_like_the_loaded_file_still_loads_the_callers_own(tmp_path, monkeypatch):
    other = write(tmp_path, "other", "WHO = 'other'\n")
    own = write(tmp_path, "own", "WHO = 'own'\n")
    monkeypatch.syspath_prepend(str(tmp_path / "own"))
    monkeypatch.delitem(sys.modules, "commands", raising=False)
    loaded = modules.load(other, "other_commands_2")
    import commands
    assert (loaded.WHO, commands.WHO) == ("other", "own")
    assert commands.__file__ == own


def test_load_twice_under_one_name_gives_the_same_module(tmp_path):
    path = write(tmp_path, "twice", "WHO = 'twice'\n")
    assert modules.load(path, "twice_commands") is modules.load(path, "twice_commands")
