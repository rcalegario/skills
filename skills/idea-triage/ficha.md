# ficha [repo]

## 1. Target

- A path names the project folder; a bare name means `~/Projects/<name>`.
- Omitted, inside `<home>`: the first folder that `catalog.py validate` reports as `<folder>: no project.yaml`. When it reports none, tell the user the catalog covers every folder, and stop.
- Omitted, inside any other project under `~/Projects`: that project's top-level folder.

The ficha's `id` is the folder name. It lives in `<folder>/project.yaml`, except for a folder that `<home>/CLAUDE.md` marks as not ours (no commits there): its ficha is `<home>/catalog/external/<id>.yaml`, and nothing is written in that folder.

In a folder with git, find the **work branch**, where the user's own commits land: the branch the repo's docs or workflows name for that (a fork whose `main` mirrors upstream, like securo, works on `custom`), else the default branch (`git symbolic-ref --short refs/remotes/origin/HEAD` without `origin/`, else `main`, else `master`). Compare it with `git branch --show-current`. When they differ, the ficha still lives on the work branch: you read the project from the checkout (its newest work) and write the ficha through a temporary worktree of the work branch (step 6).

Done when you have one folder, its id, the path its ficha goes to, and the branch it is committed on.

## 2. Read

Read what the project already says about itself, then the code only where that leaves a field open:

- `CONTEXT.md`, `CLAUDE.md` / `AGENTS.md`, `README*`, and the project's line in `<home>/CLAUDE.md`;
- manifests and deploy files: `package.json`, `pyproject.toml`, `requirements.txt`, `appsscript.json` / `.clasp.json`, `pubspec.yaml`, `wrangler.toml`, `docker-compose*`, `Dockerfile`, `*.tf`, `supabase/`, `firebase.json`;
- `git log --oneline -15` and `git remote -v`;
- the catalog: `<home>/catalog/index.yaml`, or every ficha when the index is missing, to find projects that answer the same question;
- the current ficha, when there is one; on another branch, `git -C <folder> show <work-branch>:project.yaml`.

Done when every schema field has a source in what you read, or is marked as a guess for the user to settle.

## 3. Draft

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

## 4. Validate

Write the draft and each reverse edit to scratch files and validate them in one call, so each one's id is known to the others: `uv run <home>/catalog/catalog.py validate --file <draft> --file <reverse-1> ...`. Fix and run again until it prints `<n> fichas OK`. Only fichas that passed reach the user.

## 5. Propose

Show in chat:

- the ficha, whole when new, or as a diff against the current one;
- the reverse edits, as diffs, one per project;
- the guesses, each with what would settle it;
- that `validate` passed.

Ask for a yes, or for edits. Edits go back to step 4, and the new proposal is shown the same way (whole when new, a diff when updating). Files are written only after the yes.

## 6. Write

On the yes:

1. Write the ficha and every reverse edit to their files (for a repo on another branch, in step 2's worktree).
2. Commit each project folder (not the home) that got a file and has git, one commit per repo, local only, on its work branch. When the checkout is another branch, write and commit in `git -C <folder> worktree add <scratch>/<id>-work <work-branch>`, then `git -C <folder> worktree remove` it; the checkout and its pending work stay untouched.
   - copy the format of the repo's `git log -n 10 --oneline` (prefix, language); the subject says the ficha puts the project in the home catalog;
   - commit the ficha alone, even when other work is staged: `git -C <folder> add project.yaml && git -C <folder> commit -m "<message>" -- project.yaml`.
   A folder without git just keeps the file.
3. Run `uv run <home>/catalog/catalog.py index`, and commit in the home, in its commit format, only `catalog/index.yaml` and the external fichas written in step 1: `git -C <home> add <paths> && git -C <home> commit -m "<message>" -- <paths>`. When `index` refuses because some ficha has errors, show its errors and stop: the project commits stand, and the index waits until those fichas are fixed.

Done when `index.yaml` lists the project and `git status` shows no uncommitted ficha in any repo this run touched. Report the commits made, and the next folder without a ficha when the target came from `validate`.
