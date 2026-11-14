---
name: idea-triage
description: Keeps the catalog of projects under ~/Projects. Use to write or update a project's ficha (project.yaml), or to fill the catalog folder by folder. /idea-triage ficha [repo]
---

# idea-triage

`<home>` is `realpath <skill-dir>/../..`: this skill lives in `<home>/skills/idea-triage`, reached through a symlink. The catalog is `<home>/catalog/`: the schema `project.schema.json` (the only source of fields, enums and patterns), the checker `catalog.py`, run as `uv run <home>/catalog/catalog.py validate|index`, and the generated `index.yaml`.

Talk to the user in their language. Free-text ficha values (`question`, `features`, `entities`, `notes`) are in Portuguese; ids and enum values stay as the schema has them.

## Modes

| Command | Does |
|---|---|
| `ficha [repo]` | propose, validate and write a project's ficha |

## ficha [repo]

### 1. Target

- A path names the project folder; a bare name means `~/Projects/<name>`.
- Omitted, inside a project under `~/Projects`: that project's top-level folder.
- Omitted, inside `<home>`: the first folder that `catalog.py validate` reports as `<folder>: no project.yaml`. When it reports none, tell the user the catalog covers every folder, and stop.

The ficha's `id` is the folder name. It lives in `<folder>/project.yaml`, except for a folder that `<home>/CLAUDE.md` marks as not ours (no commits there): its ficha is `<home>/catalog/external/<id>.yaml`, and nothing is written in that folder.

### 2. Read

Read what the project already says about itself, then the code only where that leaves a field open:

- `CONTEXT.md`, `CLAUDE.md` / `AGENTS.md`, `README*`, and the project's line in `<home>/CLAUDE.md`;
- manifests and deploy files: `package.json`, `pyproject.toml`, `requirements.txt`, `appsscript.json` / `.clasp.json`, `pubspec.yaml`, `wrangler.toml`, `docker-compose*`, `Dockerfile`, `*.tf`, `supabase/`, `firebase.json`;
- `git log --oneline -15` and `git remote -v` (a remote outside the user's account means `fork` or `upstream`);
- the catalog: `<home>/catalog/index.yaml`, or every ficha when the index is missing, to find projects that answer the same question.

Done when every schema field has a source in what you read, or is marked as a guess for the user to settle.

### 3. Draft

Fill the ficha from the schema, field by field:

- `question`: the one question the project answers, as the user would ask it.
- `intent`: `ativo` when the user relies on it today, `experimento` when it was tried and paused, `arquivado` when dropped. Mark it a guess unless the docs say so.
- `shape`: `standalone` for every existing project (the central does not exist yet).
- `runs_on`: where it actually runs, from the deploy files, not where it could.
- `stack`: free keys (`api`, `front`, `db`, `worker`, `bot`, ...) with short values.
- `overlaps`: only ids already in the catalog. A project that overlaps but has no ficha yet goes into `notes` as `sobrepõe <id> (sem ficha ainda)`.
- Overlaps are symmetric. List the **reverse edits** the draft implies: each catalogued project in `overlaps` whose ficha lacks this id gains it, and each catalogued ficha whose `notes` say `sobrepõe <this id> (sem ficha ainda)` gains this id in `overlaps` and loses that note.

Start a root ficha with `# yaml-language-server: $schema=../home/catalog/project.schema.json`; an external one with `# yaml-language-server: $schema=../project.schema.json`.

When the project already has a ficha, start from it: keep every field the evidence still supports and change only what it contradicts or lacks.

### 4. Validate

Write the draft and each reverse edit to scratch files and run `uv run <home>/catalog/catalog.py validate --file <scratch>` on each. Fix and run again until each prints `1 fichas OK`. The user never sees a ficha that has not passed.

### 5. Propose

Show in chat:

- the ficha, whole when new, or as a diff against the current one;
- the reverse edits, as diffs, one per project;
- the guesses, each with what would settle it;
- that `validate` passed.

Ask for a yes, or for edits. Edits go back to step 4, and the new proposal is shown whole again. Nothing is written until the yes.

### 6. Write

On the yes:

1. Write the ficha and every reverse edit to their files.
2. Commit each project folder that got a file and has git, one commit per repo, local only:
   - copy the format of the repo's `git log -n 10 --oneline` (prefix, language); the subject says the ficha puts the project in the home catalog;
   - commit the ficha alone, even when other work is staged: `git -C <folder> add project.yaml && git -C <folder> commit -m "<message>" -- project.yaml`.
   A folder without git just keeps the file.
3. Run `uv run <home>/catalog/catalog.py index`, and commit `catalog/index.yaml` in the home together with any external ficha written in step 1, in the home's commit format.

Done when `index.yaml` lists the project and `git status` shows no uncommitted ficha in any repo this run touched. Report the commits made, and the next folder without a ficha when the target came from `validate`.
