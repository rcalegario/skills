# task-dashboard

A local, read-only web page of every task folder the `/task` skill keeps in the home (`<home>/tasks/<repo>/<task>/`). It reads the files on each request, takes every status from the `task` skill's `status.py`, and never writes.

## Run

```sh
python tools/task-dashboard/dashboard.py [--home DIR] [--port 8765] [--no-browser]
```

It needs Python 3 with PyYAML. The Graph tab also loads Cytoscape.js 3.30.2, elkjs 0.9.3 and cytoscape-elk 2.2.0 from a CDN (cdnjs, jsdelivr), pinned, the first time it opens, and the Docs tab marked 15.0.6 and mermaid 11.4.1 the same way; without network the other tabs still work. The home comes from `home:` in `skills/task/config.yaml` unless `--home` is given. The server listens on `127.0.0.1` only and opens the browser on its URL.

## Page

- **Tasks** (`#`): every task in one list, newest activity first, one row each on fixed columns that line up from row to row: its main repo, its title with the folder id below, the step's reason summarized, the `/task` step after a dot in that step's color, the items bar with `n/m items` concluded, and the time since its last activity (`now`, `5 min`, `3 h`, `2 d`). A title, repo or reason too long for its column ends in `…` and shows whole on hover. Below 860 px a row takes three lines: the title with the step at the right; the repo and the folder id; the reason, then the items and the time in fixed columns. Broken tasks, then legacy ones, go last, on the same columns: their folder id as the title, the step `error` or `legacy`, a broken task's error as its reason in red, no items nor time. A click anywhere on a row, or Enter on its title, opens its task's page; legacy and broken rows open nothing.

  The reason groups the blockers `status.py` gives for the step, one phrase per kind and state, in its order: `D-01 open`, `2 decisions open (D-01, D-04)`, `F1.1 in review`, `6 features without PR (F1.1–F3.1)` (up to three ids listed, `first–last` beyond; a feature by its roadmap id), `AC-1 without pr_note`, `spike V-02 pending`, `no brief`, `brief behind context, decisions`, `no roadmap`, `worktree skills left`. A blocker of a kind the page does not know shows `status.py`'s reason as it is, and a `done` task shows none. The hover gives `status.py`'s full reason. A `!` in a red circle opens the reason when the next action is the user's (`status.py`'s `your_turn`); without it the reason starts at the same place. When `status.py` finds failures in the task folder, the reason reads `n check failures` in red after the `!`, on any step, and the hover lists each failure.

  Above the list, a chain of step chips filters it: the nine steps in the order of the `/task` state machine, joined by arrows (`decide → consolidate → plan → build → review → pr → finish → done`, with `spike` as a detour from plan to build), then `legacy` and `error` after a divider, each with its task count; a step this page does not know yet gets its own chip after `error`. A click (or Space) on a chip hides its tasks and turns it grey; the header then reads `n of m tasks`. The hidden steps are kept in the browser's `localStorage`; with nothing stored, `done` and `legacy` start hidden. When storage is blocked, the filter works for the session only.
- **Task page** (`#task=<repo>/<id>&tab=<tab>`): one task only, with a link back to all tasks, its title, its step and why, and tabs:
  - **Summary**: two columns (one below 860 px, the work first). Left, the work: the **Next** panel (your turn or waiting on others, the step and what it waits for, up to five numbered actions, who else holds what and your follow-ups), then the **items still open**, each with its open requirements and what each needs, and the concluded items on one line. Right, the sidebar: **Progress** (the items bar; items concluded, features done, validations passed, decisions open), **Checks** (status.py's failures and warnings grouped by kind, ids, fix and messages unfolding; one green line when clean) and **Lately** (the last four journal notes as one line each, unfolding, with a link to the Journal tab).
  - **Requirements**: each item with its requirements (status, decision tree, validations, what is missing) and its PR note.
  - **Graph**: the items, requirements, decisions, features (planned ones too) and validations as a graph, laid out by ELK in one column per kind and colored by status. A click lights the node's whole chain and fades the rest (Esc or a click on the background clears it); a double-click, or the `open <id>` link above the graph, opens its entry. The refresh recolors the graph in place, keeping the zoom, the pan and the lit path.
  - **Validations**: every validation folded, pending and failed first; unfolded, its file in full (where, how, expected, evidence).
  - **Decisions**: every decision folded, open and proposed first; unfolded, its file in full (question, decision, why, options with pros and cons, where it was born, who confirms it).
  - **Features**: the roadmap's milestones and features; a feature unfolds into its tasks with their commits, its criteria with their checks, and its review findings with what was done about each.
  - **Pending**: every action waiting on someone else, folded, open ones first; unfolded, its refs, closing date and link.
  - **Journal**: every note, newest first.
  - **Docs**: the task's Markdown files (every `.md` outside `repos/`), listed by folder beside the one open, rendered with its tables, code and Mermaid diagrams in the page's light or dark theme. The ids the task defines link to their tab; a link to another of its `.md` files opens it here, a web link opens a new browser tab, any other link is plain text. Raw HTML in a file shows as text. The refresh fetches and redraws the open file only when it changed on disk, keeping the scroll.

  An id inside a tab links to the entry that defines it, unfolded and scrolled into view (`&focus=<id>`).

The page refetches what it shows (all tasks, or the open task) every 30 s, or when the button in the header is clicked; its ring fills until the next refresh. A failed fetch keeps the last data on screen and shows the error. On a task page the refresh keeps the tab, the scroll and every entry the user unfolded.

## Routes

| Route | Gives |
|---|---|
| `/` | the page |
| `/static/<file>` | a file under `static/` |
| `/api/tasks` | `{home, generated, tasks: [row]}`: per task its repo, id, path, title, `/task` step (status.py's `{step, reason, blockers, your_turn}`), the row's `reason` (`{text, hover, failed}`: the summary, the text for the hover, and whether failures replaced it), failure and warning counts, items by status, features done, open and proposed decisions, open pending items, last activity (newest file time, `repos/` excluded), last journal note and the open requirements with what each misses; a legacy task (`diario.yaml` or `decisoes/`, no `decisions/`) gives only `repo`, `id`, `path`, `legacy: true` |
| `/api/tasks/<repo>/<id>` | one task whole, for its page: `{row, status, graph, docs, next, checks, readme, decisions, validations, features, pending, journal}`, where `next` is each blocker of the step as an action `[{verb, id, short, name, state, waiting}]` (`short` the roadmap id of a feature; empty when the task is done), `checks` status.py's failures and warnings grouped by kind `[{severity, kind, title, fix, ids, messages}]` (failures first), `status` is status.py's `collect()`, `graph` its links as `{nodes: [{id, kind, status, label}], edges: [{source, target}]}`, `docs` its Markdown files as `[{path, title, mtime}]` (every `.md` outside `repos/`, README and brief first), `readme` the README front matter (title, link, repos), decisions and validations their files, and each feature its `feature.yaml` with its `review.yaml` (or `null`); 404 for an unknown, legacy or broken task |
| `/api/tasks/<repo>/<id>/docs/<path>` | one Markdown file the task lists, as `text/markdown` without its YAML front matter; 404 for any path not in `docs` |

Any other path is 404; any method but GET is 405.

## Layout

```text
dashboard.py    CLI and HTTP routes only
home.py         where the home is; which folders are tasks, which are legacy
state.py        one row per task: status.py's collect() plus progress counts, last activity and last note;
                one failing task never hiding the others; task_detail(): one task whole
summary.py      the step's blockers grouped into the row's short reason; failures replace it
detail.py       one task folder as plain data: decisions, validations, features with their reviews, pending, journal
graph.py        one task's links as nodes and edges: items, requirements, decisions, features, validations
docs.py         one task's Markdown files: the list, and the text of a listed one
static/         the page: index.html, style.css, js/ (main, api, refresh, format, scripts, views/tasks, views/filter,
                views/task and its tabs under views/task/)
tests/          pytest; test.cmd holds the command the pre-commit hook runs
```

## Tests

```sh
cd tools/task-dashboard && uv run --no-project --with pytest --with pyyaml python -m pytest -q -p no:cacheprovider tests
```
