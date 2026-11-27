"""graph.py - one task's links as nodes and edges, for the Graph tab.

Nodes are the task's items, requirements, decisions, validations and features (every roadmap feature,
planned ones included, and any spec'd feature the roadmap does not list). Edges follow the story:

    item -> requirement -> root decision -> child decision (born_from) -> feature -> validation
    requirement -> validation, spike -> decision (decides), superseded -> superseding decision

An edge naming an id the task does not define is left out, and each edge appears once.
"""


def lst(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def key(feat):
    """A feature's node id: its roadmap id, or its folder name when the roadmap does not list it."""
    return feat["roadmap"] or feat["id"]


def build(task, data):
    """{nodes: [{id, kind, status, label}], edges: [{source, target}]} from status.py's Task and its collect()."""
    nodes = {}

    def node(ident, kind, status):
        if ident is not None and str(ident) not in nodes:
            nodes[str(ident)] = {"id": str(ident), "kind": kind, "status": status, "label": str(ident)}

    for item in data["items"]:
        node(item["id"], "item", item["status"])
    for req in data["requirements"]:
        node(req["id"], "requirement", req["status"])
    for d, dec in task.decisions.items():
        node(d, "decision", dec.get("status"))
    for v, val in task.validations.items():
        node(v, "validation", val.get("status"))
    # A spec'd feature's status is its feature.yaml's; the roadmap only adds the features not spec'd yet.
    for feat in data["features"]:
        node(key(feat), "feature", feat["status"])
    for ms in data["roadmap"]:
        for feat in ms["features"]:
            node(feat["id"], "feature", feat.get("status") or "planned")

    edges, seen = [], set()

    def edge(source, target):
        pair = (str(source), str(target))
        if pair[0] in nodes and pair[1] in nodes and pair not in seen:
            seen.add(pair)
            edges.append({"source": pair[0], "target": pair[1]})

    for item in data["items"]:
        for rid in item["requirements"]:
            edge(item["id"], rid)
    for req in data["requirements"]:
        edge(req["id"], req["decision"])
        for val in req["validations"]:
            edge(req["id"], val["id"])
    for d, dec in task.decisions.items():
        for parent in lst(dec.get("born_from")):
            edge(parent, d)
        for newer in lst(dec.get("superseded_by")):
            edge(d, newer)
    for rid, feat in task.roadmap.items():
        for d in lst(feat.get("decisions")):
            edge(d, rid)
    for feat in data["features"]:
        for d in feat["decisions"]:
            edge(d, key(feat))
        for v in feat["validations"]:
            edge(key(feat), v)
    for v, val in task.validations.items():
        for d in lst(val.get("decides")):
            edge(v, d)
    return {"nodes": list(nodes.values()), "edges": edges}
