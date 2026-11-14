# triage [idea]

The funnel and the route rule live in `<home>/docs/estrutura-projetos.md` (Triagem e catálogo): read that section before step 3. The **verdict** is one of:

- `exists`: a catalogued project or a GitHub repo already answers the idea;
- `feature`: the idea fits a catalogued project, which becomes the target;
- `route`: a module in the central, the default for anything new;
- `standalone`: its own project, only when one of the doc's criteria holds (another client, outside users or own domain, heavy or continuous background, another stack, data or load that would hurt the other modules); "looks big" is not one.

## 1. Idea and earlier records

Take the idea from the argument, or ask for it in one sentence. Read every record in `<home>/docs/triage/` (fields `idea`, `verdict`, `target`, `why`). When one is about the same idea, show it first and ask whether to triage again; on a no, stop.

Done when you hold the idea in one sentence and either no record covers it or the user chose to triage again.

## 2. Candidates

- **Catalog:** read `<home>/catalog/index.yaml`. A candidate is a project whose `question`, `features` or `entities` answer part of the idea; `domain` alone only narrows the search. List each one with the field that matched and how far it covers the idea. Run `catalog.py validate` too and name the folders without a ficha whose line in `<home>/CLAUDE.md` touches the idea: they are blind spots, not candidates.
- **GitHub:** `gh search repos <2-4 English keywords> --sort stars --limit 5 --json fullName,description,stargazersCount,pushedAt,url`. Phrase searches match too little: when one comes back empty, drop a keyword and run it again. Keep at most 5 repos that actually do the idea, each with stars and last push.

Show both lists before the first question.

Done when every catalogued project has been weighed, and the GitHub list holds the repos found or says what was searched and came back empty.

## 3. Quick round

Ask one question per message, each with your recommended answer so a "yes" accepts it, 10 questions at most. Ask only what the user decides: what the idea is for and who uses it, whether a candidate already does enough, which project it belongs to, which standalone criterion holds. Facts in the code, the fichas or the docs you look up yourself. Walk the funnel in order: exists, then feature, then route versus standalone; stop asking as soon as the verdict is clear.

Done when one verdict follows from the answers, with its target (the project or repo for `exists` and `feature`) and the reason in one or two sentences.

A `standalone` verdict creates a project, so it earns the full grill: invoke the `grilling` skill on the idea and the criterion that made it standalone, and carry what it settles (client, users, stack, data, what stays out) into the record's `why`. When the grill shows no criterion holds after all, the verdict goes back to `route`.

Done, for `standalone`, when the grill's frontier is empty and the user confirmed the shared understanding.

## 4. Record

Draft the record for `<home>/docs/triage/<YYYY-MM-DD>-<slug>.yaml`, the date today and the slug a short kebab-case name for the idea in Portuguese, like ficha features. Free text in Portuguese, long text as `|` blocks:

```yaml
date: 2026-11-14
idea: Saber quanto posso gastar por dia sem estourar o orçamento.
candidates:
  catalog:
    - id: cashflow-planner
      matched: features
      covers: tem cota-diaria e projeção diária
  github:
    - repo: lipeng3g/BalanceWindow
      stars: 30
      pushed: 2026-08-30
      covers: só projeção, sem orçamento
  blind_spots: []
verdict: exists              # exists | feature | route | standalone
target: cashflow-planner     # the project id or GitHub repo for exists and feature; omitted for route and standalone
why: |
  A cota diária do cashflow-planner já responde à pergunta.
```

Show the record in chat and ask for a yes or for edits; each edit shows the record again. Nothing is written before the yes.

Done when the user said yes to a record whose `candidates` hold every candidate from step 2 and whose `target`, for `exists`, names what already covers the idea.

## 5. Write

On the yes, write the file (create `docs/triage/` when missing) and commit it alone in the home, in the home's commit format: `git -C <home> add <file> && git -C <home> commit -m "<message>" -- <file>`.

Done when `git -C <home> status` shows the record committed. For `exists`, the triage ends here: report the record's path and what covers the idea.
