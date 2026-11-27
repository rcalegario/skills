# Testing

Rules for every Python test in this repo: skills, tools, `lib/` and `scripts/`. Read them before writing or changing a test.

## Git: fake by default

1. The scripts reach git only through `lib/gitutil.py`. A test fakes git there with `lib/fakegit.py`: `fake = fakegit.install(monkeypatch)` points `gitutil` at an in-memory git, `fake.init(root, files)` makes a repository with one commit, `fake.commit(root, subject)` commits the tracked files as they are on disk and returns the short sha. The fake answers the commands `gitutil` sends and raises on any other, so a new git call fails the test loudly: teach it the command, with a case in `lib/test_fakegit.py`, which runs the same history on real git. The flow tests (`skills/flow/scripts/test_flow.py`, fixture `fake`) show the pattern.
2. Real git only when git's own behaviour is what the test checks: the paths `status --porcelain` prints, a path form git must accept, a git hook, `lib/gitutil.py` itself.
3. Then the repository is shared: a session-scoped fixture builds it once and each test gets a copy (`shutil.copytree`). Never `git init` in a test or a function-scoped fixture. The one exception is the contract test in `lib/test_fakegit.py`: the history it builds from `init` on is what it compares with the fake.
4. Set the identity once, in the shared fixture's config or with `-c user.name=... -c user.email=...`; never `git config` per test.
5. Commits a test needs beyond the shared ones are its cost: keep them to the few the behaviour needs.

## Processes: in process by default

1. Call the script's `main(argv)` and read what it prints with `capsys`, as the flow, task and retro-report tests do.
2. Start a process only when the entry point itself is what the test checks: argparse's `--help`, a run without a dependency, an interpreter flag (`-X utf8`), a hook git runs.
3. Start such a script with `sys.executable`: one process, in the suite's own environment. `uv run` starts uv and then Python and resolves an environment first (about twice the time); it appears only when it is itself the command under test, as in the hook.

## Why

On the machine these skills are built on, starting a process takes about 210 ms (the mean over 1054 `git` calls), most likely because an antivirus inspects each one; elsewhere it is often 30-80 ms. The pre-commit hook runs the suites a commit touches, so every process a test starts is paid on every commit. Before these rules, two suites spent 98% of their time starting `git` and `python`: the flow suite opened 1054 processes for 154 tests (4 min serial), the scripts suite 426 for 75 (6 min).

## Habits

- Drive a script through its CLI (`main([...])`) and assert on what it prints, its exit code and the files it writes, never on its internals.
- Write files under `tmp_path` only.
- Run a skill's tests from its folder with the `test:` command of `skills.yaml`; a tool's or `lib/`'s with its `test.cmd`; the scripts suite from the root (`python -m pytest -q scripts`).
- A suite that runs longer than about 20 s serially takes `-n auto` (pytest-xdist) in its test command. Each test then runs in any worker, so a test shares nothing but session fixtures and files under `tmp_path`.

## Measuring

`scripts/spawncount.py` counts the processes a suite starts. From the repo root, with the suite's `uv run` (pytest-xdist is turned off, so one process sees every start):

```sh
uv run -q --no-project --with pytest --with pyyaml python scripts/spawncount.py skills/flow -q scripts
```

The first argument is the folder to run in, the rest go to pytest. After pytest's summary it prints the number of processes and their wall time, the count and time per program (`git status`, `python.exe`) and the ten tests that started the most. Run it on a new test file, on a suite that got slower, and before adding real git to a test.
