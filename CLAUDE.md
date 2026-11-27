# skills

My own agent skills, published as `rcalegario/skills`. Each lives in `skills/<name>/` with its own `SKILL.md`; `~/.claude/skills/<name>` links here, so an edit takes effect at once.

Fresh clone or new machine → follow SETUP.md.

- `skills.yaml` records each skill's references (what it was built from) and its `test:` command; a new skill needs its entry there. After editing it, run `python scripts/skills.py credits --write`: the pre-commit hook checks both.
- A skill folder may carry its own `CLAUDE.md` (and `MODS.md` for a fork): read it before changing that skill.
- Each skill's history was imported with paths rewritten under `skills/<name>/`, so `git log -- skills/<name>` shows it. Keep commits per skill, with the skill as the scope: `feat(flow): ...`. Conventional Commits, English, subject says why.
- The repo is public: write no names, emails or absolute home paths into it; personal settings go in a gitignored file next to a versioned `*.example.*`.
- Third-party skills are referenced, never copied in.
- A tool that works with the skills but is not one lives in `tools/<name>/`, with its own README and a one-line `test.cmd` the pre-commit hook runs from that folder; it has no `skills.yaml` entry and is listed in the README's Tools table. Commits take the tool's name as the scope.
- `lib/` holds generic helpers the skills' scripts share (YAML, git, graphs); it names no file, field or status of any skill (its README). A commit staging only modules (`lib/<m>.py`) runs its `test.cmd` and the tests of the skills and tools importing them, directly or through another lib module or skill; staging any other `lib/` file runs every skill's and tool's tests. Commits take `lib` as the scope.
- Before writing or changing a test, read [TESTING.md](TESTING.md): git is faked by default, real git is shared and a last resort, scripts are called in process.
- Run a skill's tests from inside its folder, with the `test:` command from `skills.yaml` (`cd skills/<name>` in its own Bash call). From `skills/` or the repo root, pytest leaves a `.pytest_cache` outside any skill folder.
