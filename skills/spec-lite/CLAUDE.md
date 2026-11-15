# CLAUDE.md (spec-lite)

Own skill, with its own `.git`, living in the skills-manager store; `~/.claude/skills/spec-lite` points here. Edit and commit here.

- A lighter sibling of `tlc-spec-driven` (`~/.skills-manager/skills/tlc-spec-driven`): keep the same `m<N>.f<N>.<slug>` folder names so a feature can escalate to tlc mid-way.
- `scripts/specs.py` needs PyYAML (`python3 -m pip install --user --break-system-packages pyyaml`; again after a Homebrew Python minor upgrade). Run it and the tests without `python3 -I`: isolated mode hides the user site-packages.
- After editing the script or a template: `python3 -m unittest discover -s tests`. Tests drive the CLI only.
- The spec template is `templates/spec.md`; the tasks skeleton is built in `specs.py` (`tasks_skeleton`).
- Commits: Conventional Commits in English, subject states the why, stage files by name. After a commit, refresh the backup: `git bundle create ~/.claude/skills-backups/spec-lite.bundle --all`.
- The skills-manager (registered as `local`, deployed to claude_code, preset Default) can replace this folder and drop the `.git`. Run `git status` here first; if it is not a repo: `git clone ~/.claude/skills-backups/spec-lite.bundle <tmp>`, move `<tmp>/.git` into this folder, then `git checkout main`.
