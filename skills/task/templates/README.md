---
id: <YYYY-MM-DD-HHMM>-<slug>
title: "<title>"
link: <link to the base text (issue, ticket, note); null when pasted>
repos:
  - name: <repo>
    origin: <path of the main checkout>
    worktree: repos/<repo>  # relative to this folder; null when none
    branch: <branch>
    main: true              # on exactly one repo: the one whose name is the parent folder
---

# <slug> <title>

Folder rules in the `/task` skill's `reference/format.md`. Items split into requirements in [acs.yaml](acs.yaml).

## Base text (verbatim)

<!-- The issue, ticket or note this task started from, as it was read. Delete the section when there was none. -->

## Problem

## Who it serves

## Out of scope
