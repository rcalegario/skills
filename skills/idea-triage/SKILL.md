---
name: idea-triage
description: Keeps the catalog of projects under ~/Projects. Use to write or update a project's ficha (project.yaml), or to fill the catalog folder by folder. /idea-triage ficha [repo]
---

# idea-triage

`<home>` is `realpath <skill-dir>/../..`: this skill lives in `<home>/skills/idea-triage`, reached through a symlink. The catalog is `<home>/catalog/`: the schema `project.schema.json`, the checker `catalog.py` (run with `uv run <home>/catalog/catalog.py validate|index`), and the generated `index.yaml`.

## Modes

| Command | Does |
|---|---|
| `ficha [repo]` | propose, validate and write a project's ficha |
