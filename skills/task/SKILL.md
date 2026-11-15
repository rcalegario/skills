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

`<skill-dir>` is the folder holding this file. The task folder format (files, ids, the decision tree, status rules) is in `<skill-dir>/reference/format.md`: read it before the first write in a session. Templates are in `<skill-dir>/templates/`. Run `python <skill-dir>/scripts/status.py <task>` (needs PyYAML) after every change to the task folder.

Write every file in English. Talk to the user in the language they use.

The `.md` files (context, `brief.md`, the specs) are for the user to read: where a shape, a flow or a change is the point, show it with the visuals in `~/.claude/skills/flow/reference/visuals.md` (call tree, file tree, `diff`, Mermaid) instead of describing it.

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

`<skill-dir>/config.yaml` holds `home` (the central folder, e.g. `~/projects/home`). When it is missing, ask for it and write it. The home is one git repository with its own `CLAUDE.md`; read it at the start of a session. When the folder does not exist yet, propose creating it and, on a yes: `git init`, a `CLAUDE.md` saying the home holds task folders that follow this skill, and a `.gitignore` with `tasks/*/repos/` so the worktrees stay out of the home's history.

Every task lives in `<home>/tasks/<slug>/`, the slug in kebab-case (`ponto-export-csv`).

## Where to open Claude

- **In the home**, naming the task (`/task <slug>`): for decide, consolidate, plan and review, or to see every task. Read each repo's `AGENTS.md` / `CLAUDE.md` explicitly: they are not loaded up front from here, and the repo's `.claude/` settings and hooks do not apply.
- **In a worktree**, for the build when the repo's hooks and settings matter: `cd <home>/tasks/<slug>/repos/<repo> && claude --add-dir ../..` (or `/add-dir ../..` mid-session). The `CLAUDE.md` of the task and of the home load on their own from the parent folders; `--add-dir` lets you edit the task folder.

Either way `/task <slug>` resumes the same way, and task-folder commits go to the home with `git -C <home>`.

## Ground rules

- **Facts are looked up, decisions are asked, unknowns are spiked.** Read the code, the base text and the docs yourself (sub-agents for broad reads) and write what you learn into `context/`. Put to the user only the choices that are theirs. When neither the facts nor the user can pick an option without trying it, propose a spike.
- **Outbound needs a yes.** A comment on an issue or ticket, a push, a PR and removing a worktree each wait for the user to approve the exact action in this conversation.
- **Ids stay in the task folder.** Code, code comments, commits and the PR body explain the reason in words, without `D-nn`, `NOW-n` or other task ids.
- **Project conventions first.** Commits, branch names, the PR title and the PR body follow what the repo documents (`CONTRIBUTING.md`, its `AGENTS.md` / `CLAUDE.md`, a PR template under `.github/` or `docs/`). For each topic the repo leaves undocumented, use `<skill-dir>/fallback/contributing.md`, and `<skill-dir>/fallback/pull_request_template.md` when it has no PR template. Say in one line which fallback you used.
- **Every change is versioned.** After each change: journal note, `status.py` with no failures, then commit the task folder in the home repo (`git -C <home> add <task> && git -C <home> commit`) with a conventional title naming the task and the ids (`docs(ponto-export-csv): decide D-07 PR lock`).

## start

Runs when `/task <slug>` finds no task folder.

1. **Read the base.** Ask whether there is a base text: an issue, a ticket pasted or linked, a note, a draft. Read it whole, comments included (they often carry what the description lacks). Then invoke the `grilling` skill on it until the problem, who it serves, what stays out, and the outcomes that make it done are settled. When the base text has acceptance criteria, they are the outcomes; grill the gaps.
2. **Repos.** Ask which repos the work changes, proposing the most likely ones. For each, create a worktree inside the task folder: `git -C <origin> worktree add <task>/repos/<repo> -b <branch>`, with the branch named by the repo's convention (fallback `<type>/<slug>`). For a repo whose checkout is large (hundreds of MB), propose `git sparse-checkout set <dirs>` on the worktree, with only the folders the work touches. Read each repo's `AGENTS.md` / `CLAUDE.md` now: they do not load on their own from here.
3. **Folder.** Create it from the templates: `README.md` (the base text verbatim, with its link; the problem, who it serves, what stays out), `CLAUDE.md`, empty `pending.yaml`, `journal.yaml` with J-001. Fill `repos:` in the README header.
4. **Facts.** Read the code the work touches and write `context/now.md` with code `NOW`: facts only, each section with an id, the current flow or structure drawn where it is the point (call tree, file tree, Mermaid).
5. **Items.** Propose, in one message, the split of every outcome from step 1 (written as `AC-n`; anything beyond the base text as `X-n`) into requirements, with a first root decision for each. Write `acs.yaml`, the root decisions (`open` or `proposed`) and their validations only after the user confirms the split.
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

- write it into the decision: `decided` (or `proposed` when someone in `discuss_with` other than the user must confirm), `decision`, `why`, the chosen and dropped options, `pr_note` when the PR must mention it;
- create the child decisions the answer opens (`born_from`), and the facts it needed in `context/`;
- add the actions with other people to `pending.yaml`;
- journal, `status.py`, commit.

When a question needs an experiment to answer (a combination nobody has tried, a behaviour only a real environment shows), propose a spike in the round instead of a choice: `➡️ keep <option> as the working hypothesis; spike V-nn on <where> settles it`. On a yes, set the decision `proposed` with the hypothesis in `decision`, and write the spike from `<skill-dir>/templates/validation.yaml` with `decides: [D-nn]`, the paths to compare in `how` and what to record. Its children wait until the spike settles it.

A new question raised at any step is a new decision: place it in the tree (requirement root, or `born_from`) and ask it in the next round. When a decision changes course, supersede it (`format.md`, Decisions).

Done when the frontier is empty, or every remaining decision waits on someone in `discuss_with` other than the user (each with a pending item) or on a spike.

## consolidate

Write `brief.md` from the template: **Today** from `context/`, **Target** per item and where it departs from the AC text, **Path** from the decided tree, **Open items** from the agenda in `status.py`. Cite ids; restate no decision in full. Target shows the change as a `diff` over today's shape when the change is structural; Path draws the order of the work when it is not linear. Set `date` to today. Journal, `status.py`, commit.

With `--publish`, the reader is someone outside the task: write a version without task ids (each id replaced by what it names) and publish it the way the user picks: Claude Docs or an Artifact. Record the link in the journal.

## plan

1. Run `status.py --gate plan`. Open decisions block: go back to **decide**. Proposed decisions pass, and appear in BRIEF-4.
2. Read `~/.claude/skills/flow/SKILL.md` and follow its ROADMAP and SPEC steps with the specs inside the task folder (`spec.md` and `feature.yaml` per feature): every `flow.py` call takes `--root <worktree> --specs <task>/.specs`.
3. Milestones come from BRIEF-3 Path. A feature's `spec.md` cites the decisions and context it builds on (`see D-23`) instead of restating them. Each `feature.yaml` gets a `repo:` naming the repo it changes (a name from the README's `repos:`), and a `story:` block naming the decisions it implements and the validations that prove it:

   ```yaml
   repo: ponto-api
   story:
     decisions: [D-23, D-24]
     validations: [V-01, V-08]
   ```

   A roadmap feature whose decision waits on a spike names it in `decisions:` in `roadmap.yaml`, so the gate holds it before its spec exists. Its goal states the outcome; the path comes from the spike.

4. Before the SPEC of each feature, run `status.py --gate spec --feature <id>`. A failure on a spike sends the task to **spike**; other features may be spec'd and built meanwhile.
5. Validations that need a real environment (a VM, a clone, a sibling story) stay in `validations/` and are not `/flow` tasks.

Build each feature with `/flow` BUILD, with the same `--root` and `--specs`, after `status.py --gate spec --feature <id>` passes. Journal each feature that reaches `done`, and commit the task folder.

## spike

Runs when a spike blocks the next feature, or on `spike [V-nn]`.

1. Pick the spike from **Spikes** in `status.py`. Say where it runs and what it needs (environment, snapshot, files). Ask before anything that touches a shared environment.
2. When the user can run it here, run its `how` step by step and record the output. When it needs someone else or an environment out of reach, add a `P-n` to `pending.yaml` with the steps, and work on features the spike does not block.
3. Fill `date`, `evidence` and `attachments`. `passed` when it answered the question, `failed` when it was inconclusive (say what to change and run again).
4. Settle each decision in `decides`: `decided` with the option the evidence picked and `why` citing the spike, or supersede it when the evidence points elsewhere. Create the child decisions the answer opens, and update the feature's goal in `roadmap.yaml` when the path changed.
5. Journal, `status.py`, commit. Continue with **decide** when children opened, else with the SPEC of the unblocked feature.

## review

1. Run every pending validation the user can run now, filling `date`, `evidence` and `attachments`. Ask before anything that touches a shared environment.
2. Run `status.py --gate pr`. Each item not `concluded` gets a `pr_note` the user agrees to (why it stays open, where it will be proven), or goes back to the step it needs.
3. Run `/flow` CLOSE on every feature not yet `done`: its checks prove the code; the validations here prove the story.

Done when `status.py --gate pr` has no failures.

## pr

1. Collect the material: `status.py --pr-notes`, BRIEF-3 Path, the repo's PR template (`.github/pull_request_template.md` or the one its docs name; fallback `<skill-dir>/fallback/pull_request_template.md`) and its title and branch rules (fallback `<skill-dir>/fallback/contributing.md`).
2. Compose the title and the body on that template, in English, with no task ids. Show both to the user and wait for approval.
3. After approval: push the branch from the worktree and run `gh pr create --draft` with that body. Add the PR link to the journal; when the base text is an issue or ticket, offer a comment with the link there.

## finish

After the PR is merged: for each repo in the README, offer `git -C <origin> worktree remove <task>/repos/<repo>` and `git -C <origin> branch -d <branch>`. Clear `worktree` in the README header, journal, commit. The task folder stays in the home.
