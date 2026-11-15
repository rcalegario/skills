---
name: idea-triage
description: Triages new ideas against the catalog of projects under ~/Projects, and keeps that catalog. Use to triage an idea before any code is written, or to write or update a project's ficha (project.yaml).
argument-hint: ficha [repo] | triage [idea]
---

# idea-triage

`<home>` is the `home:` value in `<skill-dir>/config.yaml` (expand `~`). When the file is missing, ask the user for the path of their home repo and write it there; `config.example.yaml` shows the format. The catalog is `<home>/catalog/`: the schema `project.schema.json` (the only source of fields, enums and patterns), the checker `catalog.py`, run as `uv run <home>/catalog/catalog.py validate|index`, and the generated `index.yaml`.

Free-text values (a ficha's `question`, `features`, `notes`; a triage record's text) are in Portuguese; `entities` are English nouns (`account`, `transaction`); ids and enum values stay as the schema has them.

The **central** is the shared monorepo where new ideas enter as modules (a ficha's `shape: route`); a project of its own is `standalone`. The central does not exist yet: every existing project is `standalone`, and work on a `route` idea waits for the central to be created.

The rules here and in the mode files are the current ones; `<home>/docs/estrutura-projetos.md` records the conversation they started from.

## Modes

Each mode's steps live in its own file next to this one. Read that file and follow it from step 1; the rest of this file holds what every mode shares.

| Command | Does | Steps |
|---|---|---|
| `ficha [repo]` | propose, validate and write a project's ficha | [`ficha.md`](ficha.md) |
| `triage [idea]` | decide where a new idea goes: already exists, feature of a project, route in the central, or standalone | [`triage.md`](triage.md) |
