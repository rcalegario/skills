"""graph.py: a task's items, requirements, decisions, features and validations as nodes and edges."""
from conftest import write

import graph
import state

ALPHA = "tasks/skills/2026-11-12-0900-alpha/"

ACS = """\
- id: AC-1
  text: "The thing works."
  requirements:
    - id: AC-1.1
      text: "it works"
      decision: D-01
      validations: [V-01]
    - id: AC-1.2
      text: "it lasts"
      decision: D-09
      validations: [V-09]
"""

D02 = """\
id: D-02
title: "Child"
status: decided
born_from: [D-01]
"""

D03 = """\
id: D-03
title: "Old way"
status: superseded
superseded_by: D-02
born_from: [D-01, D-01]
"""

V02 = """\
id: V-02
title: "Spike"
status: pending
decides: [D-02, D-77]
"""

ROADMAP = """\
milestones:
  - id: M1
    title: One
    features:
      - id: F1.1
        title: Built
        decisions: [D-02]
      - id: F1.2
        title: Planned
        status: planned
        decisions: [D-01, D-88]
"""

FEATURE = """\
id: F1.1-built
roadmap: F1.1
status: building
story:
  decisions: [D-02]
  validations: [V-01, V-99]
"""

LOOSE = """\
id: X-loose
status: draft
story:
  decisions: [D-01]
"""


def build(home):
    write(home, ALPHA + "acs.yaml", ACS)
    write(home, ALPHA + "decisions/D-02-child.yaml", D02)
    write(home, ALPHA + "decisions/D-03-old.yaml", D03)
    write(home, ALPHA + "validations/V-02-spike.yaml", V02)
    write(home, ALPHA + ".specs/roadmap.yaml", ROADMAP)
    write(home, ALPHA + ".specs/features/F1.1-built/feature.yaml", FEATURE)
    write(home, ALPHA + ".specs/features/X-loose/feature.yaml", LOOSE)
    task, data = state.collect(str(home / ALPHA))
    return graph.build(task, data)


def test_nodes_and_edges_of_every_kind(home):
    g = build(home)
    nodes = {n["id"]: n for n in g["nodes"]}
    assert nodes["AC-1"]["kind"] == "item"
    assert nodes["AC-1.1"]["kind"] == "requirement"
    assert {d: nodes[d]["status"] for d in ("D-01", "D-02", "D-03")} == {
        "D-01": "open", "D-02": "decided", "D-03": "superseded"}
    assert nodes["V-02"]["kind"] == "validation" and nodes["V-02"]["status"] == "pending"
    assert nodes["F1.1"] == {"id": "F1.1", "kind": "feature", "status": "building", "label": "F1.1"}
    assert nodes["F1.2"]["status"] == "planned"
    assert nodes["X-loose"]["kind"] == "feature" and nodes["X-loose"]["status"] == "draft"
    assert all(n["label"] == n["id"] for n in g["nodes"])
    edges = {(e["source"], e["target"]) for e in g["edges"]}
    assert {
        ("AC-1", "AC-1.1"), ("AC-1", "AC-1.2"),   # item -> requirement
        ("AC-1.1", "D-01"),                       # requirement -> root decision
        ("AC-1.1", "V-01"),                       # requirement -> validation
        ("D-01", "D-02"), ("D-01", "D-03"),       # born_from parent -> child
        ("D-03", "D-02"),                         # superseded -> superseding
        ("D-02", "F1.1"), ("D-01", "F1.2"),       # roadmap decisions -> feature
        ("D-01", "X-loose"),                      # story decisions -> feature without a roadmap entry
        ("F1.1", "V-01"),                         # story validations -> feature -> validation
        ("V-02", "D-02"),                         # spike -> decision
    } <= edges


def test_unknown_ids_and_duplicate_edges_are_dropped(home):
    g = build(home)
    ids = {n["id"] for n in g["nodes"]}
    assert not {"D-09", "V-09", "D-77", "D-88", "V-99"} & ids
    assert all(e["source"] in ids and e["target"] in ids for e in g["edges"])
    pairs = [(e["source"], e["target"]) for e in g["edges"]]
    assert len(pairs) == len(set(pairs))
    assert pairs.count(("D-02", "F1.1")) == 1  # named by the roadmap and by the story
    assert pairs.count(("D-01", "D-03")) == 1  # born_from lists D-01 twice


def test_task_detail_carries_the_graph(home):
    detail = state.task_detail(str(home), "skills", "2026-11-12-0900-alpha")
    assert {n["id"] for n in detail["graph"]["nodes"]} >= {"AC-1", "AC-1.1", "D-01", "V-01"}
    assert {"source": "AC-1.1", "target": "D-01"} in detail["graph"]["edges"]
