---
name: spec-lite
description: Lightweight spec-driven flow for personal and small projects. A YAML roadmap of milestones and features, then spec → tasks → execute → validate per feature, with state changed only through a script. Use when planning a roadmap, specifying, building or resuming a feature in a personal or simple project, or when the user names spec-lite. For large, risky or shared work, suggest tlc-spec-driven.
metadata:
  based-on: tlc-spec-driven 4.1.0
---

# spec-lite

```
ROADMAP ─→ SPECIFY ─→ TASKS ─→ EXECUTE ─→ VALIDATE
             stop 1     stop 2
```

Each feature passes two human stops: the user approves the spec, then the tasks. Everything between is yours.

## State lives in YAML, changed by the script

`.specs/ROADMAP.yaml` holds milestones, features and their status; each feature's `tasks.yaml` holds tasks and checks. Every status change goes through `scripts/specs.py` (in this skill's folder, run as `python3 <skill-dir>/scripts/specs.py <command>` from the project root). Content (titles, tasks, checks) you edit by hand, then run `check`. A non-zero exit means stop and fix what it prints.

| When | Command |
| --- | --- |
| No `.specs/` yet | `init <project>`, then `milestone "<title>" --goal "..."` |
| A new piece of work | `add <mN> <slug> "<title>"`: takes the next `mN.fN` code |
| Starting a feature | `start <feature>`: creates the folder and `spec.md` from the template; todo → spec |
| The user approved the spec | `approve <feature> spec`: writes the `tasks.yaml` skeleton; spec → tasks |
| The user approved the tasks | `approve <feature> tasks`: records the git `base`; tasks → doing |
| During execution | `set <feature> T1 doing\|done`, `set <feature> AC1 pass\|fail`, `commit-msg <feature> T1` |
| Every check passed | `finish <feature>`: doing → done |
| Resuming, or "where are we" | `status` |
| After any hand edit | `check [feature]` |

The approve commands record the user's approval: run one only in the turn the user gives it.

```
.specs/
├── ROADMAP.yaml
└── features/m1.f2.export-csv/     # milestone 1, feature 2, slug
    ├── spec.md                    # what and why, AC1..n, out of scope
    ├── design.md                  # large features with an architecture decision only
    └── tasks.yaml                 # tasks, checks, suite command, git base
```

A milestone is a cut that delivers value on its own; a feature is a piece of it, small enough to finish in a few sessions.

## Size the work first

| Size | Signal | Files | Grill | Review |
| --- | --- | --- | --- | --- |
| Small | ≤3 files, one sentence describes it | none: state the outcome in one line, build it, run the tests, commit | never | — |
| Medium | a clear feature, ≤5 tasks | `spec.md` (design in `## Notes`), `tasks.yaml` | offer once | — |
| Large | several components or a design choice | `spec.md`, `design.md` when a choice needs explaining, `tasks.yaml` | by default | `code-review` |

**Escalate to `tlc-spec-driven`** when any holds: more than ~8 tasks; a screen must match a given design pixel for pixel; auth, payments, money, concurrency or migrating real data; other people depend on the result; the user asks for rigor. Say which signal fired and recommend the switch; the user decides. tlc uses the same `m<N>.f<N>.<slug>` folder, so it picks up from the existing `spec.md`.

## Steps

1. **Roadmap.** On `init`, check the project has a `CLAUDE.md` or `AGENTS.md` stating its commands, folder structure, code style and boundaries (always / ask first / never); when it lacks one, offer to write it with `/init`. These hold for every feature, so specs never repeat them. Read `ROADMAP.yaml` (`status`). Work that is not in it gets a feature through `add`; when the milestone is unclear, ask. Planning a whole roadmap is a conversation about milestones first, features second.
2. **Specify** → read [references/spec.md](references/spec.md). Done when `check <feature>` passes and the user approved: `approve <feature> spec`.
3. **Tasks** → read [references/tasks.md](references/tasks.md). Done when `check <feature>` passes and the user approved: `approve <feature> tasks`.
4. **Execute and validate** → read [references/execute.md](references/execute.md). Done when `finish <feature>` exits 0.

**Resuming** (new session or after a compaction): run `status`, read the active feature's `spec.md` and `tasks.yaml`, compare with `git log`, and continue from the first task not done. Git wins over a status the files claim.

## Rules

- **Ask, then write.** Scope and product behaviour are the user's decisions: ask them, with your recommendation first. Facts you find in the code yourself. Each answer goes into its file in the turn it arrives; the chat does not survive a compaction.
- **One task, one commit**, with the message prepared in `tasks.yaml`. Stage files by name.
- **Tests prove the spec.** A test asserts the outcome an AC states, never the code's internals. A red test is fixed in the code; the test changes only when the spec changed.
- Approval covers local work and local commits. Push, deploy and anything destructive need their own go-ahead.

## Companion skills

Load each when its step says so: `grilling` (stress-test a spec), `tdd` (each task, when the project has tests), `code-review` (large features). Without one, do the step inline: grill as numbered questions with your recommended answer; write the test before the code; review the diff against the spec yourself.

Generated documents: headings in English, prose in the project's language, identifiers never translated.
