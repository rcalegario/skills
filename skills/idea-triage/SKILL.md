---
name: idea-triage
description: Keeps the catalog of projects under ~/Projects and triages new ideas against it. Use to write or update a project's ficha (project.yaml), to fill the catalog folder by folder, or to triage a new idea before any code is written.
argument-hint: ficha [repo] | triage [idea]
---

# idea-triage

`<home>` is `realpath <skill-dir>/../..`: this skill lives in `<home>/skills/idea-triage`, reached through a symlink. The catalog is `<home>/catalog/`: the schema `project.schema.json` (the only source of fields, enums and patterns), the checker `catalog.py`, run as `uv run <home>/catalog/catalog.py validate|index`, and the generated `index.yaml`.

Free-text ficha values (`question`, `features`, `notes`) are in Portuguese; `entities` are English nouns, as in the example in `<home>/docs/estrutura-projetos.md`; ids and enum values stay as the schema has them.

## Modes

| Command | Does |
|---|---|
| `ficha [repo]` | propose, validate and write a project's ficha |
| `triage [idea]` | decide where a new idea goes: already exists, feature of a project, route in the central, or standalone |

## ficha [repo]

### 1. Target

- A path names the project folder; a bare name means `~/Projects/<name>`.
- Omitted, inside `<home>`: the first folder that `catalog.py validate` reports as `<folder>: no project.yaml`. When it reports none, tell the user the catalog covers every folder, and stop.
- Omitted, inside any other project under `~/Projects`: that project's top-level folder.

The ficha's `id` is the folder name. It lives in `<folder>/project.yaml`, except for a folder that `<home>/CLAUDE.md` marks as not ours (no commits there): its ficha is `<home>/catalog/external/<id>.yaml`, and nothing is written in that folder.

In a folder with git, find the **work branch**, where the user's own commits land: the branch the repo's docs or workflows name for that (a fork whose `main` mirrors upstream, like securo, works on `custom`), else the default branch (`git symbolic-ref --short refs/remotes/origin/HEAD` without `origin/`, else `main`, else `master`). Compare it with `git branch --show-current`. When they differ, the ficha still lives on the work branch: you read the project from the checkout (its newest work) and write the ficha through a temporary worktree of the work branch (step 6).

Done when you have one folder, its id, the path its ficha goes to, and the branch it is committed on.

### 2. Read

Read what the project already says about itself, then the code only where that leaves a field open:

- `CONTEXT.md`, `CLAUDE.md` / `AGENTS.md`, `README*`, and the project's line in `<home>/CLAUDE.md`;
- manifests and deploy files: `package.json`, `pyproject.toml`, `requirements.txt`, `appsscript.json` / `.clasp.json`, `pubspec.yaml`, `wrangler.toml`, `docker-compose*`, `Dockerfile`, `*.tf`, `supabase/`, `firebase.json`;
- `git log --oneline -15` and `git remote -v`;
- the catalog: `<home>/catalog/index.yaml`, or every ficha when the index is missing, to find projects that answer the same question;
- the current ficha, when there is one; on another branch, `git -C <folder> show <work-branch>:project.yaml`.

Done when every schema field has a source in what you read, or is marked as a guess for the user to settle.

### 3. Draft

When the project already has a ficha, start from it: keep every field the evidence still supports and change only what it contradicts or lacks.

The schema gives each field's allowed values; these are the conventions it does not hold:

- `question`: the one question the project answers, as the user would ask it.
- `intent`: what the user does with it today; a guess unless the docs say so.
- `domain`: reuse a domain already in the catalog when one fits.
- `shape`: `standalone` for every existing project, since the central (the shared monorepo in `<home>/docs/estrutura-projetos.md`) does not exist yet.
- `origin`: from the project's line in `<home>/CLAUDE.md` first, then `git remote -v`: "fork of" means `fork`, "not ours" or a third-party remote means `upstream`; an own project leaves it out.
- `runs_on`: where it runs today, from the deploy files.
- `overlaps`: only ids already in the catalog. A project that overlaps but has no ficha yet goes into `notes` as `sobrepõe <id> (sem ficha ainda)`.

Overlaps are symmetric. List the **reverse edits** the draft implies: each catalogued project in `overlaps` whose ficha lacks this id gains it, and each catalogued ficha whose `notes` say `sobrepõe <this id> (sem ficha ainda)` gains this id in `overlaps` and loses that note.

Start a root ficha with `# yaml-language-server: $schema=../home/catalog/project.schema.json`; an external one with `# yaml-language-server: $schema=../project.schema.json`.

Done when every required field is filled or marked a guess, and every reverse edit is listed.

### 4. Validate

Write the draft and each reverse edit to scratch files and validate them in one call, so each one's id is known to the others: `uv run <home>/catalog/catalog.py validate --file <draft> --file <reverse-1> ...`. Fix and run again until it prints `<n> fichas OK`. Only fichas that passed reach the user.

### 5. Propose

Show in chat:

- the ficha, whole when new, or as a diff against the current one;
- the reverse edits, as diffs, one per project;
- the guesses, each with what would settle it;
- that `validate` passed.

Ask for a yes, or for edits. Edits go back to step 4, and the new proposal is shown the same way (whole when new, a diff when updating). Files are written only after the yes.

### 6. Write

On the yes:

1. Write the ficha and every reverse edit to their files (for a repo on another branch, in step 2's worktree).
2. Commit each project folder (not the home) that got a file and has git, one commit per repo, local only, on its work branch. When the checkout is another branch, write and commit in `git -C <folder> worktree add <scratch>/<id>-work <work-branch>`, then `git -C <folder> worktree remove` it; the checkout and its pending work stay untouched.
   - copy the format of the repo's `git log -n 10 --oneline` (prefix, language); the subject says the ficha puts the project in the home catalog;
   - commit the ficha alone, even when other work is staged: `git -C <folder> add project.yaml && git -C <folder> commit -m "<message>" -- project.yaml`.
   A folder without git just keeps the file.
3. Run `uv run <home>/catalog/catalog.py index`, and commit in the home, in its commit format, only `catalog/index.yaml` and the external fichas written in step 1: `git -C <home> add <paths> && git -C <home> commit -m "<message>" -- <paths>`. When `index` refuses because some ficha has errors, show its errors and stop: the project commits stand, and the index waits until those fichas are fixed.

Done when `index.yaml` lists the project and `git status` shows no uncommitted ficha in any repo this run touched. Report the commits made, and the next folder without a ficha when the target came from `validate`.

## triage [idea]

The funnel and the route rule live in `<home>/docs/estrutura-projetos.md` (Triagem e catálogo): read that section before step 3. The **verdict** is one of:

- `exists`: a catalogued project or a GitHub repo already answers the idea;
- `feature`: the idea fits a catalogued project, which becomes the target;
- `route`: a module in the central, the default for anything new;
- `standalone`: its own project, only when one of the doc's criteria holds (another client, outside users or own domain, heavy or continuous background, another stack, data or load that would hurt the other modules); "looks big" is not one.

### 1. Idea and earlier records

Take the idea from the argument, or ask for it in one sentence. Read every record in `<home>/docs/triage/` (fields `idea`, `verdict`, `target`, `why`). When one is about the same idea, show it first and ask whether to triage again; on a no, stop.

Done when you hold the idea in one sentence and either no record covers it or the user chose to triage again.

### 2. Candidates

- **Catalog:** read `<home>/catalog/index.yaml`. A candidate is a project whose `question`, `features` or `entities` answer part of the idea; `domain` alone only narrows the search. List each one with the field that matched and how far it covers the idea. Run `catalog.py validate` too and name the folders without a ficha whose line in `<home>/CLAUDE.md` touches the idea: they are blind spots, not candidates.
- **GitHub:** `gh search repos <2-4 English keywords> --sort stars --limit 5 --json fullName,description,stargazersCount,pushedAt,url`. Phrase searches match too little: when one comes back empty, drop a keyword and run it again. Keep at most 5 repos that actually do the idea, each with stars and last push.

Show both lists before the first question.

Done when every catalogued project has been weighed, and the GitHub list holds the repos found or says what was searched and came back empty.

### 3. Quick round

Ask one question per message, each with your recommended answer so a "yes" accepts it, 10 questions at most. Ask only what the user decides: what the idea is for and who uses it, whether a candidate already does enough, which project it belongs to, which standalone criterion holds. Facts in the code, the fichas or the docs you look up yourself. Walk the funnel in order: exists, then feature, then route versus standalone; stop asking as soon as the verdict is clear.

Done when one verdict follows from the answers, with its target (the project or repo for `exists` and `feature`) and the reason in one or two sentences.
