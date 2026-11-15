---
name: task
description: Drive a piece of work from its acceptance criteria to a draft PR, with decisions in rounds, a brief, a /flow roadmap and review, all kept in a versioned task folder. /task <slug> [decide|consolidate|plan|spike|review|pr|finish|status]
disable-model-invocation: true
---

# task

```
start ──► decide ──► consolidate ──► plan (/flow) ──► build (/flow) ──► review ──► pr ──► finish
            ▲______________ decide is open at every step _____________________________|
                                                 └─ spike: runs before the SPEC of a feature whose decision waits on it
```

`<skill-dir>` is the folder holding this file. The task folder format (files, ids, the decision tree, status rules) is in `<skill-dir>/reference/format.md`: read it before the first write in a session. Templates are in `<skill-dir>/templates/`. Never type an id, a date or a status into a YAML by hand: `python3 <skill-dir>/scripts/task.py <task> <command>` (needs PyYAML) writes them and runs the `status.py` checks after each change (exit 1 on a failure). `python3 <skill-dir>/scripts/status.py <task>` reads and checks; `--find <id>` prints where an id is defined.

Write every file in English. Talk to the user in the language they use.

The `.md` files (context, `brief.md`, the specs) are for the user to read: where a shape, a flow or a change is the point, show it with the visuals in `~/.claude/skills/flow/reference/visuals.md` (call tree, file tree, `diff`, Mermaid) instead of describing it.

## Writing the files

| To | Run |
|---|---|
| add a journal note | `task.py <task> journal --type T --text X [--refs D-01,V-02]` |
| ask a decision | `task.py <task> new decision <slug> --title T --question Q (--born-from D-01 \| --requirement AC-1.1) [--discuss-with who]` |
| record an answer | `task.py <task> decide D-nn --decision X --why Y [--proposed] [--pr-note N]` |
| change course | `task.py <task> new decision ...`, then `task.py <task> supersede D-old D-new` |
| write a validation or spike | `task.py <task> new validation <slug> --title T --how H --expected E [--where W] [--decides D-nn]` |
| record a run | `task.py <task> validate V-nn --status passed\|failed\|dropped --evidence E [--attach file]` |
| open or close a pending item | `task.py <task> new pending --with who --action A [--refs ...]`, `task.py <task> close P-n [--link URL]` |
| stamp the brief | `task.py <task> consolidate` |
| write the statuses of requirements, items and the roadmap | `task.py <task> sync` |

Statuses are never typed: `acs.yaml` (requirements, items) and `roadmap.yaml` (features, milestones) get theirs from `task.py <task> sync`, which every `task.py` command also runs. After a `/flow` command (a task `verifying`, a check `pass`), run `sync` so the requirements follow. The state machine of each entity is in `format.md`, Status.

By hand stay the prose and structure the scripts cannot know: `README.md`, `acs.yaml` (the split into requirements, confirmed with the user), `context/`, the free text of options, consequences and open points inside a decision, and `brief.md` sections. Edit them, then run `status.py`.

## Commands

| Command | Does |
|---|---|
| `/task <slug>` | start the task, or resume it at the step its state shows |
| `decide [topic]` | open a round of decisions, at any step |
| `consolidate [--publish]` | write `brief.md`; `--publish` also shares it as a page |
| `plan` | build the roadmap and the first feature with `/flow` |
| `spike [V-nn]` | run a spike and settle the decision it names |
| `review` | close the story's checks and the `/flow` review |
| `pr` | compose and open the draft PR |
| `finish` | after the merge, remove the worktrees and local branches |
| `status` | print `status.py` and say what step comes next |

## Home and task folder

`<skill-dir>/config.yaml` holds `home` (the central folder, e.g. `~/projects/home`). When it is missing, ask for it and write it. The home is one git repository with its own `CLAUDE.md`; read it at the start of a session. When the folder does not exist yet, propose creating it and, on a yes: `git init`, a `CLAUDE.md` whose tasks line names `format.md`, `status.py` for status and `--find` for ids, with this skill's real path, and a `.gitignore` with `tasks/*/repos/` and `tasks/*/*/repos/` so the worktrees stay out of the home's history.

Every task lives in `<home>/tasks/<main-repo>/<YYYY-MM-DD-HHMM>-<slug>/` (`tasks/ponto-api/2026-11-15-1430-export-csv/`), written `<task>` below:

- **Main repo**: every task has exactly one, the repo that holds most of the change (`home` when the work is docs or catalog). Its name is the first folder level, so `tasks/<repo>/` lists that repo's tasks.
- **Date and time**: the moment `start` created the folder, local time, fixed from then on. The slug is kebab-case (`export-csv`); the branch name keeps the plain slug, without the date.
- `/task <slug>` finds its folder with `ls -d <home>/tasks/*/*-<slug>`. Old tasks (`tasks/<slug>/`, no `main` in the README) keep working; `status.py` only warns about them.

## Where to open Claude

- **In the home**, naming the task (`/task <slug>`): for decide, consolidate, plan and review, or to see every task. Read each repo's `AGENTS.md` / `CLAUDE.md` explicitly: they are not loaded up front from here, and the repo's `.claude/` settings and hooks do not apply.
- **In a worktree**, for the build when the repo's hooks and settings matter: `cd <task>/repos/<repo> && claude --add-dir ../..` (or `/add-dir ../..` mid-session). The home's `CLAUDE.md` loads on its own from the parent folders; `--add-dir` lets you edit the task folder.

Either way `/task <slug>` resumes the same way, and task-folder commits go to the home with `git -C <home>`.

## Ground rules

- **Facts are looked up, decisions are asked, unknowns are spiked.** Read the code, the base text and the docs yourself (sub-agents for broad reads) and write what you learn into `context/`. Put to the user only the choices that are theirs. When neither the facts nor the user can pick an option without trying it, propose a spike.
- **Outbound needs a yes.** A comment on an issue or ticket, a push, a PR and removing a worktree each wait for the user to approve the exact action in this conversation.
- **Ids stay in the task folder.** Code, code comments, commits and the PR body explain the reason in words, without `D-nn`, `NOW-n` or other task ids.
- **Project conventions first.** Commits, branch names, the PR title and the PR body follow what the repo documents (`CONTRIBUTING.md`, its `AGENTS.md` / `CLAUDE.md`, a PR template under `.github/` or `docs/`). For each topic the repo leaves undocumented, use `<skill-dir>/fallback/contributing.md`, and `<skill-dir>/fallback/pull_request_template.md` when it has no PR template. Say in one line which fallback you used.
- **Every change is versioned.** After each change: `task.py journal` (each `task.py` command already runs the `status.py` checks; after a hand edit run `status.py`), then commit the task folder in the home repo (`git -C <home> add <task> && git -C <home> commit`) with a conventional title naming the task and the ids (`docs(ponto-export-csv): decide D-07 PR lock`).

## start

Runs when `/task <slug>` finds no task folder.

1. **Read the base.** Ask whether there is a base text: an issue, a ticket pasted or linked, a note, a draft. Read it whole, comments included (they often carry what the description lacks). Then invoke the `grilling` skill on it until the problem, who it serves, what stays out, and the outcomes that make it done are settled. When the base text has acceptance criteria, they are the outcomes; grill the gaps.
2. **Repos.** Ask which repos the work changes, proposing the most likely ones, and which is the main one. Create `<task>` now with the current date and time (`date +%Y-%m-%d-%H%M`) under the main repo's folder. For each repo, create a worktree inside the task folder: `git -C <origin> worktree add <task>/repos/<repo> -b <branch>`, with the branch named by the repo's convention (fallback `<type>/<slug>`). For a repo whose checkout is large (hundreds of MB), propose `git sparse-checkout set <dirs>` on the worktree, with only the folders the work touches. Read each repo's `AGENTS.md` / `CLAUDE.md` now: they do not load on their own from here.
3. **Folder.** Create it from the templates: `README.md` (the base text verbatim, with its link; the problem, who it serves, what stays out), empty `pending.yaml` and `journal.yaml` (`[]`), then `task.py journal` for J-001. Fill `repos:` in the README header, with `main: true` on the main repo.
4. **Facts.** Read the code the work touches and write `context/now.md` with code `NOW`: facts only, each section with an id, the current flow or structure drawn where it is the point (call tree, file tree, Mermaid).
5. **Items.** Propose, in one message, the split of every outcome from step 1 (written as `AC-n`; anything beyond the base text as `X-n`) into requirements, with a first root decision for each. Write `acs.yaml`, the root decisions (`open` or `proposed`) and their validations only after the user confirms the split, then run `task.py sync` to fill the statuses.
6. Run `status.py`, commit, and continue with **decide**.

Done when `status.py` has no failures and every requirement has a root decision and a validation.

## Resume

1. When the base text is a link (an issue, a ticket), ask whether it changed or gained comments since the last session; write what changed into `context/`, decisions or `pending.yaml`, and journal it.
2. Run `status.py`, read the last journal notes and `git -C <home> log --oneline -5 -- <task>`, then go to the first step whose bar is unmet:

| State | Step |
|---|---|
| a decision `open` or `proposed` in some tree, not awaiting a spike | decide |
| no `brief.md`, or decisions changed after its `date` | consolidate |
| no `.specs/roadmap.yaml` | plan |
| a spike under **Spikes** blocks the next feature to spec or build | spike |
| a feature not `done` | build, through `/flow` |
| an item not `concluded` without a `pr_note` | review |
| no PR yet | pr |
| PR merged | finish |

Say in one line where the task stands and which step you are taking.

## decide

Work the decision tree in **rounds**. The **frontier** is every decision whose prerequisites are settled. A round asks the whole frontier at once, then waits:

```
❓ **Q1 - D-07 <title>**: <the question, its options, the facts that matter (with context ids)>

➡️ <recommended answer>
```

Word each question so "yes" accepts the recommendation. A question whose answer depends on another still open in this round waits for the next round.

After each answer, in the same turn:

- write it with `task.py decide D-nn` (`--proposed` when someone in `discuss_with` other than the user must confirm; `--pr-note` when the PR must mention it); add the chosen and dropped `options` by hand;
- create the child decisions the answer opens with `task.py new decision --born-from`, and the facts it needed in `context/`;
- add the actions with other people with `task.py new pending`;
- `task.py journal`, commit.

When a question needs an experiment to answer (a combination nobody has tried, a behaviour only a real environment shows), propose a spike in the round instead of a choice: `➡️ keep <option> as the working hypothesis; spike V-nn on <where> settles it`. On a yes, set the decision `proposed` with the hypothesis in `decision`, and write the spike from `<skill-dir>/templates/validation.yaml` with `decides: [D-nn]`, the paths to compare in `how` and what to record. Its children wait until the spike settles it.

A new question raised at any step is a new decision: place it in the tree (requirement root, or `born_from`) and ask it in the next round. When a decision changes course, supersede it (`format.md`, Decisions).

Done when the frontier is empty, or every remaining decision waits on someone in `discuss_with` other than the user (each with a pending item) or on a spike.

## consolidate

Write `brief.md` from the template: **Today** from `context/`, **Target** per item and where it departs from the AC text, **Path** from the decided tree, **Open items** from the agenda in `status.py`. Cite ids; restate no decision in full. Target shows the change as a `diff` over today's shape when the change is structural; Path draws the order of the work when it is not linear. Run `task.py consolidate` to stamp `date`, then `task.py journal`, commit.

With `--publish`, the reader is someone outside the task: write a version without task ids (each id replaced by what it names) and publish it the way the user picks: Claude Docs or an Artifact. Record the link with `task.py journal`.

## plan

1. Run `status.py --gate plan`. Open decisions block: go back to **decide**. Proposed decisions pass, and appear in BRIEF-4.
2. Read `~/.claude/skills/flow/SKILL.md` and follow its ROADMAP and SPEC steps with the specs inside the task folder (`spec.md` and `feature.yaml` per feature): every `flow.py` call takes `--root <worktree> --specs <task>/.specs`.
3. Milestones come from BRIEF-3 Path. A feature's `spec.md` cites the decisions and context it builds on (`see D-23`) instead of restating them. Create each feature with `flow.py new <id> --title T --size S|M|L --roadmap F1.1 --repo <repo> --decisions D-23,D-24 --validations V-01,V-08`, which writes its `feature.yaml` with a `repo:` (a name from the README's `repos:`) and a `story:` block naming the decisions it implements and the validations that prove it, shaped like:

   ```yaml
   repo: ponto-api
   story:
     decisions: [D-23, D-24]
     validations: [V-01, V-08]
   ```

   A roadmap feature whose decision waits on a spike names it in `decisions:` in `roadmap.yaml`, so the gate holds it before its spec exists. Its goal states the outcome; the path comes from the spike.

4. Before the SPEC of each feature, run `status.py --gate spec --feature <id>`. A failure on a spike sends the task to **spike**; other features may be spec'd and built meanwhile.
5. Validations that need a real environment (a VM, a clone, a sibling story) stay in `validations/` and are not `/flow` tasks.

Build each feature with `/flow` BUILD, with the same `--root` and `--specs`, after `status.py --gate spec --feature <id>` passes. Run `task.py journal` for each feature that reaches `done`, and commit the task folder.

## spike

Runs when a spike blocks the next feature, or on `spike [V-nn]`.

1. Pick the spike from **Spikes** in `status.py`. Say where it runs and what it needs (environment, snapshot, files). Ask before anything that touches a shared environment.
2. When the user can run it here, run its `how` step by step and record the output. When it needs someone else or an environment out of reach, add a `P-n` to `pending.yaml` with the steps, and work on features the spike does not block.
3. Record it with `task.py validate V-nn --status passed|failed --evidence E --attach f`. `passed` when it answered the question, `failed` when it was inconclusive (say what to change and run again).
4. Settle each decision in `decides` with `task.py decide` (`--why` citing the spike), or `supersede` it when the evidence points elsewhere. Create the child decisions the answer opens, and update the feature's goal in `roadmap.yaml` when the path changed.
5. `task.py journal`, commit. Continue with **decide** when children opened, else with the SPEC of the unblocked feature.

## review

1. Run every pending validation the user can run now and record each with `task.py validate`. Ask before anything that touches a shared environment.
2. Run `status.py --gate pr`. Each item not `concluded` gets a `pr_note` the user agrees to (why it stays open, where it will be proven), or goes back to the step it needs.
3. Run `/flow` CLOSE on every feature not yet `done`: its checks prove the code; the validations here prove the story.

Done when `status.py --gate pr` has no failures.

## pr

1. Collect the material: `status.py --pr-notes`, BRIEF-3 Path, the repo's PR template (`.github/pull_request_template.md` or the one its docs name; fallback `<skill-dir>/fallback/pull_request_template.md`) and its title and branch rules (fallback `<skill-dir>/fallback/contributing.md`).
2. Compose the title and the body on that template, in English, with no task ids. Show both to the user and wait for approval.
3. After approval: push the branch from the worktree and run `gh pr create --draft` with that body. Add the PR link with `task.py journal`; when the base text is an issue or ticket, offer a comment with the link there.

## finish

After the PR is merged: for each repo in the README, offer `git -C <origin> worktree remove <task>/repos/<repo>` and `git -C <origin> branch -d <branch>`. Clear `worktree` in the README header, journal, commit. The task folder stays in the home.
