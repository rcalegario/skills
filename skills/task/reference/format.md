# Task folder format

A task folder records the facts, decisions, plan and proof behind one piece of work. It lives in `<home>/tasks/<slug>/`. Templates for every file are in `../templates/`. Write in English; code, paths and names in backticks; dates `YYYY-MM-DD`; titles in YAML between quotes.

## Files

| Path | Format | Holds |
|---|---|---|
| `README.md` | md + YAML header | the base text verbatim (with its link), the problem, who it serves, what stays out. Header: `id`, `title`, `link`, `repos:` |
| `acs.yaml` | YAML | outcomes (`AC-n`) and extras (`X-n`), each split into requirements |
| `context/*.md` | md + YAML header | facts only, each file with its `code` and the date it was read |
| `context/archive/` | any | frozen old material, read only, never checked |
| `decisions/D-nn-<slug>.yaml` | YAML | one question per file |
| `validations/V-nn-<slug>.yaml` | YAML | one concrete check, with evidence: a proof of a requirement, or a spike (`decides`) that settles a decision |
| `validations/evidence/` | any | logs and screenshots a validation lists in `attachments` |
| `pending.yaml` | YAML | actions with other people or tasks (`P-n`) |
| `journal.yaml` | YAML | events in date order (`J-nnn`) |
| `brief.md` | md + YAML header | the consolidated view: today, target, path, open items |
| `.specs/` | `/flow` | `roadmap.yaml` and `features/<id>/` with `spec.md` and `feature.yaml` |
| `CLAUDE.md` | md | pointer to this file for any agent that opens the folder |
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
| `X-n` | item beyond the base text (nice to have), so scope growth stays visible | `acs.yaml` |
| `AC-n.m`, `X-n.m` | requirement inside an item | `acs.yaml` |
| `D-nn`, `V-nn`, `P-n`, `J-nnn` | decision, validation, pending item, journal note | their files |
| `<CODE>-n`, `<CODE>-n.m` | section of a context file or of `brief.md` | the heading itself |

- Each context file declares an upper-case `code` in its header, and each heading carries the id: `## NOW-7 Firewall today`, `### NOW-7.2 Docker bypasses ufw`.
- Ids are permanent: a new item takes the next free number; existing ones never move, even when the order looks odd.
- Cite by id in plain text: `see D-12`, `(NOW-7.2)`.
- Ids stay inside the task folder. Code, commits and the PR carry the reason in words, never the id.

## Requirements and the decision tree

- A requirement is one verifiable thing an item asks for, and points to **one** root decision. A decision may be the root of several requirements.
- A new question: **is it in the text of the AC?** It becomes a requirement. **Does it exist only because of a choice of ours?** It becomes a child decision, with `born_from` naming the decision that created it.
- `born_from` is strict: "this question exists because of that choice". Influence goes in the text.
- A context fact that threatens a decision becomes a child decision of it, not a new requirement. When the base text did not foresee the fact, say so in `consequences`.
- A requirement's tree is its root plus every active child, recursively. `superseded` and `dropped` decisions leave the tree. Every active decision sits in some tree; anything beyond the base text goes into an `X-n` item.
- The split of each item into requirements is confirmed with the user before it is written.

## Status

Computed by `status.py`, never written by hand. An item's status is the lowest of its requirements:

| Status | When |
|---|---|
| `discovery` | no decision, more than one, or no validation |
| `deciding` | some decision in the tree is not `decided` |
| `decided` | tree all `decided`; some decision with `needs_code` (default true) has no `/flow` feature, or one not `done` |
| `built` | every needed feature `done`; some validation has not `passed` |
| `concluded` | every validation of the requirement `passed` |

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

Every relevant change adds a note at the end, with the next `J-nnn`: code read, decision created or changed, validation run, pending posted, reorganization. Old notes stay as written; a fix is a new note with `type: correction`.

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
