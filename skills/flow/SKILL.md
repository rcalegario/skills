---
name: flow
description: Lean feature workflow. Plan an optional roadmap, size the work, write spec.md (for people) and feature.yaml (criteria, tasks, checks), get the approval, build task by task with one commit each, prove every criterion and close with a two-axis review. Invoked with /flow (or /flow roadmap).
disable-model-invocation: true
---

# Flow

```
ROADMAP (optional) ──► SIZE ──► SPEC ──► approval ──► BUILD (per task: test → code → verify → commit → done) ──► CLOSE (suite → checks → review → finish)
```

`<skill-dir>` is the folder holding this file. Run the script as `python <skill-dir>/scripts/flow.py <command> <feature>` from the project root (`python3` or `py -3` where `python` is missing). When the specs live outside the repo (a task folder from another skill), add `--specs <dir>`: `.specs/` paths in this file then mean that folder, and `--root` stays the git repo whose commits the script records. It needs PyYAML; without it, perform the same checks by reading the file.

Every status change goes through the script; content (texts, tasks, checks, findings) you edit by hand, then run `check`. A non-zero exit means stop and fix what it prints.

| When | Command |
|---|---|
| After any hand edit | `check <feature>` |
| The user approved (M: spec and tasks; L: each in its turn) | `approve <feature> spec`, then for L `approve <feature> tasks` |
| Starting a task | `set <feature> T<n> doing` |
| The task's commit is made | `set <feature> T<n> done` (records `HEAD`; `--commit <sha>` on resume) |
| A criterion's checks ran | `set <feature> AC<n> pass\|fail` |
| Every task done | `review <feature>` |
| Every check `pass` and the review recorded | `finish <feature>` |
| Resuming, or "where are we" | `roadmap`, `status <feature>` |

`approve` records the user's approval: run it only in the turn the user gives it.

## Project rules come first

Before sizing, read the project's root `CLAUDE.md` / `AGENTS.md` and the ones in each area the work touches. They own everything project-specific: how to run tests, commit conventions, feature naming, runtime constraints, licensing. Where they disagree with this skill, they win.

Facts are looked up in the code and docs, never asked. Decisions that belong to the user are asked, never assumed.

## ROADMAP (when asked, or when no roadmap exists and the work spans several features)

1. Check the project has a `CLAUDE.md` or `AGENTS.md` stating its commands, folder structure, code style and boundaries (always / ask first / never). When it lacks one, offer to write it with `/init`. These hold for every feature, so specs never repeat them.
2. When the project docs name their own roadmap, work in that file under the project's rules and skip the roadmap script. Otherwise the roadmap is `.specs/roadmap.yaml`.
3. Read the project's docs and code. Ask the user's decisions in rounds (same question format as SPEC): the goal, who it serves, constraints, what stays out. Milestones first, features second.
4. Draft **milestones** as outcomes (what becomes true) and, inside each, **features** as tracer bullets: thin vertical slices, each demoable on its own and sized to fit M or L. Give each feature its `blocked_by` (feature or milestone ids).
5. Run `flow.py roadmap` until it exits 0. Present the milestones and features with their blockers, and stop.
6. After the user approves, write `approved` with today's date.

```yaml
vision: |
  Make reports portable.
approved: 2026-11-10
milestones:
  - id: M1
    title: Export
    outcome: Users get reports out of the app.
    features:
      - id: F1.1
        title: CSV export
        goal: Export the report as CSV.
        done_when: The report downloads as CSV.
        blocked_by: []                 # feature ids, or a milestone id for all of it
```

The roadmap holds no status. A roadmap feature's status is the `status` of the `feature.yaml` whose `roadmap:` names it (`planned` while none does), so `flow.py roadmap` shows progress per milestone and the features ready to start. Each roadmap feature has at most one `feature.yaml`.

Any change to the roadmap (a split at SIZE, a feature added or dropped) is proposed to the user and written only after they approve.

## Size

| Size | Shape | Files | Grill | Approvals | Close |
|---|---|---|---|---|---|
| **S** | ≤3 files, one sentence | none: a 1–3 step plan in chat | never | one "ok" in chat | affected tests green, commit |
| **M** | clear feature, ≤8 tasks | `spec.md` + `feature.yaml` | offer once | one (spec and tasks together) | suite, checks, review |
| **L** | several components or an architectural decision | `spec.md` + `feature.yaml`, `design.md` when a choice needs explaining | by default | two (spec, then tasks) | suite, checks, review |

An S plan that grows past 3 steps becomes M.

**Escalate** when any of these shows up, at sizing or once the task list is drafted:

- more than 8 tasks;
- many decisions still open after the first round of questions;
- a new domain, with no similar code in the repo to follow;
- auth, payments, money, concurrency, or migrating real data;
- other people depend on the result, or a screen must match a given design pixel for pixel;
- criteria only a human can prove in a real environment (UAT).

Say which signal fired, then suggest, in this order: (1) **split** into features that fit M or L, proposing the cut (and the matching roadmap change, when there is a roadmap); (2) when splitting does not remove the risk, move to `/tlc-spec-driven`. The user decides.

## SPEC (M and L)

1. Read the relevant code and docs. With a roadmap, start from a feature `flow.py roadmap` lists as ready, or the one the user names. Check the project's docs for the feature naming rule; default to `<roadmap id>-<slug>` (`F1.1-csv-export`), or a short kebab-case slug without a roadmap.
2. Open with the **assumptions** you are making, each with where it came from, so the user corrects them at a glance:

   ```
   Assumptions (correct me now, or I go with these):
   1. Export uses the current screen's filters - the list filters client-side
   2. Comma separator, UTF-8 with BOM, so Excel opens it right
   ```

3. Ask the user's decisions in one round (L: in rounds, each round asking every question whose prerequisites are settled). Number each question and lead with your recommendation, so "yes" accepts it:

   ```
   **Q1 - <title>**: <question, with its options>
   ➡️ <recommended answer>
   ```

   Turn vague words into concrete ones ("fast" → "under 1 s for 1,000 rows"). Write each answer into its file in the turn it arrives: a criterion, an `Out of scope` line, or a `Notes` entry.
4. Create `.specs/features/<feature>/` with `spec.md` from `<skill-dir>/templates/spec.md` and `feature.yaml` (schema below). `spec.md` is the prose for people; everything the script checks lives in `feature.yaml`. Each fact lives in one of them, never both.
5. Write the criteria (below). Re-read the request sentence by sentence: each sentence lands on a criterion, an `Out of scope` line, or a question.
6. Write the tasks and checks (below). For L, only after the spec is approved.
7. **Grill by size.** M: when the draft passes `check`, offer once: "Want me to grill this spec first?" and run the `grilling` skill on a yes. L: run `grilling` before presenting. Bound it to this feature's behaviour and scope; the architecture is `design.md`'s job.
8. Run `flow.py check <feature>` until it exits 0. Present: the problem in a line, the criteria, out of scope, the assumptions you kept, and (M, or L at its second stop) the tasks as a numbered list (title, blocked by, commit message) with one line on why the first task leads, and the checks (criterion → test or manual). Blocking questions go first. Stop.

Done when: `check` exits 0, the summary is in chat, and the turn ended waiting for the user. On the approval: `approve <feature> spec` (M approves both; L then writes the tasks and stops again for `approve <feature> tasks`).

`.specs/` is working state. Keep it out of task commits; when the project git-ignores it, content search skips it, so read the file by its explicit path.

### Criteria

Each criterion is one line with one observable outcome, in one of four shapes:

| Shape | Use for | Example |
|---|---|---|
| `WHEN <trigger> THEN <result>` | a response to an action or event | WHEN the user clicks "Export" THEN a CSV of the filtered rows downloads |
| `IF <error> THEN <result>` | failures, invalid input, empty states | IF the list is empty THEN the page shows "Nothing to export" |
| `WHILE <state>, WHEN <trigger> THEN <result>` | behaviour that holds only in a state | WHILE an import runs, WHEN the user opens Export THEN the button is disabled |
| `ALWAYS <invariant>` | a rule that always holds | ALWAYS amounts are stored in cents |

- One outcome per criterion; two behaviours are two criteria.
- Concrete values: the exact message, the status code, the limit.
- For each WHEN, ask what the IF is: the error, the empty case, the duplicate. That is the criterion most often missing.

### Tasks

- **Tracer bullets.** Each task is a thin vertical slice through every layer it needs (data, logic, UI, test) that works on its own. Slice by behaviour, never by layer.
- A refactor that makes the next task easy comes first, as its own task.
- **Riskiest first.** Among tasks that can start, lead with the one you are least sure works: a library or service the project never used, a data shape other tasks build on, a performance doubt, the part the user hesitated on. When the doubt is too big for a task, add a spike task before it (`prototype` skill) so the plan changes before the rest is built.
- `blocked_by` lists only the tasks that truly gate this one.
- **`commit`** is the final message, written now so the user approves it with the task. Match the repo: run `git log -n 10 --oneline` and copy its prefix style and language. The subject says why the change matters, not which files it touches.
- `verify` runs this task's tests; `test` (top level) runs the whole suite, read from the repo (`package.json`, `Makefile`, `pyproject.toml`, CI config).

### Checks

Every criterion gets a check that proves it:

- **`test`**: names the automated test that fails when the criterion is false (`file > test name`). Use it whenever the project has tests and the criterion is reachable from them.
- **`manual`**: the steps the user follows to see the outcome. Use it for what tests cannot reach: look and feel, a real browser, a file opening in another app.

A project with no test setup gets all-manual checks (and needs no `test` command); say so when presenting.

### feature.yaml

```yaml
id: F1.1-csv-export
title: Export the report as CSV
roadmap: F1.1                  # optional: the roadmap feature this delivers
size: M                        # S | M | L
status: draft                  # draft | approved | building | review | done  (changed by the script)
approved:                      # written by `approve`
  spec: null
  tasks: null
base: null                     # HEAD when the tasks were approved, written by `approve`; the review diffs from it
test: npm test                 # the whole suite; needed when a check names a test

acceptance:
  - id: AC1
    text: WHEN the user clicks "Export" THEN a CSV with one row per report line and the screen's header downloads
  - id: AC2
    text: IF a value contains a comma THEN it is quoted

tasks:
  - id: T1
    title: CSV writer with header and rows
    covers: [AC1]
    blocked_by: []
    verify: npm test -- export
    commit: "feat(export): let users download the report as CSV"
    status: todo               # todo | doing | done  (changed by `set`; `done` adds `sha:`, the task's commit)
  - id: T2
    title: Quote values with commas
    covers: [AC2]
    blocked_by: [T1]
    verify: npm test -- export
    commit: "fix(export): keep values with commas in one column"
    status: todo

checks:
  - ac: AC1
    test: "src/export.test.ts > downloads one row per line"
    status: pending            # pending | pass | fail  (changed by `set`)
  - ac: AC2
    manual: "Export a report with a comma in a name, open it in a spreadsheet, see one column"
    status: pending

deferred:                      # ideas that came up and are out of this feature
  - Choose the delimiter.

review:                        # filled at CLOSE
  findings:
    - text: AC2 test does not cover a quote inside a value
      action: fix              # fix | wontfix
      task: T3                 # fix → the task that fixes it
    - text: Rename writer module
      action: wontfix
      reason: Matches the existing naming.
```

`spec.md` holds the rest: Problem, Assumptions, Out of scope and Notes (decisions taken along the way; for M, the design in a few lines). `check` refuses an approved M or L feature whose `spec.md` is missing or still has a `TODO`.

For L, `design.md` sits next to them only when a choice needs explaining (a new module, a data model, a library, a flow across components): the components touched, the data shape, the chosen option and the one you rejected with why. A small diagram (file tree, call flow, Mermaid) beats a paragraph when the flow is not obvious. Ask the user only about choices that change what they will see or maintain.

## BUILD

Run `flow.py status <feature>` and take a task from the **frontier** (not done, every blocker done). For each task:

1. `set <feature> T<n> doing`.
2. Write the test from the criteria the task covers (use the `tdd` skill where a clear seam exists).
3. Write the minimum code that makes it pass, touching only what the task needs.
4. Run the task's `verify` command, plus typecheck/lint when the project has them, until it is green.
5. Commit the task's code and tests only, with the task's `commit` message, staging files by name.
6. `set <feature> T<n> done`. It records `HEAD`, prints the next frontier, and refuses while code changes are uncommitted.

**Tests hold the line.** Each test asserts the outcome its criterion names, never the code's internals, and would fail under a plausible wrong implementation. When a test seems wrong, ask the user before changing it; a red test is fixed in the code, with assertions kept as strict as the criterion.

**Scope.** An idea that is not in a task's criteria goes to `deferred`; a bug outside the task is reported to the user. When a task turns out bigger than planned, or needs a decision the spec did not settle, stop and ask: split the task (then `check`), or update the spec with the user. A decision the user makes mid-build is written into its file in the turn it arrives.

**Authority.** Approval covers local work and local commits. Push, deploy, and any remote or destructive action need their own explicit go-ahead.

## CLOSE

S: run the affected tests, commit, done.

M and L:

1. `review <feature>` (it refuses while a task is open). Run the `test` suite once. A failure is fixed in its own commit, and the suite runs again.
2. Every `test` check whose test passed: `set <feature> AC<n> pass`.
3. Review the diff since `base` (fetch first), along two separate axes:
   - **Spec**: criteria missing or partial, behaviour nobody asked for, criteria that look implemented but wrong. The spec is `spec.md` plus `feature.yaml`.
   - **Standards**: breaches of the project's documented standards (its `CLAUDE.md` / `AGENTS.md` files and coding-standards docs).

   Invoke the `code-review` skill with `base` and the paths to `spec.md` and `feature.yaml` when it is available; otherwise dispatch two sub-agents in parallel, one per axis, each given the diff command and its sources, each reporting in under 400 words with a quote or `file:line` per finding.
4. Record every finding under `review.findings` (`findings: []` when clean). A `fix` adds a task (same BUILD loop); a `wontfix` carries a `reason` the user agreed to. One round: after the fixes, run the suite again, and there is no second review.
5. **Manual checks.** Present the `manual` checks as a numbered checklist with their steps, and wait. Record each one with `set <feature> AC<n> pass|fail` as the user reports. A `fail` is fixed (a task, same loop) and checked again.
6. `finish <feature>`: it refuses while a task is open, a check is not `pass`, or the review is missing.

Done when: `finish` exits 0. Report in a few lines: the criteria proved by tests, the ones the user confirmed, anything deferred. A lesson that will matter in later features is proposed to the user as a line in the right `CLAUDE.md` / `AGENTS.md`.

## Resume

Run `flow.py roadmap` when there is a roadmap, then `flow.py status <feature>`, and read the feature's `spec.md` and `feature.yaml`. When the file disagrees with `git log` (a task commit exists but the task is not done), git wins: run `flow.py set <feature> <task> done --commit <sha>` for that task, then continue from the frontier.

## Companion skills

Load each when its step says so: `grilling` (stress-test a spec), `tdd` (each task, when the project has tests), `prototype` (a spike task), `code-review` (CLOSE). Without one, do the step inline: grill as numbered questions with your recommended answer; write the test before the code; review the diff against the spec yourself.

Generated documents: headings in English, prose in the project's language, identifiers never translated.
