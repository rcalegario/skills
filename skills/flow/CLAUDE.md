# CLAUDE.md (flow)

Own skill, with its own `.git`, living in the skills-manager store; `~/.claude/skills/flow` points here. Edit and commit here.

- Works alone in any repo, and inside a `task` folder (`~/.skills-manager/skills/task`) through `--specs`. `task`'s `status.py` reads `feature.yaml` (`status`, `repo`, `story`): change both together when the feature format moves.
- Each feature is `spec.md` (prose, from `templates/spec.md`) plus `feature.yaml` (everything the script checks). Status changes go through `scripts/flow.py`.
- `scripts/flow.py` needs PyYAML. After editing the script or a template: `python3 -m pytest -q scripts` (or `uv run --no-project --with pytest --with pyyaml python -m pytest -q scripts`). Tests drive the CLI only.
- Commits: Conventional Commits in English, subject states the why, stage files by name. After a commit, refresh the backup: `git bundle create ~/.claude/skills-backups/flow.bundle --all`.
- The skills-manager (registered as `local`, deployed to claude_code, preset Default) can replace this folder and drop the `.git`. Run `git status` here first; if it is not a repo: `git clone ~/.claude/skills-backups/flow.bundle <tmp>`, move `<tmp>/.git` into this folder, then `git checkout main`.
