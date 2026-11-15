# Setup

Steps for a fresh clone or a new machine. Each one can run again on a machine that is already set up.

1. Enable the pre-commit hook:

   ```sh
   git -C ~/.skills-manager/skills/task config core.hooksPath .githooks
   ```

2. Install [uv](https://docs.astral.sh/uv/): the hook runs the tests through it.
