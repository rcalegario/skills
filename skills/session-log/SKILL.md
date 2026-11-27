---
name: session-log
description: Writes one YAML file per Claude Code session (calls, failures, tokens, cost per model, skills, compactions, edits, title and opening prompt, subagents), under a folder per day, for every session whose file is missing or older than its log. /session-log [<session.jsonl>...]
disable-model-invocation: true
---

# session-log

`<skill-dir>` is the folder holding this file. Run `python3 <skill-dir>/scripts/sessions.py extract` (needs PyYAML); `--help` lists the options. When it reports `config.yaml` missing, ask the user to copy `<skill-dir>/config.example.yaml` to it and fill it.

- No argument: run `extract`. It reads every session log under `~/.claude/projects/` and writes `<out>/<YYYY-MM-DD>/<session-id>.yaml` for each one whose file is missing or older than its log (the date is the session's local start date).
- Log paths as arguments: run `extract <logs>`, which writes those files whatever their age.
- Session ids (or unique prefixes) as arguments: run `extract <ids>`, which writes each file when missing or older than its logs. An id that matches no log, or a prefix that matches several, exits 1 with one line.

`--print-path` prints only the path of each named session's file, one per line, so another skill can read a session's metrics on demand: `extract <id> --print-path`.

`transcript <id>` prints a session's conversation in a compact form, for an agent to read the whole session: a header (session, project, span, metrics file), then prompts and agent text whole, thinking and call results cut, each call as `#n` with the number the session file uses, and skills, compactions, interruptions and subagents in one line each. `--from N --to M --full` reads calls N to M untruncated, `--agent <id>` reads a subagent (its id is on the `→ agent` line), `--lines N` keeps more of each cut; an error result always keeps its first 20 lines.

A SessionEnd hook (`extract --hook`, set up by the repo's SETUP.md) writes each session's file when it ends, so a run by hand only catches what the hook missed.

`extract --hook --print-path` prints only the written file's path (nothing on failure), so the hook command can pipe it into another script, such as `retro-report`'s triage.

Report the line it prints (`N written, M up to date, K not session logs`) and the `out` folder. Talk to the user in the language they use.
