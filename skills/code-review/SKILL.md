---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag or merge-base) on separate axes, each run by its own sub-agent, and report structured findings that /flow can record. Use when the user wants to review a branch, a PR or work in progress, or asks to \"review since X\"."
---

Review of the diff between `HEAD` and a fixed point the user supplies. Each axis runs as its own **sub-agent with a fresh context window**, so axes do not pollute each other; this skill gathers their findings.

The skill only reads and reports. It edits no file and records nothing: fixes and `flow.py finding` calls belong to whoever called it.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point (a commit SHA, branch, tag, `main`, `HEAD~5`). `/flow` passes its `base`. If none was given, ask for it.

Run `git rev-parse <fixed-point>` first. When it fails, stop with one line: "Review stopped: `<ref>` is not a valid ref."

Then capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base), and the commits with `git log <fixed-point>..HEAD --oneline`. When the diff is empty, stop with one line: "Review stopped: no changes between `<ref>` and `HEAD`." No sub-agent is spawned for nothing.

The diff covers committed work only. When `git status --short` shows uncommitted changes, say in the report that they are not part of the review.

### 2. Find the spec

Look for the originating spec, in this order, and stop at the first hit:

1. A path the caller passed (`/flow` passes the feature's `spec.md` and `feature.yaml`).
2. The current feature's `spec.md` and `feature.yaml` when the repo works with `/flow` (a `.specs/` folder, or the task folder it names).
3. Issue references in the commit messages (`#123`, `Closes #45`, `!67`), read with `gh issue view` or `glab` when the CLI is available. When it is not, note the reference, mention it in the question below, and go on.
4. A file under `docs/` or `specs/` whose name contains the branch name without its type prefix (`feature/seed` → `seed`) or the feature id.

A spec file that the change itself adds is still the spec: the Spec sub-agent reads it as the spec and does not review it as code.

Never ask the user to set up an issue tracker. When nothing is found, ask where the spec is. If the user says there is none, skip the Spec axis: the report keeps a `## Spec` section that holds the line "Spec skipped: no spec available".

### 3. Find the standards

Search the repo for every file that documents how code is written: `CLAUDE.md` and `AGENTS.md` (root and the folders the diff touches), `CONTRIBUTING.md`, `CODING_STANDARDS.md`, style docs under `docs/`. When `CODING_STANDARDS.md` or `CONTRIBUTING.md` exists it must be on the list. Always add the user's own `~/.claude/CLAUDE.md` when it exists: it carries rules that hold in every repo.

Then attach the **smell baseline** in `reference/smells.md`, in full. It applies even when a repo documents nothing, with two rules: a documented repo standard overrides the baseline, and every smell is a labelled judgement call, never a hard violation. Skip anything tooling already enforces.

### 4. Run the repo's own checks

Before any sub-agent, run the checks the repo defines, **once**: its tests, linter and type checker. Find the commands in this order: `CLAUDE.md` / `AGENTS.md`, then `Makefile`, `package.json` scripts, `pyproject.toml`, the CI config (`.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, `Jenkinsfile`). Never infer a command from a folder name (a `tests/` folder is not a command).

- Run only commands that read and verify: test, lint, typecheck, format check. Never an install, build-and-deploy, migration, or any command that changes something outside the working tree.
- Checks must leave the tree as they found it. Take `git status --short` before, run with the usual cache switches (`PYTHONDONTWRITEBYTECODE=1` for Python), and take it again after. Files the checks created are reported under **Checks** as "created by the checks" and left in place; the skill deletes nothing.
- A failure goes under **Checks** in the report as a fact, with the command and the first failing lines. The axes do not review what a tool already proved: tell each sub-agent which checks failed so it does not repeat them.
- When no command is found, write "Warning: no checks found" under **Checks** and go on with the review. A warning is always a line that starts with `Warning:`.

### 5. Run the axes in parallel

Issue the Standards and the Spec sub-agent calls together, in the foreground. Start each with a fresh context window and give it **only** the diff command, the commit list and its own sources. The sub-agent runs the diff command itself; repo files are passed as paths for it to read, and the smell baseline is pasted in full. Neither sub-agent sees the other's sources or findings.

**Standards sub-agent**: the standards files from step 3, the smell baseline pasted in full (the sub-agent has no other access to it) and the failed checks from step 4. Brief: "Report every place the diff breaks a documented standard, citing the file and the rule, and any baseline smell you see, naming it and quoting the hunk. Documented-standard breaches can be hard; baseline smells are judgement calls, and a documented repo rule overrides the baseline. Skip anything tooling enforces or the failed checks already show. Read each file with line numbers before citing a line. One line per finding in the format of `reference/findings.md`, source `standards-review`. Under 400 words."

**Spec sub-agent**: the spec from step 2 and the failed checks from step 4. Brief: "Report (a) requirements the spec asked for that are missing or partial, (b) behaviour in the diff that was not asked for, (c) requirements that look implemented but are wrong. Quote the spec line for each. Read each file with line numbers before citing a line. One line per finding in the format of `reference/findings.md`, source `spec-review`. Under 400 words."

When there is no spec, skip the Spec sub-agent.

### 6. Verify the serious findings

For each axis that returned a `blocker` or `should-fix`, start **one** new sub-agent with a fresh context window and give it those findings, the diff command, the same sources as its axis (for Standards, the smell baseline too) and the failed checks from step 4. Brief: "Try to refute each finding against the code: read the surrounding code and the spec or rule it cites, and look for a guard, a caller or a requirement that makes it wrong. Check every cited `file:line` against the file and correct it when it is off. Answer per finding: `kept`, `downgraded to <severity>` or `dropped`, with one sentence of evidence."

- `kept` and `downgraded` findings go into the report with their final severity.
- `dropped` ones are not hidden: they go under **Dropped by verify**, with the finding and the refuter's reason, so the user can overrule.
- `nit` findings skip this step.

### 7. Report

Write one section per axis, under `## Standards` and `## Spec`, with the findings in the format of `reference/findings.md`. The order is `## Checks` (what step 4 found: failures, files the checks created, warnings), `## Standards`, `## Spec`, `## Dropped by verify`, then the summary lines. Do **not** merge or rerank findings across axes: the separation exists to prevent that.

The summary has one line per axis: how many findings, and the worst one in that axis; add a line for **Checks** when something failed. Never pick a single winner across axes.

## Why separate axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the spec asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
