# Task folder format

A task folder records the facts, decisions, plan and proof behind one piece of work. It lives in `<home>/tasks/<main-repo>/<YYYY-MM-DD-HHMM>-<slug>/`: the first level is the task's main repo, the name carries the start time (see the task `SKILL.md`). Templates for every file are in `../templates/`. Write in English; code, paths and names in backticks; dates `YYYY-MM-DD`; titles in YAML between quotes.

## Files

| Path | Format | Holds |
|---|---|---|
| `README.md` | md + YAML header | the base text verbatim (with its link), the problem, who it serves, what stays out. Header: `id` (the folder name), `title`, `link`, `repos:` (exactly one with `main: true`) |
| `acs.yaml` | YAML | outcomes (`AC-n`) and extras (`X-n`), each split into requirements, each with its derived `status` |
| `context/*.md` | md + YAML header | facts only, each file with its `code` and the date it was read |
| `context/archive/` | any | frozen old material, read only, never checked |
| `decisions/D-nn-<slug>.yaml` | YAML | one question per file |
| `validations/V-nn-<slug>.yaml` | YAML | one concrete check, with evidence: a proof of a requirement, or a spike (`decides`) that settles a decision |
| `validations/evidence/` | any | logs and screenshots a validation lists in `attachments` |
| `pending.yaml` | YAML | actions with other people or tasks (`P-n`) |
| `journal.yaml` | YAML | events in date order (`J-nnn`) |
| `brief.md` | md + YAML header | the consolidated view: today, target, path, open items. Header: `code`, `title`, `date`, and `sources` (one hash per group of files it summarises, see Brief sources). BRIEF-2 holds the requirements block and BRIEF-4 the open-items block, both written by `task.py` and never by hand (see Brief requirements, Brief open items) |
| `.specs/` | `/flow` | `roadmap.yaml` and `features/<id>/` with `spec.md` and `feature.yaml` |
| `repos/<repo>/` | git worktree | the code, on the task's branch; ignored by the home repo and by `status.py` |

Where each thing goes: **fact** → context; **choice** → decision; **change to the code** → a `/flow` feature; **proof** → validation; **experiment that picks an option** → spike (a validation with `decides`); **action with someone else** → pending; **event** (something read, decided, changed) → journal. Cite a fact by its id; never copy it.

## Chain

```text
requirement (acs.yaml) ──decision──▶ root decision ◀──born_from── child decisions
        ▲                                 ▲                              ▲
        │                                 └──── story.decisions ─────────┴── /flow feature
        └──────── proves ── validation ◀──── story.validations ──────────────────┘
```

Each link is written in one place; `status.py` derives the reverse:

| Link | Written in |
|---|---|
| requirement → root decision, validations | `acs.yaml` |
| child decision → the decision that created it | `born_from` of the decision |
| feature → decisions, validations | `story:` block of `feature.yaml` |
| roadmap feature not yet spec'd → decisions | `decisions:` of its entry in `roadmap.yaml` |
| spike → the decisions it settles | `decides` of the validation |
| pending item, journal note → ids it touches | `refs` |

## Ids

| Id | What | Born in |
|---|---|---|
| `AC-n` | an outcome that makes the task done: an acceptance criterion of the base text, or one settled at start | `acs.yaml` |
| `N-n` | a note item of an Aha story, an item like `AC-n` (`extensions/aha/aha.md`) | `acs.yaml` |
| `X-n` | item beyond the base text (nice to have), so scope growth stays visible | `acs.yaml` |
| `AC-n.m`, `X-n.m` | requirement inside an item | `acs.yaml` |
| `D-nn`, `V-nn`, `P-n`, `J-nnn` | decision, validation, pending item, journal note | their files |
| `<CODE>-n`, `<CODE>-n.m` | section of a context file or of `brief.md` | the heading itself |

- Each context file declares an upper-case `code` in its header, and each heading carries the id: `## NOW-7 Firewall today`, `### NOW-7.2 Docker bypasses ufw`.
- Ids are permanent: a new item takes the next free number; existing ones never move, even when the order looks odd.
- Cite by id in plain text: `see D-12`, `(NOW-7.2)`. `status.py` fails on a cited id that does not exist, in any file.
- `brief.md` cites only what still holds: `status.py` also fails when it cites a `superseded` decision (naming the active end of its `superseded_by` chain), a `dropped` decision, a `dropped` item or a requirement of one. Other files may cite them as history; the brief says it in words.
- Ids stay inside the task folder. Code, commits and the PR carry the reason in words, never the id.

## Requirements and the decision tree

- A requirement is one verifiable thing an item asks for, and points to **one** root decision. A decision may be the root of several requirements.
- A new question: **is it in the text of the AC?** It becomes a requirement. **Does it exist only because of a choice of ours?** It becomes a child decision, with `born_from` naming the decision that created it.
- `born_from` is strict: "this question exists because of that choice". Influence goes in the text.
- A context fact that threatens a decision becomes a child decision of it, not a new requirement. When the base text did not foresee the fact, say so in `consequences`.
- A requirement's tree is its root plus every active child, recursively. `superseded` and `dropped` decisions leave the tree. Every active decision sits in some tree; anything beyond the base text goes into an `X-n` item.
- The split of each item into requirements is confirmed with the user before it is written.

## Status

Every entity with a status shows it in its own file. Nobody types a status: a script writes it, and a script that sets the status of a higher entity first checks the lower ones. Two kinds:

- **Derived** (requirement, item, roadmap feature and milestone, feature task, feature): the status follows from the entities below it. It is written by `task.py sync` (which every `task.py` command runs after its own edit) or by `flow.py`; `status.py` fails when the written status differs from the computed one, and when it is missing.
- **Recorded** (decision, validation, pending item, check): a person's act changes it, through the `task.py` or `flow.py` command that owns it, which refuses a move the machine does not allow.

After a `/flow` command in a task, run `task.py <task> sync`, so the requirements follow the features.

| Entity | File | Machine | Moved by |
|---|---|---|---|
| decision | `decisions/D-nn-*.yaml` | `open` → `proposed` → `decided`; `decided`, `proposed` → `superseded`; `dropped` | `task.py decide`, `supersede` (a decided decision is never decided again: supersede it) |
| validation | `validations/V-nn-*.yaml` | `pending` → `passed` \| `failed` (rerun allowed) \| `dropped` (final) | `task.py validate` |
| pending item | `pending.yaml` | `open` → `done` \| `dropped` (both final) | `task.py close` |
| check | `feature.yaml` | `pending` → `pass` \| `fail` | `flow.py set <feature> AC<n>`, only once every task covering it has a commit |
| feature task | `feature.yaml` | `todo` → `doing` → `verifying` → `done` | `flow.py set T<n> doing\|verifying`; `done` only when every check of the criteria it covers is `pass` (back to `verifying` when one fails) |
| feature | `feature.yaml` | `draft` → `approved` → `building` → `review` → `done` | `flow.py approve`, `set`, `review` (tasks `verifying` or `done`), `finish` (tasks `done`, checks `pass`, review recorded) |
| roadmap feature | `roadmap.yaml` | `planned` (no feature file yet), then the status of its feature | `flow.py`, after each command that changes a feature |
| roadmap milestone | `roadmap.yaml` | `planned` (all features planned) → `building` → `done` (all done) | `flow.py`, same |
| requirement | `acs.yaml` | `discovery` → `deciding` → `decided` → `built` → `concluded` (it can move back) | `task.py sync` |
| item | `acs.yaml` | the lowest status of its requirements, or `dropped` (an `X-n` the user dropped, written by hand) | `task.py sync` |

Requirement status:

| Status | When |
|---|---|
| `discovery` | no decision, more than one, or no validation |
| `deciding` | some decision in the tree is not `decided` |
| `decided` | tree all `decided`; some decision with `needs_code` (default true) has no `/flow` feature, or one not `done` |
| `built` | every needed feature `done`; some validation has not `passed` |
| `concluded` | every validation of the requirement `passed` |

What each requirement still misses follows its status: `discovery` the missing root decision or validation; `deciding` each decision of its tree not `decided` (with `discuss_with` and the spikes it awaits); `decided` each decision needing code with no feature, and each linked feature not `done`; `built` each validation not `passed`. `status.py` prints it in the **Missing** column and in `--json`.

## Step

The `/task` step comes from the folder: `status.py` prints it on its first line (`Step: <step> - <reason>`) and in `--json`. The first rule that holds wins:

| Step | When |
|---|---|
| `decide` | a decision `open` or `proposed`, not awaiting a spike and not in the `refs` of an open pending item |
| `consolidate` | no `brief.md`, no `date` or `sources` map in it, or a group of sources whose hash differs from the one stamped in it |
| `plan` | no `.specs/roadmap.yaml` |
| `spike` | a spike `pending` or `failed` blocks a feature not `done` |
| `build` | a `feature.yaml`, or a roadmap feature without one, not `done` |
| `review` | an item not `concluded` and without a `pr_note` |
| `done` | the README lists repos and none has a `worktree` (finish clears them) |
| `pr` | a feature without a `pr` link |
| `finish` | otherwise: every feature has a PR and a worktree remains |

Whether a PR is merged is not read: check it before `finish`.

Beside the reason, `--json` gives the step's `blockers` as data, the same entities the reason names, and `your_turn`. The reason is worded from them:

| Step | Each blocker (`id`, `kind`, `state`) |
|---|---|
| `decide` | a decision, `decision`, `open` or `proposed` |
| `consolidate` | `brief.md`, `brief`, `missing`, `no-date` or `no-sources`; or each changed group, `source`, `changed` |
| `plan` | `roadmap.yaml`, `roadmap`, `missing` |
| `spike` | a spike, `spike`, `pending` or `failed` |
| `build` | a feature (or a roadmap feature without a file), `feature`, its status |
| `review` | an item, `item`, its status |
| `pr` | a feature, `feature`, `no-pr` |
| `finish` | a repo, `repo`, `worktree` |
| `done` | none |

Each blocker also has `waiting`: `true` when it waits on someone else, because its id is in the `refs` of an open pending item, or it is a decision `proposed` whose `discuss_with` names someone and not `me`, or it is an item where everything its requirements miss (see Status) waits by those two rules. An item with nothing missing, or missing something that names no id (no root decision, no validation), does not wait.

`your_turn` says whether the next action is the user's: always on `consolidate`, `plan`, `build`, `pr` and `finish`; on `decide`, `spike` and `review` when some blocker is not `waiting`; never on `done`. A failure of the checks makes it `true` on any step.

### Brief sources

`task.py consolidate` stamps `sources` in the brief header: one 12-hex hash per group, over what a person writes and never over what a script stamps.

```yaml
date: 2026-11-19
sources:
  context: "3f9a1c07be52"
  acs: "9d2e4b60a1f7"
  decisions: "c18b7a5e0d34"
```

| Group | Hashed |
|---|---|
| `context` | the text of `context/*.md` without its `read_on` line; `context/archive/` is left out |
| `acs` | per item and requirement: `id`, `text`, `decision`, `validations`, and whether an item is `dropped`; never a derived `status` |
| `decisions` | per decision: `id`, `title`, `status`, `question`, `decision`, `why`, `consequences` and each option's `name` and `status`; never `date` |

Line endings and the layout of the YAML do not change a hash. A group that differs sends the task to `consolidate`, and the Step line names it (`context, decisions changed after brief.md`); a brief with no `sources` says `brief.md has no sources`. Pending items, the roadmap, validations, the journal and the README are not hashed.

### Brief requirements

BRIEF-2 starts with a block that every `task.py` command rewrites from `acs.yaml`: each item, in file order, and under it each of its requirements with its root decision, each text on one line (newlines and runs of spaces become one space). Items and requirements that are `dropped` stay out. A root that is `superseded` shows the active end of its `superseded_by` chain, and `(no active root)` when the chain ends in a dropped decision or nowhere. The hand-written target goes below it; nothing between the markers is edited by hand.

```markdown
## BRIEF-2 Target

<!-- task:generated requirements -->
- **AC-1** Users get the report out of the app
  - AC-1.1 (D-01) The report downloads as CSV
<!-- /task:generated -->

Where the target departs from the AC text, written by hand.
```

With no item or requirement left, the block holds `None: acs.yaml has no requirements.` The markers, the insertion under a `## BRIEF-2` heading that has none, and the failures of `status.py` (`block requirements is stale`, no block, no BRIEF-2 heading) work as for the open items below. A block whose end marker is gone fails `status.py` (`has no end marker`), and `task.py` leaves the brief as it is until it is fixed by hand.

### Brief open items

BRIEF-4 starts with a block that every `task.py` command rewrites from the decisions and `pending.yaml`: the open and proposed decisions and the open pending items, grouped by person like the Agenda of `status.py`. Hand prose (follow-ups, notes out of scope) goes below it; nothing between the markers is edited by hand.

```markdown
## BRIEF-4 Open items

<!-- task:generated open-items -->
**me**
- D-07 (proposed) Lock the PR - awaiting spike V-03

**PO**
- P-2 (pending) Ask for the vCenter snapshot
<!-- /task:generated -->

Follow-ups written by hand.
```

With nothing open, the block holds `None: no decision is open or proposed and no pending item is open.` A brief with a `## BRIEF-4` heading and no markers gets the block inserted under the heading at the next `task.py` command. `status.py` fails when the block differs from what the folder gives (`block open-items is stale`), when the markers are missing, or when the brief has no BRIEF-4 heading to hold them; `task.py sync` fixes the first two. Every byte outside the markers stays as written.

## Decisions

Status: `open` (no option chosen) → `proposed` (option recommended, awaiting confirmation) → `decided`; or `superseded` (with `superseded_by`) or `dropped` (the question no longer exists).

- Required: `title`, `question`; `decision` once decided or superseded; `why` once decided. Every other key appears only when it has content.
- Each option has `status`: `chosen`, `recommended`, `alternative` or `dropped`, plus `how`, `pros`, `cons`.
- When a decision changes course, write a new one with `supersedes`, and set the old one `superseded` with `superseded_by`. The old file stays.
- A finding that is not a choice becomes a context fact, and the decision becomes `dropped`.
- `discuss_with` names who must confirm: a person, a team, another task's slug, or `me` for a self-check. The agenda in `status.py` groups by it.
- `needs_code: false` marks a decision that changes no code (e.g. "keep production behaviour").
- `pr_note` holds the text the PR must carry because of this decision, in English and ready to paste. It disappears from the PR when the decision leaves the tree.
- A decision that only an experiment can settle gets a spike (see Spikes). It stays `open` or `proposed` (the working hypothesis) until the spike `passed`; `status.py` fails a `decided` decision whose spike has not passed. Its `why` then cites the spike and its evidence.

## Validations

Status `pending` → `passed` or `failed`, with `date` and `evidence`; or `dropped` when what it proved left the task. Every requirement has at least one validation; a validation may prove several. `depends_on` names features or other tasks it waits for.

### Spikes

A spike is a validation with `decides: [D-nn]`: an experiment, usually on a real environment, that picks between the options of a decision before any code is written for it.

- It proves no requirement: it never appears in `acs.yaml`, and a requirement still needs a validation of the delivered code.
- `passed` means it answered the question (the answer goes into the decision); `failed` means it was inconclusive and blocks like `pending`. `dropped` when the question went away.
- It blocks the features that link its decisions, not the roadmap: `status.py --gate spec --feature F` fails while a decision of `F` (its roadmap `decisions:` or its `story.decisions`) waits for a spike. The roadmap may be approved with the spike still pending.
- `status.py` lists every spike not passed under **Spikes**, with the features it blocks, and marks its decisions in the agenda.

## Pending

One entry per action with someone else. `with` names who; `refs` the ids behind it. Closing sets `status: done` (or `dropped`) and `closed`. A comment posted on an issue or ticket records its link in `link`.

## Journal

Every relevant change adds a note at the end (`task.py journal` picks the next `J-nnn` and the date): code read, decision created or changed, validation run, pending posted, reorganization. Old notes stay as written; a fix is a new note with `type: correction`.

## Repos

Each entry of `repos:` in the README header names a repo the work changes:

```yaml
repos:
  - name: ponto-api
    origin: ~/projects/ponto-api           # the main checkout
    worktree: repos/ponto-api              # relative to the task folder; null when none
    branch: feat/ponto-export-csv
```

A `/flow` feature names its repo in `repo:`, and its `flow.py --root` is that repo's worktree (or `origin` when `worktree` is null).

## Versioning

The home is one git repository; task folders have none of their own. Each change that leaves `status.py` without failures is committed there, with a conventional title naming the task and the ids, e.g. `docs(ponto-export-csv): decide D-07 PR lock`.
