# Setup

Steps for a fresh clone or a new machine. Each one can run again on a machine already set up.

1. Clone to `~/Projects/skills` (the links below assume it):

   ```sh
   git clone https://github.com/rcalegario/skills ~/Projects/skills
   ```

2. Link each skill into Claude (run it again after adding a folder to `skills/`):

   ```sh
   mkdir -p ~/.claude/skills
   for d in ~/Projects/skills/skills/*/; do n=$(basename "$d"); ln -sfn "${d%/}" ~/.claude/skills/"$n"; done
   ```

3. Create the personal settings of `task` and `idea-triage` (gitignored; edit `home` if your home repo is elsewhere):

   ```sh
   cp -n ~/Projects/skills/skills/task/config.example.yaml ~/Projects/skills/skills/task/config.yaml
   cp -n ~/Projects/skills/skills/idea-triage/config.example.yaml ~/Projects/skills/skills/idea-triage/config.yaml
   ```

4. Create the personal settings of `retro-report` (gitignored; edit `retros` and `projects` if your retros and projects are elsewhere):

   ```sh
   cp -n ~/Projects/skills/skills/retro-report/config.example.yaml ~/Projects/skills/skills/retro-report/config.yaml
   ```

5. Create the personal settings of `session-log` (gitignored; edit `out` if the session files go elsewhere):

   ```sh
   cp -n ~/Projects/skills/skills/session-log/config.example.yaml ~/Projects/skills/skills/session-log/config.yaml
   ```

6. Show the `retro-report` band, which offers a retro once `threshold` sessions wait for one: add the skill's mod to the `env` block of `~/.claude/settings.json`, so every session loads it (and reloads it when a file changes):

   ```json
   "env": { "CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/skills/retro-report/mod" }
   ```

   The variable takes several folders separated by `:`; keep any already there.

7. Write each session's `session-log` file when the session ends, and let `retro-report` judge whether it is worth a retro: add a SessionEnd hook to the `hooks` block of `~/.claude/settings.json`. It needs `python3` with PyYAML, and never fails the exit. Hooks of one event run in parallel, so the triage is piped after the extract in one command, which hands it the file it wrote. The `timeout` lifts the 1.5-second budget that SessionEnd hooks share by default, so a long log is not cut off:

   ```json
   "hooks": {
     "SessionEnd": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/skills/session-log/scripts/sessions.py extract --hook --print-path | python3 ~/.claude/skills/retro-report/scripts/retro.py triage --hook", "timeout": 10}]}]
   }
   ```

   Without `retro-report`, keep only `python3 ~/.claude/skills/session-log/scripts/sessions.py extract --hook`. The triage needs the `triage` block of `retro-report`'s `config.yaml` (step 4 copies it from `config.example.yaml`; add it to a config copied before).

   Keep any `SessionEnd` hooks already there, as other entries of the list.

8. Enable the pre-commit hook. It checks `skills.yaml` and runs the tests of the repo scripts and of each skill a commit touches (each skill's command is its `test:` in `skills.yaml`). It needs [uv](https://docs.astral.sh/uv/), `python3` and the `claude` CLI:

   ```sh
   git -C ~/Projects/skills config core.hooksPath .githooks
   ```

The eight skills are linked straight to this repo. If skills-manager ever lists one of them (`flow`, `task`, `spec-lite`, `tlc-spec-driven`, `idea-triage`, `retro-report`, `session-log`, `code-review`), remove it from the manager: it would replace the links with its own copy.
