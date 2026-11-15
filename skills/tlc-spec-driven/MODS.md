# Local modifications to tlc-spec-driven

## Where this lives (read first)

- **Real folder:** `~/.skills-manager/skills/tlc-spec-driven` - the skills-manager store. It holds the `.git` of this fork.
- `~/.claude/skills/tlc-spec-driven` is a **symlink** to it. The manager replaced the real folder with that link (2026-11-08, when `show-me` was installed) and the `.git` that lived there was lost. Edit and commit in the store path; never rely on a `.git` under `~/.claude/skills`.
- The manager can replace the folder again on an install, update or deploy. After any manager action, run `git -C ~/.skills-manager/skills/tlc-spec-driven status`; if it is not a repository, restore it: `git clone ~/.claude/skills-backups/tlc-spec-driven.bundle <tmp>`, then copy `<tmp>/.git` into the store folder and `git checkout main`.
- Backup bundle: `~/.claude/skills-backups/tlc-spec-driven.bundle` (refresh with `git bundle create <that path> --all` after meaningful commits).
- The manager has this skill as an `import` with no upstream URL, so it never fetches updates. Updates come from `tech-leads-club/agent-skills`, folder `packages/skills-catalog/skills/(development)/tlc-spec-driven`, and are merged by hand.
- `.skill-meta.json` and `__pycache__` are git-ignored; the manager's content hash in its database goes stale after our commits and does not matter.

Base: upstream 4.1.0 (`upstream-4.1.0`). Update procedure:
1. Put the new upstream tree on branch `upstream` and tag it `upstream-<version>`.
2. `git merge upstream` into `main`; conflicts land exactly on the lines below.
3. Run `python3 scripts/selftest.py` and `python3 -m unittest discover -s tests`.

See what we changed: `git diff upstream-4.1.0 main` (or `git log upstream-4.1.0..main`).
The previous version (3.x + our edits) is kept on branch `local-mods`. A bundle backup of the whole repo is at `~/.claude/skills-backups/tlc-spec-driven.bundle`.

## Kept

| Change | Why | Where |
| --- | --- | --- |
| Feature folders are `m<N>.f<N>.<slug>`: milestone (a large cut that delivers value), feature inside it (may be a back/front slice), `f` restarts per milestone. Old names keep working with `--allow-legacy` | Traceability from feature to milestone; used across our projects | `scripts/validate_spec.py`, `references/specify.md` §0, `SKILL.md` |
| Generated indexes: `index.py features` (`.specs/features/AGENTS.md`) and `index.py adr` (`docs/adr/AGENTS.md`), each with a `CLAUDE.md` import | Agents read one table instead of every folder | `scripts/index.py`, `tests/test_index.py` |
| Decisions are ADRs in `docs/adr/AD-NNN-slug.md`; `STATE.md` holds only the Handoff. `validate_spec.py` reads active ADRs, with `STATE.md` as legacy fallback | Decisions live with the code and are indexed | `references/memory.md`, `references/design.md`, `scripts/validate_spec.py`, `tests/test_validate_spec_decisions.py` |
| Tasks are skipped at ≤5 steps (matches the >5 safety valve); Medium row says ≤5 steps | Upstream contradicted itself (<10 tasks vs >5) | `SKILL.md`, `references/tasks.md` |
| Gate Build is one row: build + lint + all tests | `implement.md` said "lint only", `tasks.md` said "all tests" | `references/implement.md` |
| `tasks.md` template fenced with four backticks | The inner diagram fence closed the template early, so the rest leaked into projects' tasks.md | `references/tasks.md` |
| Size limits in words (spec ≲3k, design ≲5k, tasks ≲6k, `wc -w`) | The agent can count words, not tokens | `SKILL.md` |
| Grill by scope (Small never, Medium on a yes, Large/Complex by default); `grilling` is an optional external skill | Stress-test specs before approval | `SKILL.md` §Companion skills, `references/discuss.md`, `references/specify.md` |
| Show me: a copy of Dex Horthy's `show-me` (MIT) inside the skill, used for explanations and documents. The upstream skill is user-invoked only, so it is copied, not loaded; re-copy when upstream changes (pinned blob in the file header) | Explain with visuals, and do not depend on a skill the model cannot load | `references/show-me.md`, `SKILL.md` §Companion skills, `references/design.md` |

## Dropped (upstream 4.x replaced them)

- `validate_state.py` verdict fix: the script is gone; `validate_verification.py` does not parse a verdict by regex.
- `run_mutant.py` and the 5-mutant sensor: upstream dropped mutations for proofs run with the project's own tests.
- Handoff section-scoped write rule, lessons and sub-agents wording tied to mutants.
- "Ask which MCPs/skills per task": upstream removed it.
- `REVIEW.md` and `.changes/` (history on `local-mods`).
