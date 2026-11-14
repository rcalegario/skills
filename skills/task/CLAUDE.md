# CLAUDE.md (task)

Own skill, with its own `.git`, living in the skills-manager store; `~/.claude/skills/task` points here. Edit and commit here.

- Works with its sibling `flow` (`~/.skills-manager/skills/flow`): `plan` and `review` follow `flow`'s SKILL.md, and `status.py` reads `flow`'s `feature.yaml` (`status`, `repo`, `story`). Change both together when the feature format moves.
- `config.yaml` holds the home (`~/Projects/home`); the folder format is `reference/format.md`.
- `scripts/status.py` needs PyYAML. After editing the script or a template: `python3 -m pytest -q scripts` (or `uv run --no-project --with pytest --with pyyaml python -m pytest -q scripts`). Tests drive the CLI only.
- Commits: Conventional Commits in English, subject states the why, stage files by name. After a commit, refresh the backup: `git bundle create ~/.claude/skills-backups/task.bundle --all`.
- The skills-manager (registered as `local`, deployed to claude_code, preset Default) can replace this folder and drop the `.git`. Run `git status` here first; if it is not a repo: `git clone ~/.claude/skills-backups/task.bundle <tmp>`, move `<tmp>/.git` into this folder, then `git checkout main`.
