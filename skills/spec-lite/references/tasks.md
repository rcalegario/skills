# Tasks

Goal: a `tasks.yaml` the user approves, where every AC is covered by a task and proved by a check.

`approve <feature> spec` wrote the skeleton: one task covering every AC, and one check per AC. Fill it in:

```yaml
feature: m1.f2.export-csv
test: npm test                     # the command that runs the whole suite
tasks:
  - id: T1
    title: Download the filtered list as CSV
    covers: [AC1, AC3]
    blocked_by: []
    commit: "feat(export): let users download the filtered list as CSV"
    status: todo
  - id: T2
    title: Tell users when there is nothing to export
    covers: [AC2]
    blocked_by: [T1]
    commit: "feat(export): tell users when there is nothing to export"
    status: todo
checks:
  - ac: AC1
    test: "src/export.test.ts > downloads only the filtered rows"
    status: pending
  - ac: AC2
    manual: "Clear the filters until the list is empty, click Export, read the message"
    status: pending
```

## Tasks

- **Tracer bullets.** Each task is a thin vertical slice through every layer it needs (data, logic, UI, test) that works and can be shown on its own. Slice by behaviour, never by layer.
- A refactor that makes the next task easy comes first, as its own task.
- **Riskiest first.** Among tasks that can start, lead with the one you are least sure works: a library or service the project never used, a data shape other tasks build on, a performance doubt, the part the user hesitated on. When the doubt is too big for a task, add a spike task before it (`prototype` skill) so the plan changes before the rest is built.
- `blocked_by` lists only the tasks that truly gate this one.
- Medium: 1-5 tasks. More than ~8 means the feature is too big: split it into two features, or escalate to `tlc-spec-driven`.
- **`commit`** is the final message, written now so the user approves it with the task. Match the repo: run `git log -n 10 --oneline` and copy its prefix style and language. The subject says why the change matters, not which files it touches.
- `test` is the suite command, read from the repo (`package.json`, `Makefile`, `pyproject.toml`, CI config).

## Checks

Each AC gets a check that proves it:

- **`test`**: names the automated test that fails when the AC is false (`file > test name`). Use it whenever the project has tests and the AC is reachable from them.
- **`manual`**: the steps the user follows to see the outcome. Use it for what tests cannot reach: look and feel, a real browser, a file opening in another app.

A project with no test setup gets all-manual checks; say so when presenting.

## Present and stop

Run `check <feature>` until it passes. Present the tasks as a numbered list (title, blocked by, commit message), with one line on why the first task leads, and the checks (AC → test or manual). Ask whether the granularity and the messages are right.

On the user's approval: `approve <feature> tasks`. Then go to [execute.md](execute.md).
