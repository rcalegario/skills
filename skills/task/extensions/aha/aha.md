# Aha extension

Read when `/task <id>` names an Aha record (`SKILL.md`, Extensions). Follow `SKILL.md` as written; this file adds to a step or replaces part of it, under the same step name. Nothing here applies to a task that is not an Aha story.

Tools: `read_records` (Aha MCP). `<AHA-ID>` is the record id (`AHSMT-85-2`); the task slug is that id in lowercase (`ahsmt-85-2`), so the folder is `<home>/tasks/<main-repo>/<YYYY-MM-DD-HHMM>-ahsmt-85-2/`.

## Recognising

The id looks like `<PREFIX>-<n>` or `<PREFIX>-<n>-<m>` and `read_records` finds it. When an Aha-shaped id is not found, ask whether it is a typo or a plain task.

## Ground rules (adds)

- **Outbound needs a yes** also covers an Aha comment and an Aha field change.
- Facts are also looked up in Aha, not only in the code.

## start

- **Read the base** (replaces the base-text question and the grilling): `read_records` the story (`fields: detailed`, include `comment`), then its parent feature with its `requirement` association, to know the sibling stories. Read every comment: they carry what the description lacks. Grill only the gaps the story leaves.
- **Branch**: `<type>/<AHA-ID>-<slug>` when the repo documents none.
- **Folder**: use `README.aha.md` instead of the base `README.md` template. Fill `comments_read_until` with the newest comment's timestamp.
- **Items**: besides the story's `AC-n`, split each item of the story's Note into `N-n`, and write each `N-n` in `acs.yaml` like an `AC-n`. A `N-n` has requirements and a root decision as any item does.

## Resume

Before running `status.py`: read the story's comments newer than `comments_read_until`. Write what they change into `context/`, decisions or `pending.yaml`, journal it, and move the marker.

## consolidate --publish

The reader can be the PO or the team: besides Claude Docs or an Artifact, offer a comment on the story with the version without ids. A comment posted records its link with `task.py journal`, and in `pending.yaml` as `aha_comment` when it waits on an answer.

## pr

Used only for the topics the repo leaves undocumented, on top of `fallback/`:

- **Branch**: `<type>/<AHA-ID>-<slug>`, e.g. `feat/AHSMT-72-16-promote-final-without-rebuild`; without an Aha record (a dependency bump) `<type>/<slug>`.
- **Title**: `<type>(<scope>): [AHSMT-x-y] <summary>`; leave the bracket out when there is no record.
- **Body**: under Related Work add `**Aha record:** [AHSMT-x-y](https://komatsuahs.aha.io/requirements/AHSMT-x-y)`, the most specific record (the requirement, otherwise the feature `https://komatsuahs.aha.io/features/AHSMT-x`). Only bot, dependency or hotfix PRs write `N/A — <reason>`. Author checklist: title and branch carry the id, the record is linked. Reviewer checklist: the linked record matches the change.
- After the PR is open, offer a comment with its link on the story (needs a yes).
