# skills

Agent skills I wrote or forked, for Claude Code and other agents that read `SKILL.md` folders.

| Skill | What it does |
|---|---|
| `flow` | Lean feature workflow: spec, tasks, one commit per task, every criterion proved by a check |
| `task` | A versioned task folder that carries work from its base text to a draft PR |
| `spec-lite` | Lightweight spec-driven flow for personal and small projects |
| `tlc-spec-driven` | Fork of tech-leads-club's spec-driven skill |
| `idea-triage` | Triage new ideas against a catalog of projects |
| `retro-report` | Retro over the sessions no retro has read yet, with its fixes tracked as a roadmap |
| `code-review` | Review a diff on separate axes, with structured findings that `/flow` can record |

## Install

```sh
npx skills add rcalegario/skills
```

## Credits

What each skill is built from. Edit `skills.yaml`, then run `python scripts/skills.py credits --write`.

<!-- credits:start -->
<!-- Generated from skills.yaml by `python scripts/skills.py credits --write`. -->

### flow

- derived from [tlc-spec-driven](skills/tlc-spec-driven) - Criteria proved by checks, with every gate enforced by a tested script
- derived from [spec-lite](skills/spec-lite) - YAML state for roadmap and features, changed only through the script
- inspired by [humanlayer/skills · show-me](https://github.com/humanlayer/skills/tree/4d69d20f6e9b/plugins/show-me/skills/show-me) (MIT, `4d69d20f6e9b`) - Shapes, flows and changes shown as visuals in the docs people read

### task

- inspired by [mattpocock/skills · grilling](https://github.com/mattpocock/skills/tree/95249b0b4978/skills/productivity/grilling) (`95249b0b4978`) - Decisions asked in rounds over a design tree, each with a recommended answer
- inspired by [mattpocock/skills · to-spec](https://github.com/mattpocock/skills/tree/5c89081d4bbe/skills/engineering/to-spec) (`5c89081d4bbe`) - Turning a base text into outcomes and requirements before any code
- inspired by [mattpocock/skills · to-tickets](https://github.com/mattpocock/skills/tree/9e2abf8611a3/skills/engineering/to-tickets) (`9e2abf8611a3`) - Splitting the work into slices that each ship on their own

### code-review

- derived from [mattpocock/skills · code-review](https://github.com/mattpocock/skills/tree/5863806dd4e1/skills/engineering/code-review) (MIT, `5863806dd4e1`) - Two parallel axes (Standards with a Fowler smell baseline, Spec) reported apart, never reranked

### spec-lite

- derived from [tlc-spec-driven](skills/tlc-spec-driven) - Spec, tasks, execute and validate per feature, made lighter for personal projects

### tlc-spec-driven

- fork of [tech-leads-club/agent-skills · tlc-spec-driven](https://github.com/tech-leads-club/agent-skills/tree/8658b66/packages/skills-catalog/skills/%28development%29/tlc-spec-driven) (CC-BY-4.0, `8658b66`) - The whole skill at upstream 4.1.0; local changes are listed in its MODS.md
- derived from [humanlayer/skills · show-me](https://github.com/humanlayer/skills/tree/4d69d20f6e9b/plugins/show-me/skills/show-me) (MIT, `4d69d20f6e9b`) - A copy of show-me in references/show-me.md, credited in its header

### idea-triage

- No outside references.

### retro-report

- derived from [mattpocock/skills · retro](https://github.com/mattpocock/skills/tree/5863806dd4e1/skills/engineering/retro) (`5863806dd4e1`) - The improvement categories a retro looks for and who fixes what, implementation or review
- inspired by [microsoft/TokenEconomizer · trace](https://github.com/microsoft/TokenEconomizer/tree/7042ea8/tokeneconomizer/trace) (Apache-2.0, `7042ea8`) - Reading a Claude Code transcript as an ordered list of tool calls with their results
- inspired by [microsoft/TokenEconomizer · observe.py](https://github.com/microsoft/TokenEconomizer/tree/7042ea8/tokeneconomizer/microskills/observe.py) (Apache-2.0, `7042ea8`) - Classifying a command's output into error classes by pattern

<!-- credits:end -->

## License

MIT (see `LICENSE`), except `skills/tlc-spec-driven`, a fork that stays under CC-BY-4.0 with attribution (see Credits and its `MODS.md`).
