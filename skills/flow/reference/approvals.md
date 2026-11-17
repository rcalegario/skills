# Approval messages

Every stop where `flow` or `task` waits for the user's yes uses one skeleton and one of four types: **question**, **plan**, **outbound**, **checklist**. The user reads many of these; the same shape every time lets them find what is asked and what a yes does without reading twice.

Labels below are in English. Write them in the conversation's language (`Approval` → `Aprovação`, `On approval` → `Ao aprovar`); ids, commands, paths and enum values stay as they are.

## Skeleton

```
🛑 **Approval · <step> · <target>**
<what is at stake, in one or two lines>

<the type's body>

**On approval:** <exactly what a yes runs, writes, commits or sends>
➡️ <recommendation> (answer "yes" to approve)
```

- `<step>` is the skill step (`decide`, `plan`, `SPEC`, `pr`, `CLOSE`…), `<target>` what it is about (`round 2`, `F1.2`, `PR #42`).
- **On approval** is required. Name the commands, the files written, the commit and anything sent out. A yes approves only what this line names; anything more needs its own stop.
- Sections of a body come in the order given, and an empty one is left out.

## Cards

No message uses a table. A list of things (options, features, criteria, tasks, checks, steps) is a stack of cards, a blank line between them:

```
**T1 · Write the CSV writer**
- **covers:** AC1
- **blocked by:** nothing
- **commit:** `feat(export): let users download the report as CSV`
```

The title is bold, with the item's id first. Each attribute is one sub-list line with a bold label. A card with a single attribute may put it on the title line after ` · `.

## Enum values

A value from a fixed set is written in inline code. A state value gets a dot by meaning before it:

- 🟢 ok: `pass`, `done`, `chosen`, `decided`, reversible
- 🟡 waiting: `pending`, `proposed`, `recommended`, `open`, `doing`
- 🔴 problem: `fail`, `blocked`, irreversible
- ⚪ out of play: `dropped`, `superseded`

Neutral values (a type, a size, a check kind) get no dot: **size:** `M`, **check:** `manual`.

## question

To choose between options.

Body: an optional **Assumptions** list first (what was taken as given, each with where it came from, so the user corrects it at a glance), then the questions of the round, `---` between them. Each:

```
❓ **Q1 - D-07 <title>**: <the question, with the facts that matter and their context ids>

**A · <option>**
- **how:** …
- **pros:** …
- **cons:** …

**B · <option>**
- …

➡️ <recommended answer>
```

- Word each question so "yes" accepts its recommendation.
- Options are cards, one under the other. A question with no real alternative (confirm a fact or a single proposal) has no option cards.
- A spike is an answer: `➡️ hypothesis: <option>; spike V-nn on <where> settles it`.
- One **On approval** for the whole round: the decisions recorded, the children opened, the commit. The closing ➡️ says how to answer: "yes" for every recommendation, or `Q2: <other>` to change one.

## plan

To approve work before it is built.

Body sections, in this order:

1. **Blockers**: questions that must be answered first, as **question** blocks.
2. **Goal**: one line.
3. **Scope**: `in` and `out`, one line each.
4. **Content**, as cards:
   - requirement split: one card per requirement, with its root decision and validation;
   - roadmap: one card per feature, with milestone, size and blocked by;
   - spec: criteria cards, then task cards (covers, blocked by, commit) with one line on why the first leads, then check cards (criterion → `test` or `manual`);
   - S plan: only Goal and the steps as cards.
5. **Assumptions**: what was taken as given, with where it came from.

**On approval** names the script calls (`flow.py roadmap --approve`, `flow.py approve <feature> spec`, the `acs.yaml` written) and the commit.

## outbound

To let something leave this machine or happen where it cannot be taken back: a push, a PR, a comment, a deploy, a removal, an action on a shared environment.

Body sections, in this order:

1. **Action**: the exact command, in a code block.
2. **Target**: the remote, branch, issue, environment or path.
3. **Payload**: what goes with it, verbatim (the PR title and body, the comment), or the diff size against the repo's PR limit.
4. **Undo**: how to take it back, or 🔴 irreversible.

**On approval** runs exactly the **Action** command and records the link or result.

## checklist

For checks only the user can run.

Body: one card per check, numbered in the order to run them:

```
**1 · AC2 · An empty list shows the message**
- **steps:** open the report with no rows, click Export
- **expected:** "Nothing to export" appears
```

The closing ➡️ gives the answer form: one line, `1 ok, 2 failed: <what you saw>`. **On approval** names `flow.py set <feature> AC<n> pass|fail` for each line, and that each failure becomes a fix task.
