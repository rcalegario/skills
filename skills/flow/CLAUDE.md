# CLAUDE.md (flow)

Own skill, living in `~/Projects/skills/skills/flow` (the shared repo, see its root CLAUDE.md); `~/.claude/skills/flow` links here. Edit and commit here.

- Works alone in any repo, and inside a `task` folder (`skills/task`) through `--specs`. `task`'s `status.py` reads `feature.yaml` (`status`, `repo`, `story`): change both together when the feature format moves.
- Each feature is `spec.md` (prose, from `templates/spec.md`) plus `feature.yaml` (everything the script checks). Status changes, `new` (the feature skeleton), `finding` and `roadmap --approve` go through `scripts/flow.py`; `task.py` imports its line-editing helpers, so keep their names.
- `scripts/flow.py` needs PyYAML. Its tests drive the CLI only; the repo root pre-commit hook runs them when this skill is staged (command: its `test:` in the root `skills.yaml`).
- Commits: Conventional Commits in English, subject states the why, stage files by name.
