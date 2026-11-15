# Specify

Goal: a `spec.md` the user approves, where every acceptance criterion states one outcome someone can observe.

## 1. Understand the request

Scan the code around the feature first, then open with the assumptions you are making, each with where it came from, so the user corrects them at a glance:

```
Assumptions (correct me now, or I go with these):
1. Export uses the current screen's filters, not the whole list — the list filters client-side
2. Comma separator, UTF-8 with BOM, so Excel opens it right
3. Only the list owner can export — same rule as the "Edit" button
```

Every answer lands in the spec: an AC, an `Out of scope` line, or a `## Notes` entry. Then talk: what problem, for whom, what does done look like, what is out. Turn vague words into concrete ones ("fast" → "under 1 s for 1,000 rows"; "users" → "the logged-in owner").

**Grill by size.** Medium: when the draft passes `check`, offer once: "Want me to grill this spec first?" and run `grilling` on a yes. Large: run `grilling` before presenting the spec. Bound it to this feature's behaviour and scope; architecture is the design's job.

## 2. Write the criteria

`spec.md` comes from `start` with the template. Each criterion is one line, `- **ACn**: <text>`, in one of four shapes:

| Shape | Use for | Example |
| --- | --- | --- |
| `WHEN <trigger> THEN <result>` | a response to an action or event | WHEN the user clicks "Export" THEN a CSV of the filtered rows downloads |
| `IF <error> THEN <result>` | failures, invalid input, empty states | IF the list is empty THEN the page shows "Nothing to export" |
| `WHILE <state>, WHEN <trigger> THEN <result>` | behaviour that holds only in a state | WHILE an import runs, WHEN the user opens Export THEN the button is disabled |
| `ALWAYS <invariant>` | a rule that always holds | ALWAYS amounts are stored in cents |

- One outcome per criterion; two behaviours are two ACs.
- Concrete values: the exact message, the status code, the limit.
- For each WHEN, ask what the IF is: the error, the empty case, the duplicate. That is the requirement most often missing.
- Re-read the request sentence by sentence: each sentence lands on an AC, an `Out of scope` line, or a question.

`## Notes` holds decisions taken along the way; for a medium feature, also the design in a few lines (which modules change, any new data shape).

## 3. Design (large features only)

Write `design.md` only when a choice needs explaining: a new module, a data model, a library, a flow across components. Keep it short: the components touched, the data shape, the chosen option and the one you rejected with why. A small diagram (file tree, call flow, Mermaid) beats a paragraph when the flow is not obvious. Ask the user only about choices that change what they will see or maintain.

## 4. Present and stop

Run `check <feature>` until it passes. Then present: the problem in a line, the ACs, out of scope, and the defaults you picked for the user to correct. Questions that block go first.

On the user's approval: `approve <feature> spec`. It writes the `tasks.yaml` skeleton; go to [tasks.md](tasks.md).
