---
name: idea-triage
description: Keeps the catalog of projects under ~/Projects and triages new ideas against it. Use to write or update a project's ficha (project.yaml), to fill the catalog folder by folder, or to triage a new idea before any code is written.
argument-hint: ficha [repo] | triage [idea]
---

# idea-triage

`<home>` is `realpath <skill-dir>/../..`: this skill lives in `<home>/skills/idea-triage`, reached through a symlink. The catalog is `<home>/catalog/`: the schema `project.schema.json` (the only source of fields, enums and patterns), the checker `catalog.py`, run as `uv run <home>/catalog/catalog.py validate|index`, and the generated `index.yaml`.

Free-text ficha values (`question`, `features`, `notes`) are in Portuguese; `entities` are English nouns, as in the example in `<home>/docs/estrutura-projetos.md`; ids and enum values stay as the schema has them.

## Modes

Each mode's steps live in its own file next to this one. Read that file and follow it from step 1; the rest of this file holds what every mode shares.

| Command | Does | Steps |
|---|---|---|
| `ficha [repo]` | propose, validate and write a project's ficha | [`ficha.md`](ficha.md) |
| `triage [idea]` | decide where a new idea goes: already exists, feature of a project, route in the central, or standalone | [`triage.md`](triage.md) |
