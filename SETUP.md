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

4. Enable the pre-commit hook. It checks `skills.yaml` and runs the tests of the repo scripts and of each skill a commit touches (each skill's command is its `test:` in `skills.yaml`). It needs [uv](https://docs.astral.sh/uv/) and `python3`:

   ```sh
   git -C ~/Projects/skills config core.hooksPath .githooks
   ```

The five skills are linked straight to this repo. If skills-manager ever lists one of them (`flow`, `task`, `spec-lite`, `tlc-spec-driven`, `idea-triage`), remove it from the manager: it would replace the links with its own copy.
