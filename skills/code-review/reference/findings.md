# Findings

Every sub-agent reports findings in this shape, so the report is uniform and step 6 can record each one through `flow.py finding` without rewriting it.

## One finding, one line

```
- [<severity>, <confidence>] <file>:<line> - <what is wrong>. Hunk: `<the quoted line or lines>`. Fix: <what to change>. Source: <source>
```

- `<file>:<line>` is the line number in the file as it stands at `HEAD` (what `cat -n` shows), never a line inside a diff hunk. For a requirement that is **missing**, there is no line: write `-` for the file and quote the spec line in `Hunk`.
- `Hunk` quotes the code (or, for a missing requirement, the spec text) so the reader can check the claim without opening the file.
- `Fix` is a suggestion in one sentence; the skill never applies it.

## Severity

| Severity | Means |
|---|---|
| `blocker` | The change should not merge as it is: wrong behaviour, a requirement missing, a hard breach of a documented standard. |
| `should-fix` | A real problem that is not fatal: partial requirement, scope creep, a documented standard broken in a small way. |
| `nit` | Worth saying, fine to leave: a naming smell, a style preference. Every baseline smell is at most a `nit` or a `should-fix`, never a `blocker`. |

## Confidence

| Confidence | Means |
|---|---|
| `high` | The quoted hunk and the quoted rule or spec line plainly disagree. |
| `medium` | Likely wrong, but it depends on context the reviewer could not fully see. |
| `low` | A suspicion. Say so, and say what would settle it. |

## Source per axis

The `Source` is the value `flow.py finding --source` accepts:

| Axis | Source |
|---|---|
| Spec | `spec-review` |
| Standards | `standards-review` |

## Under each axis

A clean axis says "no findings". An axis that could not run (no spec) says why and is not counted as clean.
