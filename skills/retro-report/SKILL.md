---
name: retro-report
description: Retro over one Claude Code session, the current one by default, written as a tracked report whose fixes become a /flow roadmap. /retro-report [<retro-folder> | <session id>]
disable-model-invocation: true
---

# retro-report

You are improving the coding agent's **environment** (steering files, checks, tools, docs) from what its sessions show, so future runs go better. Every retro is a folder the next one reads: its sessions count as read, and each fix carries a status until it is done or declined.

`<skill-dir>` is the folder holding this file. Run the script as `python3 <skill-dir>/scripts/retro.py <command>` (needs PyYAML); `--help` lists the commands. When the script reports `config.yaml` missing, ask the user to copy `<skill-dir>/config.example.yaml` to it and fill it.

A retro reads one session. When `retro.py session <id>` exits 1 on an unknown id or an ambiguous prefix, its one line names it or the candidates: ask the user which one.

Write every file in English. Talk to the user in the language they use.

## Mode

| Argument | Mode |
|---|---|
| none | **report** on the current session |
| a session id, or a unique prefix of one | **report** on that session |
| a folder holding `retro.yaml` | **roadmap** |

`retro.py pending` lists the sessions no retro has read yet, minus those the [triage](#triage) judged `skip`, to pick an id from. The **band**, a row above the prompt (`SETUP.md` step 6), offers today's sessions the triage judged `worth`, one per press.

## report

1. **Style.** Load the `writing-for-agents` skill: every fix this retro proposes is text an agent will read. When it is not installed, say so in one line and go on.
2. **Session.** Run `retro.py session [<id>]` (no id: the current session). It prints two lines:
   - the metrics file, written by the sibling `session-log` skill when missing or stale: calls, failures, repeats, search streaks, compactions, cost. Its header gives the full id, the project and the span. Read it.
   - the retro **folder**: `<retros>/<YYYY-MM-DD>-<slug of the session's title>/`, or the folder of a retro already naming the session. `transcript.txt` there is the session's conversation, written just now.

   A session that started with `/retro-report` is a **retro session**: `session` exits 1 saying so, and creates nothing. Ask the user whether to read it anyway; on a yes, run `retro.py session <id> --anyway`. Triage judges such a session `skip`.
3. **Read.** Read the whole conversation, then what steered it:
   - **Another session:** read `<folder>/transcript.txt` whole, in parts when it is long. Each call is `#n`, the number `call` takes in the evidence. For the moments that become evidence, run `python3 <skill-dir>/../session-log/scripts/sessions.py transcript <id> --from N --to M --full`; add `--agent <id>` when a candidate hinges on a subagent.
   - **The current session** is in your context, and `transcript.txt` holds it up to now: read there what a compaction dropped, and search it for each evidence moment to take its `#n`, or give the moment as `at`. When the context is nearly full, suggest `/clear` and then `/retro-report <id>` instead.
   - **The repos it worked in:** their steering files (`CLAUDE.md`, `AGENTS.md`, `CODING_STANDARDS.md`) and their own check commands (lint, typecheck, test scripts, pre-commit hooks, CI workflows).

   Done when the whole conversation is read. Tell the user what you read.
4. **Record.** Look for candidates in each [category](#categories); each traces to moments of the session. Write them to `<folder>/retro.yaml` ([shape](#retroyaml)) in English before showing anything:
   - `created` is now, local time with its offset (`2026-11-14T08:39:00-03:00`); `session` is the full id from the metrics header.
   - One finding per candidate, most severe first, each `status: reviewing`, with `category`, `severity`, `what`, `evidence`, `fix` and `lands_in`: the file, check or tool the fix changes ([where a fix lands](#where-a-fix-lands)).
   - Severity: `high` broke work or will recur every session; `medium` cost time or tokens in this session; `low` friction.
   - Evidence is one item per moment: `call` (the `#n`) or `at`, which joins the transcript span's date and the line's time in UTC (`2026-11-14T10:32:05Z`).
   - No candidate at all: write `findings: []` and say so. A retro naming the session is what marks it read and takes it off the band.

   Run `retro.py validate <folder>` and fix every error.
5. **Review.** Give the folder's path, then show each finding in this shape, in the user's language:

   ```
   ### C1 · automated-checks · high
   **What happened:** the agent committed twice with failing tests; nothing ran them before the commit.
   **Evidence:**
   - #42 `Bash: git commit -m ...` -> `3 failed`
   - 10:32:05 `user: run the tests before committing`
   **Fix:** a pre-commit hook runs pytest.
   **Lands in:** .githooks/pre-commit
   ```

   `C<n>` is the finding's `id`; an evidence line is `#<call>` or the `at` as the transcript's `HH:MM:SS`, then its excerpt. End with the reply line: `C1 keep`, `C2 reword: <text>`, `C3 decline: <reason>`. Each reply changes the finding in `retro.yaml`:

   | Reply | Finding |
   |---|---|
   | keep | `status: accepted` |
   | reword | the text changed, `status: accepted` |
   | decline | `status: wontfix`, `wontfix: <reason>` |
   | none | stays `reviewing` until a verifier, outside this skill, judges it |

   Add the decisions taken while discussing, then run `retro.py validate <folder>` again.
6. **Close.** Show `retro.py check <folder> --all`. Offer to commit the folder, following the conventions of the repo that holds the retros. Say that `/retro-report <folder>` plans the accepted fixes, and that `retro.py render <folder>` writes `retro.md` when the user wants it.

## roadmap

- **No `roadmap.yaml` in the folder:** read `retro.yaml`. Run the ROADMAP step of the `flow` skill with `--specs <folder>` over the `accepted` findings: one feature per fix, or one for fixes that change the same thing together. A `reviewing` finding waits until it is accepted or declined. Once the roadmap is approved, set each finding's `feature` to its roadmap id, then validate: those findings show as `planned`. Each feature is built later with `/flow`, its `--root` the repo the fix changes.
- **A roadmap exists:** run `retro.py check <folder> --all` and show it. When nothing is left to do and `outcome` is empty, offer to write the Outcome, then validate.

## Triage

A SessionEnd hook judges each session as it ends, right after `session-log` writes its file (`SETUP.md` step 7): `retro.py triage --hook` reads the file's path from `sessions.py extract --hook --print-path` and records `worth` or `skip`, with the rules that fired, in `<retros>/triage/<YYYY-MM-DD>-triage.yaml`. A session is `skip` when it is a retro session (it started with `/retro-report`) or below `triage.min_calls`, and `worth` when any rule in `triage.limits` of `config.yaml` reaches its limit. Only sessions of the configured `projects` are judged.

To judge sessions the hook missed, or after changing the limits: `retro.py triage <session.yaml>...` over `session-log`'s files. It prints one verdict per session and replaces each session's earlier entry.

## Categories

The keys `retro.yaml` takes, each with what to look for:

- `navigation`: the agent took long to find a file or a fact; a hidden dependency between files. Fix: a navigation pointer.
- `automated-checks`: a mistake a lint, type check, test or hook would have caught; a checker that exists but nothing runs, or runs broken. Read the repo's own check commands first, so the finding is the missing wiring, not a reinvented check. A repo with no **guardrail** (no pre-commit hook and no CI job running its lint, typecheck or test command) is itself a finding.
- `coding-standards`: the reviewer missed something, or a rule needs adding, removing or clarifying. Classify the violation first: a **mechanical** one (a fixed pattern, a banned API, an import shape, a file location) or a **judgement call** (cross-file consistency, matching the surrounding style). [Where a fix lands](#where-a-fix-lands) says where each goes.
- `global-agents-md`: steering that belongs in coding standards or a check, in an `AGENTS.md` / `CLAUDE.md` grown large.
- `tool-economy`: expensive or repeated calls that a script, a pointer or a cheaper tool would replace.
- `no-ops`: steering lines that change nothing the agent would do anyway.
- `information-access`: a crucial fact the agent could not reach (logs, a service, a doc).

## Where a fix lands

Work goes through two stages. The implementing agent carries the most context pressure (exploring, writing, debugging); the reviewer the least (it receives a diff). Rules to enforce belong to review and checks, not to the implementer's always-loaded files.

| Place | Holds |
|---|---|
| a check (linter rule, pre-commit hook, CI job, whichever the repo's guardrail makes cheapest) | every mechanical rule, full stop |
| `CLAUDE.md` / `AGENTS.md` | navigation pointers only: they load into every agent's context |
| `CODING_STANDARDS.md` | judgement calls, read during review; past 1,000 lines, pointers to docs |
| docs | references the files above point to; look for an existing doc before writing one |
| a skill | a doc its description makes findable, or a user-invoked command, written as `writing-for-agents` says |

## retro.yaml

```yaml
created: 2026-11-14T08:39:00-03:00          # when the retro was written, local time with its offset
title: checkers on commit
summary: >
  What the session did, in a few lines.
session: f7d25f99-d8b7-491a-8ddf-e265777467b1    # the one session read, its full id
findings:
  - id: 1                                  # 1, 2, 3 …
    category: automated-checks
    severity: high                         # high, medium or low
    status: accepted                       # reviewing, accepted or wontfix
    what: >
      What happened, in a few lines.
    evidence:                              # the moments it happened, at least one
      - call: 42                           # the transcript's #n, 1 to calls.total
        excerpt: "Bash: python: command not found"
      - at: 2026-11-14T10:32:05Z           # a moment with no call number: the span's date, the line's UTC time
        excerpt: "user: run the tests before committing"
    fix: What to change, in words
    lands_in: .githooks/pre-commit         # the file, check or tool the fix changes
    feature: F1.1                          # set in roadmap mode, on an accepted finding only
  - id: 2
    category: tool-economy
    severity: low
    status: wontfix
    what: >
      What happened.
    evidence:
      - call: 7
        excerpt: "Read: README.md (again)"
    fix: What to change
    lands_in: CLAUDE.md
    wontfix: the reason                    # exactly when status is wontfix
decisions:
  - What was settled while discussing the findings.
outcome: >                                 # optional: written when the roadmap is done
  When it finished, what changed, what was learned.
```

Each evidence item has exactly one of `call` and `at` (with a timezone), and an excerpt of at most 3 lines and 300 characters. `validate` checks that `call` is within the session's calls and `at` between its start and end.

`status` is written: `reviewing` until the user or a verifier settles it, then `accepted` or `wontfix`. `check` and `retro.md` show an accepted finding by its roadmap: `open` (no feature yet), `planned`, or `fixed` (its feature is done). Only accepted findings count as to do.

`retro.md` exists only after `retro.py render <folder>`, run when the user asks. It is generated: change the yaml and render again.
