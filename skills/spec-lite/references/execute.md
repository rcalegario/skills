# Execute and validate

Goal: every task committed, every check `pass`, and `finish <feature>` exiting 0.

## Each task, in `blocked_by` order

`status` names the next task. For it:

1. `set <feature> T<n> doing`.
2. Build it test-first: load `tdd` for the task's ACs when the project has tests. The test asserts what the AC states.
3. Run the tests for the files you touched, plus typecheck/lint when the project has them. Green before moving on; a red test is fixed in the code.
4. `set <feature> T<n> done`.
5. Commit: stage the changed files by name, plus `tasks.yaml` when the repo tracks `.specs/`, and commit with the message from `commit-msg <feature> T<n>` (add the session's attribution lines).

If a task turns out bigger than planned, or needs a decision the spec did not settle, stop and ask: split the task in `tasks.yaml` (then `check`), or update the spec with the user.

## Validate, after the last task

1. **Suite.** Run the `test` command from `tasks.yaml` once. Every `test` check whose test passed: `set <feature> AC<n> pass`. A failure is fixed (its own commit), and the suite runs again.
2. **Review (large features).** Load `code-review` with the fixed point `base` from `tasks.yaml` and the feature's `spec.md` as the spec. Fix what it finds that matters (each fix its own commit), and tell the user what you chose to leave.
3. **Manual checks.** Present the `manual` checks as a numbered checklist with their steps, and wait. Mark each one with `set <feature> AC<n> pass|fail` as the user reports. A `fail` is fixed and checked again.
4. **Finish.** `finish <feature>`: it refuses while any task is open or any check is not `pass`. Commit the final `ROADMAP.yaml`/`tasks.yaml` state when the repo tracks `.specs/`.

Report in a few lines: the ACs proved by tests, the ones the user confirmed, anything left for later. Then `status` shows the next feature.
