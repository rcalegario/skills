# Fallback: commits, branches and pull requests

Used only for the topics the project documents none of its own (a `CONTRIBUTING.md`, a `CLAUDE.md` / `AGENTS.md` section, or a PR template). When the project documents a topic, its rule wins for that topic.

## Commits

- Title: `<type>(<scope>): <summary>`, a Conventional Commit. `<type>` is one of `feat`, `fix`, `chore`, `ci`, `docs`, `refactor`, `revert`, `build` or `test`; the scope is optional. The summary says why the change matters.
- One commit per finished task, made once its tests pass. Keep unrelated changes in separate commits.
- Add a body only when the change is complex. A breaking change takes `!` right before the colon: `feat(api)!: ...`.

## Branches and target

- Branch: `<type>/<slug>`, e.g. `feat/ponto-export-csv`, with `<type>` the Conventional Commit type of the PR title.
- Target `main`, except stacked PRs, which target their parent PR's branch.

## Pull requests

- Title: a Conventional Commit, like a commit title. When the repo squash-merges, it becomes the commit on `main`, so a breaking change carries `!` in the title.
- Body: the project's PR template, or `pull_request_template.md` next to this file.
- **Testing** lists only the tests actually run; **evidence** is something a reviewer can check (a CI run, commands and their output, screenshots).
- Aim for about 500 changed lines or fewer, generated files excluded. Split larger work into stacked PRs: each targets the branch of the PR below it, says `Stacked on: #N`, and the stack merges bottom up.
- Open the PR as a **draft** until CI is green.
