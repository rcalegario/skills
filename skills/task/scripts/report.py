"""The text report status.py prints, rendered from the task's collected state.

render() reads no task file and not the Task: it takes collect()'s plain data and the two things collect()
does not carry, the status of each decision and validation by id, and every root each requirement names
(collect() keeps the first). Loaded by status.py by its file path as task_report."""


def agenda_lines(agenda):
    """The agenda as one line per entry, by person: the Agenda of the report and the open-items block of the brief."""
    out = {}
    for who, entries in agenda.items():
        for e in entries:
            if e["kind"] == "pending":
                line = "%s (pending) %s" % (e["id"], e["title"])
            else:
                line = "%s (%s) %s" % (e["id"], e["status"], e["title"])
                if e["awaits"]:
                    line += " - awaiting spike %s" % ", ".join(e["awaits"])
            out.setdefault(who, []).append(" ".join(line.split()))
    return out


def render(state, statuses, roots):
    """The report: step, items, requirements, features, spikes and agenda.

    state is collect(); statuses is {decision or validation id: its status}, a missing id being unknown;
    roots lists, for each entry of state["requirements"] in order, the root decisions it names."""
    step = state["step"]
    out = ["Step: %s - %s\n" % (step["step"], step["reason"])]
    out.append("# Items\n")
    out.append("| Item | Status | Requirements | Decisions decided | Validations passed |")
    out.append("|---|---|---|---|---|")
    req_lines = []
    # collect() lists the requirements of each item not dropped, in item order
    queue = iter(zip(state["requirements"], roots))
    for item in state["items"]:
        if item["status"] == "dropped":
            continue
        ds, vs = set(), set()
        for req, mine in [next(queue) for _ in item["requirements"]]:
            tree = req["tree"]
            ds |= set(tree)
            vs |= {v["id"] for v in req["validations"]}
            waiting = ["%s (%s)" % (d, statuses.get(d)) for d in tree if statuses.get(d) != "decided"]
            children = [d for d in tree if d not in mine]
            vtxt = ", ".join("%s (%s)" % (v["id"], statuses.get(v["id"], "?")) for v in req["validations"])
            missing = "; ".join(m["text"] for m in req["missing"]) or "-"
            req_lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                req["id"], req["status"], ", ".join(mine) or "-",
                ", ".join(children) or "-", ", ".join(waiting) or "-", vtxt or "-", missing))
        n_dec = sum(1 for d in ds if statuses.get(d) == "decided")
        n_val = sum(1 for v in vs if statuses.get(v) == "passed")
        out.append("| %s | %s | %d | %d/%d | %d/%d |" % (
            item["id"], item["status"], len(item["requirements"]), n_dec, len(ds), n_val, len(vs)))
    out.append("\n# Requirements\n")
    out.append("| Requirement | Status | Root | Children | Not decided | Validations | Missing |")
    out.append("|---|---|---|---|---|---|---|")
    out += req_lines
    if state["features"]:
        out.append("\n# Features\n")
        out.append("| Feature | Status | Decisions | Validations |")
        out.append("|---|---|---|---|")
        for feat in state["features"]:
            out.append("| %s | %s | %s | %s |" % (feat["id"], feat["status"],
                                                 ", ".join(feat["decisions"]) or "-",
                                                 ", ".join(feat["validations"]) or "-"))
    if state["spikes"]:
        out.append("\n# Spikes\n")
        out.append("| Spike | Status | Where | Decides | Blocks features |")
        out.append("|---|---|---|---|---|")
        for spike in state["spikes"]:
            out.append("| %s | %s | %s | %s | %s |" % (
                spike["id"], spike["status"], spike["where"] or "-",
                ", ".join(spike["decides"]), ", ".join(spike["blocks"]) or "-"))
    agenda = agenda_lines(state["agenda"])
    if agenda:
        out.append("\n# Agenda\n")
        for who in sorted(agenda):
            out.append("**%s**" % who)
            out += ["- %s" % line for line in agenda[who]]
            out.append("")
    return "\n".join(out)
