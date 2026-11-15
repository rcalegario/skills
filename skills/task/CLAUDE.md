# CLAUDE.md (task)

Own skill, living in `~/Projects/skills/skills/task` (the shared repo, see its root CLAUDE.md); `~/.claude/skills/task` links here. Edit and commit here.

- Works with its sibling `flow` (`skills/flow`): `plan` and `review` follow `flow`'s SKILL.md, and `status.py` reads `flow`'s `feature.yaml` (`status`, `repo`, `story`). Change both together when the feature format moves.
- `config.yaml` holds the home (`~/Projects/home`); it is gitignored, and `config.example.yaml` is the versioned copy (SETUP.md copies it). The folder format is `reference/format.md`.
- `scripts/task.py` writes the YAMLs (journal, decisions, validations, pending, brief date) by line edits, reusing `flow`'s helpers from `skills/flow/scripts`; `status.py` only reads. Add a command for any field an id, date or status gets typed into.
- `scripts/status.py` needs PyYAML. Its tests drive the CLI only; the repo root pre-commit hook runs them when this skill is staged (command: its `test:` in the root `skills.yaml`).
- Commits: Conventional Commits in English, subject states the why, stage files by name.
