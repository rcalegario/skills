---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag or merge-base) on separate axes, each run by its own sub-agent, and report structured findings that /flow can record. Use when the user wants to review a branch, a PR or work in progress, or asks to \"review since X\"."
---

Review of the diff between `HEAD` and a fixed point the user supplies. Each axis runs as its own **sub-agent with a fresh context window**, so axes do not pollute each other; this skill gathers their findings.

The skill only reads and reports. It edits no file and records nothing: fixes and `flow.py finding` calls belong to whoever called it.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point (a commit SHA, branch, tag, `main`, `HEAD~5`). `/flow` passes its `base`. If none was given, ask for it.

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base), and the commits with `git log <fixed-point>..HEAD --oneline`.

Run `git rev-parse <fixed-point>` and check the diff is not empty **before anything else**. A bad ref or an empty diff stops the review here with a one-line message, so no sub-agent is spawned for nothing.

### 2. Find the spec

Look for the originating spec, in this order, and stop at the first hit:

1. A path the caller passed (`/flow` passes the feature's `spec.md` and `feature.yaml`).
2. The current feature's `spec.md` and `feature.yaml` when the repo works with `/flow` (a `.specs/` folder, or the task folder it names).
3. Issue references in the commit messages (`#123`, `Closes #45`, `!67`), read with `gh issue view` or `glab` when the CLI is available. When it is not, note the reference and go on.
4. A file under `docs/` or `specs/` named like the branch or the feature.

Never ask the user to set up an issue tracker. When nothing is found, ask where the spec is. If the user says there is none, skip the Spec axis and write "Spec skipped: no spec available" in the report.

### 3. Find the standards

Search the repo for every file that documents how code is written: `CLAUDE.md` and `AGENTS.md` (root and the folders the diff touches), `CONTRIBUTING.md`, `CODING_STANDARDS.md`, style docs under `docs/`. When `CODING_STANDARDS.md` or `CONTRIBUTING.md` exists it must be on the list. Always add the user's own `~/.claude/CLAUDE.md` when it exists: it carries rules that hold in every repo.

Then attach the **smell baseline** in `reference/smells.md`, in full. It applies even when a repo documents nothing, with two rules: a documented repo standard overrides the baseline, and every smell is a labelled judgement call, never a hard violation. Skip anything tooling already enforces.

## Why separate axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the spec asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
