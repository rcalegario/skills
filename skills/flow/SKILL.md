---
name: flow
description: Lean feature workflow. Plan an optional roadmap, size the work, write spec.md (for people) and feature.yaml (criteria, tasks, checks), get the approval, build task by task with one commit each, prove every criterion and close with a two-axis review. Invoked with /flow (or /flow roadmap).
disable-model-invocation: true
---

# Flow

```
ROADMAP (optional) ──► SIZE ──► SPEC ──► approval ──► BUILD (per task: test → code → verify → commit → verifying) ──► CLOSE (suite → checks → review → finish)
```

`<skill-dir>` is the folder holding this file. Run the script as `python <skill-dir>/scripts/flow.py <command> <feature>` from the project root (`python3` or `py -3` where `python` is missing). When the specs live outside the repo (a task folder from another skill), add `--specs <dir>`: `.specs/` paths in this file then mean that folder, and `--root` stays the git repo whose commits the script records. It needs PyYAML; without it, perform the same checks by reading the file.

Every status change, the roadmap approval and the feature skeleton go through the script; content (criteria, tasks, checks) you edit by hand, then run `check`. A non-zero exit means stop and fix what it prints.

| When | Command |
|---|---|
| A feature is chosen | `new <feature> --title T --size S\|M\|L [--roadmap F1.1]` (a `/task` story adds `--repo`, `--decisions`, `--validations`) |
| The user approved the roadmap | `roadmap --approve` |
| After any hand edit | `check <feature>` |
| The user approved (M: spec and tasks; L: each in its turn) | `approve <feature> spec`, then for L `approve <feature> tasks` |
| Starting a task | `set <feature> T<n> doing` |
| The task's commit is made | `set <feature> T<n> verifying` (records `HEAD`, refused when its subject is not the task's `commit`; `--commit <sha>` on resume or for an earlier commit) |
| A criterion's checks ran | `set <feature> AC<n> pass\|fail`: a task turns `done` when every check of the criteria it covers passes, and goes back to `verifying` when one fails |
| A review finding | `finding <feature> --text T --source S [--severity --confidence --file --line --hunk --fix]`: appended to `review.yaml` as the next `R-n`, with no outcome yet. Add `--action fix --task T<n>` or `--action wontfix --reason R` when the outcome is already known. `S` is `spec-review`, `standards-review`, `correctness-review`, `tests-review`, `security-review`, `pr-comment` (add `--comment-id N`, the GitHub comment id) or `user` |
| The outcome of a finding | `finding <feature> R-n --action fix --task T<n>` or `--action wontfix --reason R` (replaces an earlier outcome) |
| A clean review, after the review ran | `finding <feature> --none --axes spec,standards` (`findings: []`; M and L need both axes) |
| The feature's PR is open | `pr <feature> --url U` |
| Every task committed (`verifying` or `done`) | `review <feature>` |
| Every check `pass` and every finding in `review.yaml` has an outcome | `finish <feature>` |
| Resuming, or "where are we" | `roadmap`, `status <feature>` |

`approve` and `roadmap --approve` record the user's approval: run them only in the turn the user gives it.

Every stop that waits for the user's yes uses the skeleton and the type named at that stop, from `<skill-dir>/reference/approvals.md`.

## Project rules come first

Before sizing, read the project's root `CLAUDE.md` / `AGENTS.md` and the ones in each area the work touches. They own everything project-specific: how to run tests, commit conventions, feature naming, runtime constraints, licensing. Where they disagree with this skill, they win.

Facts are looked up in the code and docs, never asked. Decisions that belong to the user are asked, never assumed.

## ROADMAP (when asked, or when no roadmap exists and the work spans several features)

1. Check the project has a `CLAUDE.md` or `AGENTS.md` stating its commands, folder structure, code style and boundaries (always / ask first / never). When it lacks one, offer to write it with `/init`. These hold for every feature, so specs never repeat them.
2. When the project docs name their own roadmap, work in that file under the project's rules and skip the roadmap script. Otherwise the roadmap is `.specs/roadmap.yaml`.
3. Read the project's docs and code. Ask the user's decisions in rounds (**question** format): the goal, who it serves, constraints, what stays out. Milestones first, features second.
4. Draft **milestones** as outcomes (what becomes true) and, inside each, **features** as tracer bullets: thin vertical slices, each demoable on its own and sized to fit M or L. Give each feature its `blocked_by` (feature or milestone ids).
5. Run `flow.py roadmap` until it exits 0. Present the roadmap in the **plan** format, and stop.
6. After the user approves, run `flow.py roadmap --approve`.

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

A roadmap feature's status is the `status` of the `feature.yaml` whose `roadmap:` names it (`planned` while none does); a milestone is `planned` (all its features planned), `done` (all done) or `building`. The script writes both into `roadmap.yaml` after every command that changes a feature, so never edit those `status` lines: they are overwritten. `flow.py roadmap` shows progress per milestone and the features ready to start. Each roadmap feature has at most one `feature.yaml`.

Any change to the roadmap (a split at SIZE, a feature added or dropped) is proposed to the user (**plan** format) and written only after they approve.

## Size

| Size | Shape | Files | Grill | Approvals | Close |
|---|---|---|---|---|---|
| **S** | ≤3 files, one sentence | none: a 1–3 step plan in chat (**plan** format) | never | one "yes" in chat | affected tests green, commit |
| **M** | clear feature, ≤8 tasks | `spec.md` + `feature.yaml` | offer once | one (spec and tasks together) | suite, checks, review |
| **L** | several components or an architectural decision | `spec.md` + `feature.yaml`, `design.md` when a choice needs explaining | by default | two (spec, then tasks) | suite, checks, review |

An S plan that grows past 3 steps becomes M.

**One feature, one small PR.** A feature is delivered by one PR, and it stays within the size the project recommends (its `CONTRIBUTING.md`; without one, the limit in the `task` skill's `fallback/contributing.md`). When the diff would pass it, split the feature at SIZE, or stack PRs. This skill does not repeat the number: read it from that source.

**Escalate** when any of these shows up, at sizing or once the task list is drafted:

- more than 8 tasks;
- many decisions still open after the first round of questions;
- a new domain, with no similar code in the repo to follow;
- auth, payments, money, concurrency, or migrating real data;
- other people depend on the result, or a screen must match a given design pixel for pixel;
- criteria only a human can prove in a real environment (UAT).

Say which signal fired, then suggest, in this order: (1) **split** into features that fit M or L, proposing the cut (and the matching roadmap change, when there is a roadmap); (2) when splitting does not remove the risk, move to the official [tlc-spec-driven](https://github.com/tech-leads-club/agent-skills/tree/main/packages/skills-catalog/skills/%28development%29/tlc-spec-driven). The user decides (**question** format, one option per path). A chosen split changes the roadmap, which then gets its own **plan** stop.

## SPEC (M and L)

1. Read the relevant code and docs. With a roadmap, start from a feature `flow.py roadmap` lists as ready, or the one the user names. Check the project's docs for the feature naming rule; default to `<roadmap id>-<slug>` (`F1.1-csv-export`), or a short kebab-case slug without a roadmap.
2. List the **assumptions** you are making, each with where it came from, in the **Assumptions** list of the first question round.

3. Ask the user's decisions in one round (L: in rounds, each round asking every question whose prerequisites are settled), in the **question** format.
   Turn vague words into concrete ones ("fast" → "under 1 s for 1,000 rows"). Write each answer into its file in the turn it arrives: a criterion, an `Out of scope` line, or a `Notes` entry.
4. Run `flow.py new <feature> ...`: it creates `.specs/features/<feature>/` with `spec.md` (from `<skill-dir>/templates/spec.md`) and a draft `feature.yaml` (schema below) that you then fill: each empty list carries a commented example of one item with every required field. `spec.md` is the prose for people; everything the script checks lives in `feature.yaml`. Each fact lives in one of them, never both.
5. Write the criteria (below). Re-read the request sentence by sentence: each sentence lands on a criterion, an `Out of scope` line, or a question.
6. Write the tasks and checks (below). For L, only after the spec is approved.
7. **Grill by size.** M: when the draft passes `check`, offer once: "Want me to grill this spec first?" and run the `grilling` skill on a yes. L: run `grilling` before presenting. Bound it to this feature's behaviour and scope; the architecture is `design.md`'s job.
8. Run `flow.py check <feature>` until it exits 0. Present it in the **plan** format: the criteria, and (M, or L at its second stop) the tasks and the checks. Stop.

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
- A criterion that exists to save time (a skip, a cache, a check before the work) names the measurement showing the step it saves costs more than its check. Without one, a spike task measures it first (see **Riskiest first**), or the criterion is dropped.

### Tasks

- **Tracer bullets.** Each task is a thin vertical slice through every layer it needs (data, logic, UI, test) that works on its own. Slice by behaviour, never by layer.
- A refactor that makes the next task easy comes first, as its own task.
- **Riskiest first.** Among tasks that can start, lead with the one you are least sure works: a library or service the project never used, a data shape other tasks build on, a performance doubt, the part the user hesitated on. When the doubt is too big for a task, add a spike task before it (`prototype` skill) so the plan changes before the rest is built.
- `blocked_by` lists only the tasks that truly gate this one.
- **`commit`** is the final message, written now so the user approves it with the task. Match the repo: run `git log -n 10 --oneline` and copy its prefix style and language. The subject says why the change matters, not which files it touches.
- `repo` (optional) is the path of the repo this task commits to, when it is not `--root` (a task that edits another repo, such as a docs repo). `set ... verifying` and `check` look for its commit there.
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
    status: todo               # todo | doing | verifying | done  (changed by `set`; `verifying` adds `sha:`, the task's commit;
                               # `done` comes only from the checks of its criteria passing)
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

pr: https://github.com/acme/app/pull/42   # written by `pr`, once the PR is open
```

### review.yaml

The review lives beside `feature.yaml`, in `review.yaml`, filled at CLOSE and written only by `flow.py finding`, which creates the file, stamps it and numbers each finding:

```yaml
base: abc1234                  # the feature's base, stamped when the file is created
head: def5678                  # HEAD when the file is created
created: 2026-11-12
axes: [spec, standards]        # only on a clean review: the axes that ran (`finding --none --axes`)
findings:                      # [] for a clean review (`finding --none --axes spec,standards`)
  - id: R-1                    # assigned by the script
    text: "AC2 test does not cover a quote inside a value"
    source: spec-review        # spec-review | standards-review | correctness-review | tests-review | security-review | pr-comment | user
    severity: should-fix       # optional: blocker | should-fix | nit
    confidence: high           # optional: high | medium | low
    file: "src/export.test.ts" # optional, the file at HEAD ("-" when nothing points at a line)
    line: 41                   # optional
    hunk: "expect(csv).toContain(',')"   # optional, the quoted code or spec line
    fix: "Add a value with a quote"      # optional, one sentence
    action: fix                # absent until decided: fix | wontfix
    task: T3                   # fix → the task that fixes it
  - id: R-2
    text: "Rename writer module"
    source: pr-comment
    comment_id: 2201           # pr-comment → the GitHub comment id; one finding per comment
    action: wontfix
    reason: "Matches the existing naming."
```

A feature closed before `review.yaml` keeps its `review:` block in `feature.yaml`: `check`, `status` and `finish` still read it and warn that it is legacy; `finding` refuses such a feature until the block moves into `review.yaml`, and `check` fails when both exist.

`spec.md` holds the rest: Problem, Assumptions, Out of scope and Notes (decisions taken along the way; for M, the design in a few lines). `check` refuses an approved M or L feature whose `spec.md` is missing or still has a `TODO`.

For L, `design.md` sits next to them only when a choice needs explaining (a new module, a data model, a library, a flow across components): the components touched, the data shape, the chosen option and the one you rejected with why. Ask the user only about choices that change what they will see or maintain.

`spec.md` and `design.md` are for the user to read: where a shape, a flow or a change is the point, show it with the visuals in `<skill-dir>/reference/visuals.md` (call tree, file tree, `diff`, Mermaid) instead of describing it.

## BUILD

Run `flow.py status <feature>` and take a task from the **frontier** (no commit yet, every blocker `verifying` or `done`). For each task:

1. `set <feature> T<n> doing`.
2. Write the test from the criteria the task covers (use the `tdd` skill where a clear seam exists).
3. Write the minimum code that makes it pass, touching only what the task needs.
4. Run the task's `verify` command, plus typecheck/lint when the project has them, until it is green.
5. Commit the task's code and tests only, with the task's `commit` message, staging files by name.
6. `set <feature> T<n> verifying`. It records `HEAD`, prints the next frontier, and refuses while code changes are uncommitted (with `--specs` inside the repo, only in the folder that holds them). The task is `done` only when the checks of its criteria pass (CLOSE, or earlier for checks you can run now).

**Tests hold the line.** Each test asserts the outcome its criterion names, never the code's internals, and would fail under a plausible wrong implementation. When a test seems wrong, ask the user before changing it; a red test is fixed in the code, with assertions kept as strict as the criterion.

**Scope.** An idea that is not in a task's criteria goes to `deferred`; a bug outside the task is reported to the user. When a task turns out bigger than planned, or needs a decision the spec did not settle, stop and ask: split the task (then `check`), or update the spec with the user. A decision the user makes mid-build is written into its file in the turn it arrives.

**Authority.** Approval covers local work and local commits. Push, deploy, and any remote or destructive action need their own explicit go-ahead (**outbound** format).

## CLOSE

S: run the affected tests, commit, done.

M and L:

1. `review <feature>` (it refuses while a task is open). Run the `test` suite once. A failure is fixed in its own commit, and the suite runs again.
2. Every `test` check whose test passed: `set <feature> AC<n> pass`.
3. Review the diff since `base` (fetch first), along two separate axes:
   - **Spec**: criteria missing or partial, behaviour nobody asked for, criteria that look implemented but wrong. The spec is `spec.md` plus `feature.yaml`.
   - **Standards**: breaches of the project's documented standards (its `CLAUDE.md` / `AGENTS.md` files and coding-standards docs).

   Invoke the `code-review` skill with `base`, the paths to `spec.md` and `feature.yaml`, and `--feature <feature> --root <root> --specs <specs>` (the same values as your `flow.py` calls) when it is available: it records every finding in `review.yaml` itself, or a clean review. Otherwise dispatch two sub-agents in parallel, one per axis, each given the diff command and its sources, each reporting in under 400 words with a quote or `file:line` per finding, and record each finding yourself with `flow.py finding <feature> --text T --source S ...` (its severity, file, line, hunk and fix when the review gave them), or `finding <feature> --none --axes spec,standards` when both axes ran and are clean. Never record a clean review for an axis that did not run.
4. Comments left on the PR are findings too: read them (`gh api repos/<owner>/<repo>/pulls/<n>/comments`, and `issues/<n>/comments` for general ones), and record each with `--source pr-comment --comment-id <id>`. Then give each finding its outcome with `finding <feature> R-n --action fix --task T<n>` or `--action wontfix --reason R`: a `fix` adds a task first (same BUILD loop); a `wontfix` carries a `reason` the user agreed to (**question** format). One round: after the fixes, run the suite again, and there is no second review.
5. **Manual checks.** Present the `manual` checks in the **checklist** format, and wait. Record each one with `set <feature> AC<n> pass|fail` as the user reports. A `fail` is fixed (a task, same loop) and checked again.
6. `finish <feature>`: it refuses while a task is not `done`, a check is not `pass`, `review.yaml` is missing, or a finding has no outcome.

Done when: `finish` exits 0. Report in a few lines: the criteria proved by tests, the ones the user confirmed, anything deferred. A lesson that will matter in later features is proposed to the user as a line in the right `CLAUDE.md` / `AGENTS.md`.

## Resume

Run `flow.py roadmap` when there is a roadmap, then `flow.py status <feature>`, and read the feature's `spec.md` and `feature.yaml`. When the file disagrees with `git log` (a task commit exists but the task has no `sha`), git wins: run `flow.py set <feature> <task> verifying --commit <sha>` for that task, then continue from the frontier.

## Companion skills

Load each when its step says so: `grilling` (stress-test a spec), `tdd` (each task, when the project has tests), `prototype` (a spike task), `code-review` (CLOSE). Without one, do the step inline: grill as numbered questions with your recommended answer; write the test before the code; review the diff against the spec yourself.

Generated documents: headings in English, prose in the project's language, identifiers never translated.
