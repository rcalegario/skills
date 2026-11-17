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

### 4. Run the repo's own checks

Before any sub-agent, run the checks the repo defines, **once**: its tests, linter and type checker. Find the commands in this order: `CLAUDE.md` / `AGENTS.md`, then `Makefile`, `package.json` scripts, `pyproject.toml`, the CI config.

- Run only commands that read and verify: test, lint, typecheck, format check. Never an install, build-and-deploy, migration, or any command that changes something outside the working tree.
- A failure goes under **Checks** in the report as a fact, with the command and the first failing lines. The axes do not review what a tool already proved: tell each sub-agent which checks failed so it does not repeat them.
- When no command is found, write "Checks: none found" as a warning in the report and go on with the review.

### 5. Run the axes in parallel

Issue the Standards and the Spec sub-agent calls together, in the foreground. Start each with a fresh context window and give it **only** the diff command, the commit list and its own sources. Neither sees the other's sources or findings.

**Standards sub-agent**: the standards files from step 3, the smell baseline pasted in full (the sub-agent has no other access to it) and the failed checks from step 4. Brief: "Report every place the diff breaks a documented standard, citing the file and the rule, and any baseline smell you see, naming it and quoting the hunk. Documented-standard breaches can be hard; baseline smells are judgement calls, and a documented repo rule overrides the baseline. Skip anything tooling enforces or the failed checks already show. One line per finding in the format of `reference/findings.md`, source `standards-review`. Under 400 words."

**Spec sub-agent**: the spec from step 2 and the failed checks from step 4. Brief: "Report (a) requirements the spec asked for that are missing or partial, (b) behaviour in the diff that was not asked for, (c) requirements that look implemented but are wrong. Quote the spec line for each. One line per finding in the format of `reference/findings.md`, source `spec-review`. Under 400 words."

When there is no spec, skip the Spec sub-agent.

### 6. Verify the serious findings

For each axis that returned a `blocker` or `should-fix`, start **one** new sub-agent with a fresh context window and give it those findings, the diff command and the same sources as its axis. Brief: "Try to refute each finding against the code: read the surrounding code and the spec or rule it cites, and look for a guard, a caller or a requirement that makes it wrong. Answer per finding: `kept`, `downgraded to <severity>` or `dropped`, with one sentence of evidence."

- `kept` and `downgraded` findings go into the report with their final severity.
- `dropped` ones are not hidden: they go under **Dropped by verify**, with the finding and the refuter's reason, so the user can overrule.
- `nit` findings skip this step.

### 7. Report

Write one section per axis, under `## Standards` and `## Spec`, with the findings in the format of `reference/findings.md`. Put `## Checks` first with what step 4 found (failures, or "none found"), and `## Dropped by verify` last. Do **not** merge or rerank findings across axes: the separation exists to prevent that.

End with one line per axis: how many findings, and the worst one in that axis. Never pick a single winner across axes.

## Why separate axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the spec asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
