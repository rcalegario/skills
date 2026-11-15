# skills

My own agent skills, published as `rcalegario/skills`. Each lives in `skills/<name>/` with its own `SKILL.md`; `~/.claude/skills/<name>` links here, so an edit takes effect at once.

Fresh clone or new machine → follow SETUP.md.

- `skills.yaml` records each skill's references (what it was built from) and its `test:` command; a new skill needs its entry there. After editing it, run `python scripts/skills.py credits --write`: the pre-commit hook checks both.
- A skill folder may carry its own `CLAUDE.md` (and `MODS.md` for a fork): read it before changing that skill.
- Each skill's history was imported with paths rewritten under `skills/<name>/`, so `git log -- skills/<name>` shows it. Keep commits per skill, with the skill as the scope: `feat(flow): ...`. Conventional Commits, English, subject says why.
- The repo is public: write no names, emails or absolute home paths into it; personal settings go in a gitignored file next to a versioned `*.example.*`.
- Third-party skills are referenced, never copied in.
