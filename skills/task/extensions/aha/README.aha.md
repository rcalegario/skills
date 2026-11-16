---
id: <YYYY-MM-DD-HHMM>-<aha-id-lowercase>
title: "<title>"
link: <Aha link to the record>
feature: <Aha link to the parent feature>
status_at_source: <status in Aha when read>
estimate: <hours>
comments_read_until: null   # timestamp of the newest Aha comment already read
owner: <name>
repos:
  - name: <repo>
    origin: <path of the main checkout>
    worktree: repos/<repo>  # relative to this folder; null when none
    branch: <branch>
    main: true              # on exactly one repo: the one whose name is the parent folder
---

# <AHA-ID> <title>

Folder rules in the `/task` skill's `reference/format.md`. Items split into requirements in [acs.yaml](acs.yaml).

## The story (verbatim)

**As a** ..., **I want** ..., **so that** ...

**Acceptance Criteria**

- [ ] **AC-1:** ...

**Note:** ...

The note, split into items:

| Id | Note item |
|---|---|
| **N-n** | ... |

## Where it fits in the feature

| Story | Delivers | Owner | Relation to this one |
|---|---|---|---|
| ... | ... | ... | ... |
