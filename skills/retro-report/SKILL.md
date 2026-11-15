---
name: retro-report
description: Retro over the Claude Code sessions no retro has read yet, written as a tracked report whose fixes become a /flow roadmap. /retro-report [<retro-folder> | <session ids>]
disable-model-invocation: true
---

# retro-report

You are improving the coding agent's **environment** (steering files, checks, tools, docs) from what its sessions show, so future runs go better. Every retro is a folder the next one reads: its sessions count as read, and each fix carries a status until it is done or declined.

`<skill-dir>` is the folder holding this file. Run the script as `python3 <skill-dir>/scripts/retro.py <command>` (needs PyYAML); `--help` lists the commands. `pending` and `check` with no folder read `<skill-dir>/config.yaml` (`retros`, the folder holding the retros, and `projects`); when it is missing, ask the user to copy `config.example.yaml` and fill it.

Write every file in English. Talk to the user in the language they use.

## Mode

| Argument | Mode |
|---|---|
| a folder holding `retro.yaml` | **roadmap** |
| none | **report** over every pending session |
| anything else (session ids, "the last 3 sessions") | **report** over those sessions only |

## report

1. **Sessions.** List them: `retro.py pending` for no argument; for named sessions, find each log under `~/.claude/projects/` (`<id>.jsonl`). Say how many there are. None → say so and stop.
2. **Folder.** Propose `<retros>/<YYYY-MM-DD>-<slug>/` (today, the slug from the sessions' main theme) and confirm it. Digest every session into it: `retro.py digest <logs> > <folder>/sessions.yaml`. Every digested session goes into `sources.sessions`, so it leaves `pending`: the Sessions table is the record of what was looked at.
3. **Read.** From the digests, pick the sessions worth reading in depth: failures, search streaks, repeats, the highest cost and minutes. Read those logs around the flagged calls, plus the steering files and checks of the repos they worked in. Tell the user which sessions you read and why. Done when every flagged session is read or named as skipped with a reason.
4. **Findings.** Look for candidates in each [category](#categories), with the evidence (session, what happened). Present them in order of severity, each with a proposed fix in words. The user keeps, rewords or declines each one; a declined one stays as `wontfix` with the reason when the user wants it recorded.
5. **Write.** Write `<folder>/retro.yaml` ([shape](#retroyaml)), with the decisions taken while discussing. Run `retro.py validate <folder>` and fix every error, then `retro.py render <folder>`. `retro.md` is generated: change the yaml and render again.
6. **Close.** Show the Findings table. Offer to commit the folder, following the conventions of the repo that holds the retros, and say that `/retro-report <folder>` plans the fixes.

## roadmap

- **No `roadmap.yaml` in the folder:** read `retro.yaml`. Run the ROADMAP step of the `flow` skill with `--specs <folder>` over the findings without `wontfix`: one feature per fix, or one for fixes that change the same thing together. Once the roadmap is approved, set each finding's `feature` to its roadmap id, then validate and render: those findings show as `planned`. Each feature is built later with `/flow`, its `--root` the repo the fix changes.
- **A roadmap exists:** run `retro.py check <folder> --all` and show it. When nothing is left to do and `outcome` is empty, offer to write the Outcome (when the roadmap finished, what changed, what was learned on the way), then validate and render.

## Categories

The keys `retro.yaml` takes, each with what to look for:

- `navigation`: the agent took long to find a file or a fact; a hidden dependency between files. Fix: a navigation pointer.
- `automated-checks`: a mistake a lint, type check, test or hook would have caught; a checker that exists but nothing runs. Read the repo's own check commands first, so the finding is the missing wiring, not a reinvented check.
- `coding-standards`: the reviewer missed something. A mechanical rule (a pattern, a banned API, a file location) gets a deterministic check; the standards file keeps only judgement calls.
- `global-agents-md`: steering that belongs in coding standards or a check, in an `AGENTS.md` / `CLAUDE.md` grown large.
- `tool-economy`: expensive or repeated calls that a script, a pointer or a cheaper tool would replace.
- `no-ops`: steering lines that change nothing the agent would do anyway.
- `information-access`: a crucial fact the agent could not reach (logs, a service, a doc).

Weigh where a fix lands: the implementing agent carries the most context pressure, the reviewer the least, so rules to enforce belong to review and checks; always-loaded files hold only pointers.

## retro.yaml

```yaml
date: 2026-11-14
title: checkers on commit
summary: >
  What the sessions did, in a few lines.
sources:
  sessions: [f7d25f99-d8b7-491a-8ddf-e265777467b1]   # every digested session, matching sessions.yaml
findings:
  - id: 1                                  # 1, 2, 3 …
    category: automated-checks
    what: >
      What happened, with the evidence.
    fix: What to change, in words
    sessions: [f7d25f99-d8b7-491a-8ddf-e265777467b1]   # optional: where it happened
    feature: F1.1                          # set in roadmap mode; or wontfix: <reason>, never both
decisions:
  - What was settled while discussing the findings.
outcome: >                                 # optional: written when the roadmap is done
  When it finished, what changed, what was learned.
```

A finding's status comes from the folder's roadmap: `open` (no feature yet), `planned`, `fixed` (its feature is done) or `wontfix`.
