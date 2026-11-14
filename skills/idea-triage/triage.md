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
