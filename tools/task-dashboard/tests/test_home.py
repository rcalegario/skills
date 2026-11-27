"""home.py: where the home is, and which folders under it are tasks."""
import pytest
from conftest import write

import home as homemod


def test_home_from_config_or_exit_2(tmp_path, capsys):
    write(tmp_path, "config.yaml", "home: /some/where\n")
    assert homemod.resolve_home(None, str(tmp_path / "config.yaml")) == "/some/where"
    assert homemod.resolve_home("/given", str(tmp_path / "config.yaml")) == "/given"
    for config in (str(tmp_path / "missing.yaml"), str(tmp_path / "empty.yaml")):
        write(tmp_path, "empty.yaml", "other: 1\n")
        with pytest.raises(SystemExit) as exc:
            homemod.resolve_home(None, config)
        assert exc.value.code == 2
        assert "no home: pass --home or set home in skills/task/config.yaml" in capsys.readouterr().err


def test_task_folders_skip_non_tasks(home):
    found = [(f.repo, f.id, f.legacy) for f in homemod.task_folders(str(home))]
    assert found == [("iac", "2026-11-10-1000-old", True), ("skills", "2026-11-12-0900-alpha", False)]


def test_legacy_folder_without_acs_is_a_task(home):
    write(home, "tasks/iac/2026-11-01-0800-oldest/diario.yaml", "[]\n")
    found = [(f.id, f.legacy) for f in homemod.task_folders(str(home))]
    assert ("2026-11-01-0800-oldest", True) in found
