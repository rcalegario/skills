# CLAUDE.md (tlc-spec-driven fork)

This folder is a local fork of `tech-leads-club/agent-skills`, with its own `.git`. `~/.claude/skills/tlc-spec-driven` is a symlink to it: edit and commit here.

- Read `MODS.md` before changing or updating the skill. See our changes with `git diff upstream-<version> main` instead of re-reading everything.
- After editing a script or a template: `python3 -I scripts/selftest.py` and `python3 -I -m unittest discover -s tests`.
- Commits: Conventional Commits in English, subject states the why, stage files by name, with the attribution lines the session gives.
- After a commit, refresh the backup: `git bundle create ~/.claude/skills-backups/tlc-spec-driven.bundle --all`.
- The skills-manager can replace this folder and drop the `.git`. Run `git status` here first; if it is not a repo, restore it from the bundle (steps in `MODS.md`).
- `references/show-me.md` is a copy of an upstream skill: change it only by re-copying from the source in its header.
