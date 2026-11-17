---
name: session-log
description: Writes one YAML file per Claude Code session (calls, failures, tokens, cost per model, skills, compactions, edits, title and opening prompt, subagents), under a folder per day, for every session whose file is missing or older than its log. /session-log [<session.jsonl>...]
disable-model-invocation: true
---

# session-log

`<skill-dir>` is the folder holding this file. Run `python3 <skill-dir>/scripts/sessions.py extract` (needs PyYAML); `--help` lists the options. When it reports `config.yaml` missing, ask the user to copy `<skill-dir>/config.example.yaml` to it and fill it.

- No argument: run `extract`. It reads every session log under `~/.claude/projects/` and writes `<out>/<YYYY-MM-DD>/<session-id>.yaml` for each one whose file is missing or older than its log (the date is the session's local start date).
- Log paths as arguments: run `extract <logs>`, which writes those files whatever their age.

Report the line it prints (`N written, M up to date, K not session logs`) and the `out` folder. Talk to the user in the language they use.
