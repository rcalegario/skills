# lib

Generic helpers shared by the skills' scripts (today `task` and `flow`), so each exists once.

**Rule:** nothing here names a file, field or status of any skill. A helper that knows what a skill's files mean (a roadmap, a feature, a decision) stays in that skill's scripts. `test_generic.py` fails when a module here names one.

| Module | Holds |
|---|---|
| `yamlio.py` | `read`, `parse` and `load` of YAML files with one error (`YamlError`: `<path> is not valid YAML: ...`), `load_mapping` (`(text, data)` of a file whose top level is a mapping; otherwise `ERROR: <path> ...` on stderr and exit 1), `as_list` (a list, or `[]` for anything else), `not_a_list`, `list_errors` (one message per field holding a single value), `frontmatter` (and `FRONTMATTER_RE`, its pattern, for a caller that keeps the header text), `today`, `next_id` |
| `modules.py` | `load(path, name)`: the module in a file, registered under `name`, with `sys.path` left alone, so a skill uses another skill's module without that folder's module names shadowing its own |
| `yamledit.py` | line edits that keep comments and order: `read_lines`, `split_lines`, `block_end`, `set_key`, `set_top`, `set_child`, `put`, `render`, `scalar` (`Quoted` forces quotes), `item_blocks`, `item_lines`, `header_end`; `edit`, `write_lines` and `append_item` write only a change that `verify` confirms (`EditError` otherwise) |
| `gitutil.py` | `git`, `head_sha`, `commit_exists` |
| `fakegit.py` | for tests: `install(monkeypatch)` points `gitutil` at an in-memory git (`init`, `track`, `commit`) that answers the commands `gitutil` sends, without a process; `test_fakegit.py` runs the same history on real git |
| `graph.py` | `find_cycle` over `{node: [nodes]}` |

## Use from a skill

A skill's script reaches this folder through the real path of its own file, so it works when `~/.claude/skills/<name>` is a link to this repo:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from lib import yamlio  # noqa: E402
```

A skill copied out of this repo alone does not find `lib/`.

## Tests

`test.cmd` is the one-line test command, run from this folder. The root pre-commit hook runs it when a commit stages a file under `lib/`. When the staged files are only modules (`lib/<m>.py`), it also runs the tests of the skills and tools whose code imports one of them, directly, through another lib module, or through another skill's scripts; any other staged `lib/` file (`__init__.py`, `test.cmd`, this README) runs the tests of every skill and tool.
