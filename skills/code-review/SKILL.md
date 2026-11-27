---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag or merge-base) along two axes, Standards (does the code follow this repo's documented standards?) and Spec (does it do what the spec asked?), each run by its own sub-agent in parallel and reported side by side. Use when the user wants to review a branch, a PR or work in progress, or asks to \"review since X\"."
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards**: does the code conform to this repo's documented coding standards?
- **Spec**: does the code faithfully implement the originating spec or issue?

Both axes run as **parallel sub-agents** so they don't pollute each other's context; this skill then aggregates their findings. It edits no file; given a feature folder, it records the findings in that feature's `review.yaml` through `flow.py` (step 6).

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point (a commit SHA, branch, tag, `main`, `HEAD~5`). `/flow` passes its `base`. If none was given, ask for it.

Run `git rev-parse <fixed-point>` first. When it fails, stop with one line: "Review stopped: `<ref>` is not a valid ref." Then capture the diff command once, `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base), and the commits with `git log <fixed-point>..HEAD --oneline`. When the diff is empty, stop with one line: "Review stopped: no changes between `<ref>` and `HEAD`." No sub-agent starts for nothing.

### 2. Find the spec

Look for the originating spec, in this order, and stop at the first hit:

1. A path the caller passed (`/flow` passes the feature's `spec.md` and `feature.yaml`).
2. The current feature's `spec.md` and `feature.yaml` when the repo works with `/flow` (a `.specs/` folder).
3. Issue references in the commit messages (`#123`, `Closes #45`), read with `gh issue view` when the CLI is available.
4. A file under `docs/` or `specs/` whose name matches the branch name or the feature.

When nothing is found, ask the user where the spec is. If they say there is none, the Spec sub-agent is skipped and the report says "no spec available".

### 3. Find the standards

Search the repo for every file that documents how code is written: `CLAUDE.md` and `AGENTS.md` (root and the folders the diff touches), `CONTRIBUTING.md`, `CODING_STANDARDS.md`, style docs under `docs/`. When `CODING_STANDARDS.md` or `CONTRIBUTING.md` exists, it must be on the list.

On top of what the repo documents, the Standards axis always carries the **smell baseline** in `reference/smells.md`: a fixed set of Fowler code smells that applies even when a repo documents nothing. A documented repo standard overrides it, and every smell is a labelled judgement call, never a hard violation.

### 4. Spawn both sub-agents in parallel

Issue both sub-agent calls together, each with the `model` option set to `sonnet`, and wait for both. Each gets the diff command and the commit list, and answers one line per finding in the format of `reference/findings.md` (pasted into its prompt), with the line number of the file as it stands at `HEAD`.

**Standards sub-agent**: the standards files from step 3 (as paths) and `reference/smells.md` pasted in full (the sub-agent has no other access to it). Brief: "Report, per file and hunk, (a) every place the diff violates a documented standard, citing the file and the rule, and (b) any baseline smell you spot, naming it and quoting the hunk. Documented-standard breaches can be hard; baseline smells are always judgement calls, at most `should-fix`, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Source `standards-review`. Under 400 words."

**Spec sub-agent**: the path or fetched contents of the spec. Brief: "Report (a) requirements the spec asked for that are missing or partial, (b) behaviour in the diff that was not asked for, (c) requirements that look implemented but where the implementation looks wrong. Quote the spec line for each finding. Source `spec-review`. Under 400 words."

If the spec is missing, skip the Spec sub-agent.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings: the two axes are deliberately separate (see _Why two axes_). A skipped Spec axis keeps its heading with "Spec skipped: no spec available".

End with one summary line per axis: how many findings, and the worst one within that axis. Never pick a single winner across axes.

### 6. Record the findings (only with `--feature`)

When the caller passed `--feature <folder>` (with the `--root` and `--specs` of its `flow.py` calls), the review is kept in that feature's `review.yaml`, which `flow.py` owns: it creates the file, numbers each finding `R-n` and checks it. Never write `review.yaml` by hand.

- `flow.py` is the sibling skill's script, `<skill-dir>/../flow/scripts/flow.py`. When it is not there, record nothing and add one line to the report: "Not recorded: flow.py not found."
- For each finding of both axes, in report order, run:

  ```bash
  python <flow.py> --root <root> --specs <specs> finding <feature> --text "<what is wrong>" --source <source> \
    --severity <severity> --confidence <confidence> --file <file> [--line <line>] --hunk "<hunk>" --fix "<fix>"
  ```

  Each value comes from the finding's line as the sub-agent wrote it (`reference/findings.md`); `--line` is left out when the file is `-`. Give no `--action`: the outcome is the caller's to decide.
- When both axes ran and neither has a finding, run `finding <feature> --none --axes spec,standards` once instead. When the Spec axis was skipped, record only the Standards findings (no `--none`), and say in the report that the spec part was not reviewed.
- When a call exits non-zero, stop recording, and report the command, its output and the findings left unrecorded under the summary: `review.yaml` then holds only the findings before it.

End the report with the ids `flow.py` printed (`R-1`..`R-n`, or "clean review recorded").

Without `--feature`, nothing is recorded and no file is edited.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the spec asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
