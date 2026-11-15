# CLAUDE.md (tlc-spec-driven fork)

This folder is a fork of `tech-leads-club/agent-skills`, kept in my skills repo.

- Read `MODS.md` before changing or updating the skill. See our changes with `git diff tlc-spec-driven/upstream-<version> main -- skills/tlc-spec-driven` instead of re-reading everything.
- After editing a script or a template: `python3 -I scripts/selftest.py` and `python3 -I -m unittest discover -s tests` (the repo pre-commit hook runs both when this skill is staged).
- Commits: Conventional Commits in English, subject states the why, stage files by name, with the attribution lines the session gives.
- `references/show-me.md` is a copy of an upstream skill: change it only by re-copying from the source in its header.
