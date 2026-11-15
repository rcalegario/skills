# Local modifications to tlc-spec-driven

## Where this lives (read first)

- This folder is `skills/tlc-spec-driven/` in my skills repo (`~/Projects/skills`); `~/.claude/skills/tlc-spec-driven` links here. Edit and commit in the repo, as for any other skill there.
- Its history was imported with paths rewritten under `skills/tlc-spec-driven/`, so its refs carry the `tlc-spec-driven/` prefix: branch `tlc-spec-driven/upstream`, tags `tlc-spec-driven/upstream-<version>`, branch `tlc-spec-driven/local-mods`.
- Updates come from `tech-leads-club/agent-skills`, folder `packages/skills-catalog/skills/(development)/tlc-spec-driven`, and are merged by hand. The pinned upstream commit is this skill's reference in the repo's `skills.yaml`.

Base: upstream 4.1.0 (tag `tlc-spec-driven/upstream-4.1.0`). Update procedure, from the repo root:
1. `git worktree add <tmp> tlc-spec-driven/upstream`, copy the new upstream folder over `<tmp>/skills/tlc-spec-driven/` (`rsync -a --delete`), commit it there as `upstream: tlc-spec-driven <version> @<sha>`, tag it `tlc-spec-driven/upstream-<version>`, then `git worktree remove <tmp>`.
2. `git merge tlc-spec-driven/upstream` into `main`; conflicts land exactly on the lines below.
3. Run `python3 -I scripts/selftest.py` and `python3 -I -m unittest discover -s tests` from this folder (the repo hook also runs them).
4. Set the new upstream commit in `skills.yaml` and run `python scripts/skills.py credits --write`.

See what we changed: `git diff tlc-spec-driven/upstream-4.1.0 main -- skills/tlc-spec-driven` (or `git log tlc-spec-driven/upstream-4.1.0..main -- skills/tlc-spec-driven`).

The previous version (3.x + our edits) is kept on branch `tlc-spec-driven/local-mods`.

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
- `REVIEW.md` and `.changes/` (history on `tlc-spec-driven/local-mods`).
