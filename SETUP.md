# Setup

Steps for a fresh clone or a new machine. Each one can run again on a machine already set up.

1. Clone to `~/Projects/skills` (the links below assume it).

2. Link each skill into Claude (run it again after adding a folder to `skills/`):

   ```sh
   mkdir -p ~/.claude/skills
   for d in ~/Projects/skills/skills/*/; do n=$(basename "$d"); ln -sfn "${d%/}" ~/.claude/skills/"$n"; done
   ```

3. Enable the pre-commit hook. It checks `skills.yaml` and runs the tests of the repo scripts and of each skill a commit touches (each skill's command is its `test:` in `skills.yaml`). It needs [uv](https://docs.astral.sh/uv/) and `python3`:

   ```sh
   git -C ~/Projects/skills config core.hooksPath .githooks
   ```
