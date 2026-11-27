"""roadmap.py - the /flow roadmap: reading and checking roadmap.yaml, the status rule of its features
and milestones, writing those statuses back, and the `roadmap` command.

It imports only lib/ and the standard library, so another skill loads it by its file path
(lib/modules.py) without putting flow's folder on its import path.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from lib import yamlio  # noqa: E402
from lib.yamlio import as_list, list_errors, load_mapping  # noqa: E402
from lib.graph import find_cycle  # noqa: E402
from lib.yamledit import edit, item_blocks, set_key, set_top, split_lines, write_lines  # noqa: E402


def roadmap_path(specs):
    return os.path.join(specs, "roadmap.yaml")


def load_roadmap(specs):
    path = roadmap_path(specs)
    if not os.path.isfile(path):
        return None
    _, data = load_mapping(path)
    return data


def roadmap_features(data):
    """Feature id -> (milestone id, feature dict), in file order."""
    found = {}
    for milestone in as_list(data.get("milestones")):
        if not isinstance(milestone, dict):
            continue
        for feature in as_list(milestone.get("features")):
            if isinstance(feature, dict) and feature.get("id") is not None:
                found.setdefault(str(feature["id"]), (str(milestone.get("id")), feature))
    return found


def features_from(paths, load):
    """{folder name: parsed feature.yaml} for the feature.yaml `paths`, in their order; `load(path)` parses one
    (a caller with its own cache passes its loader), and a file that is not a mapping is left out."""
    found = {}
    for path in paths:
        data = load(path)
        if isinstance(data, dict):
            found[os.path.basename(os.path.dirname(path))] = data
    return found


def _parse_or_none(path):
    try:
        return yamlio.parse(yamlio.read(path), path)
    except (OSError, yamlio.YamlError):
        return None


def linked_features(specs):
    """Roadmap id -> list of (folder name, feature.yaml status)."""
    paths = sorted(glob.glob(os.path.join(specs, "features", "*", "feature.yaml")))
    return links_of(features_from(paths, _parse_or_none))


def links_of(features):
    """Roadmap id -> list of (folder name, status), from {folder name: parsed feature.yaml} in folder order."""
    links = {}
    for folder, data in features.items():
        if isinstance(data, dict) and data.get("roadmap") is not None:
            links.setdefault(str(data["roadmap"]), []).append((folder, data.get("status")))
    return links


def linked_statuses(links):
    """Roadmap id -> the status of the first feature linking it, from linked_features."""
    return {rid: folders[0][1] for rid, folders in links.items()}


def validate_roadmap(data, links):
    errors, warnings = [], []
    err = errors.append
    if not isinstance(data.get("vision"), str) or not data.get("vision").strip():
        err("'vision' is required")
    for e in list_errors(data, ("milestones",), "roadmap.yaml: "):
        err(e)
    milestones = as_list(data.get("milestones"))
    if not milestones:
        err("'milestones' needs at least one milestone")

    milestone_ids, feature_ids = {}, {}
    for i, milestone in enumerate(milestones):
        if not isinstance(milestone, dict) or milestone.get("id") is None:
            err("milestones[%d] needs an 'id'" % i)
            continue
        mid = str(milestone["id"])
        if mid in milestone_ids:
            err("milestone id %s is duplicated" % mid)
        milestone_ids[mid] = []
        for key in ("title", "outcome"):
            if not str(milestone.get(key) or "").strip():
                err("%s needs '%s'" % (mid, key))
        for e in list_errors(milestone, ("features",), "roadmap.yaml: %s " % mid):
            err(e)
        features = as_list(milestone.get("features"))
        if not features:
            err("%s needs at least one feature" % mid)
        for j, feature in enumerate(features):
            if not isinstance(feature, dict) or feature.get("id") is None:
                err("%s features[%d] needs an 'id'" % (mid, j))
                continue
            fid = str(feature["id"])
            if fid in feature_ids or fid in milestone_ids:
                err("id %s is duplicated" % fid)
            feature_ids[fid] = feature
            milestone_ids[mid].append(fid)
            for e in list_errors(feature, ("blocked_by",), "roadmap.yaml: %s " % fid):
                err(e)
            for key in ("title", "goal", "done_when"):
                if not str(feature.get(key) or "").strip():
                    err("%s needs '%s'" % (fid, key))

    graph = {}
    for fid, feature in feature_ids.items():
        deps = []
        for dep in as_list(feature.get("blocked_by")):
            dep = str(dep)
            if dep in milestone_ids:
                deps.extend(d for d in milestone_ids[dep] if d != fid)
            elif dep in feature_ids:
                deps.append(dep)
            else:
                err("%s is blocked by unknown id %s" % (fid, dep))
            if dep == fid:
                err("%s is blocked by itself" % fid)
        graph[fid] = {"blocked_by": deps}
    cycle = find_cycle({f: node["blocked_by"] for f, node in graph.items()})
    if cycle:
        err("blocked_by cycle: %s" % " -> ".join(cycle))

    for rid, folders in links.items():
        if rid not in feature_ids:
            err("%s links roadmap: %s, which is not in the roadmap" % (folders[0][0], rid))
        if len(folders) > 1:
            err("roadmap feature %s is linked by several features: %s (split it in the roadmap)"
                % (rid, ", ".join(f for f, _ in folders)))
    return errors, warnings, graph


# ---------------------------------------------------------------- the status rule

def roadmap_status(rid, linked):
    """The status of roadmap feature `rid`: its linked feature's status, `planned` while none links it.
    `linked` maps a roadmap id to the status of the feature linking it."""
    return linked[rid] if rid in linked else "planned"


def milestone_status(statuses):
    if all(s == "planned" for s in statuses):
        return "planned"
    return "done" if all(s == "done" for s in statuses) else "building"


def statuses(data, linked):
    """The status of every milestone and feature of a roadmap, in file order:
    [(milestone, [(feature, status)], milestone status)], each milestone and feature its mapping.

    It reads even an invalid roadmap: an entry that is not a mapping, or a feature without an id,
    is skipped, and a milestone with no feature left has the status None."""
    found = []
    for milestone in as_list(data.get("milestones")):
        if not isinstance(milestone, dict):
            continue
        features = [(feature, roadmap_status(str(feature["id"]), linked))
                    for feature in as_list(milestone.get("features"))
                    if isinstance(feature, dict) and feature.get("id") is not None]
        found.append((milestone, features, milestone_status([s for _, s in features]) if features else None))
    return found


# ---------------------------------------------------------------- writing and the command

def sync_roadmap(specs, data=None, links=None, text=None):
    """Write the status of every roadmap feature and milestone into roadmap.yaml: nothing when it is invalid
    or every status is already right. `data`, `links` and `text` (the file's LF text) are read when not
    given. Returns the text written, or None when the file was left as it was."""
    data = data or load_roadmap(specs)
    if data is None:
        return None
    links = links if links is not None else linked_features(specs)
    if validate_roadmap(data, links)[0]:
        return None
    path = roadmap_path(specs)
    if text is None:
        text, _ = load_mapping(path)
    wanted = {}
    for milestone, features, state in statuses(data, linked_statuses(links)):
        wanted[str(milestone["id"])] = state
        wanted.update((str(feature["id"]), s) for feature, s in features)

    def change(lines):
        for ident, state in wanted.items():
            start, end, indent = item_blocks(lines, "id", ident)[0]
            set_key(lines, start, end, indent, "status", state, after="title")

    lines = split_lines(text)
    change(lines)
    if "".join(lines) == text:
        return None
    write_lines(path, lines, lambda d: True)
    return "".join(lines)


def cmd_roadmap(specs, approve=False):
    data = load_roadmap(specs)
    if data is None:
        print("ERROR: %s does not exist" % roadmap_path(specs))
        return 1
    links = linked_features(specs)
    errors, warnings, graph = validate_roadmap(data, links)
    for w in warnings:
        print("WARNING: %s" % w)
    for e in errors:
        print("ERROR: %s" % e)
    if errors:
        return 1
    if approve:
        today = yamlio.today()
        text, _ = load_mapping(roadmap_path(specs))
        edit(roadmap_path(specs), text, lambda lines: set_top(lines, "approved", today, after="vision"),
             lambda d: str(d.get("approved")) == today)
        print("Roadmap approved %s" % today)

    sync_roadmap(specs, data, links)
    features = roadmap_features(data)
    linked = linked_statuses(links)
    status = {fid: roadmap_status(fid, linked) for fid in features}
    for milestone in as_list(data.get("milestones")):
        fids = [str(f["id"]) for f in as_list(milestone.get("features"))]
        done = sum(1 for f in fids if status[f] == "done")
        print("%s - %s: %d/%d done" % (milestone.get("id"), milestone.get("title"), done, len(fids)))
        for fid in fids:
            folder = links.get(fid, [("", "")])[0][0]
            print("  %-9s %-6s %s%s" % (status[fid], fid, features[fid][1].get("title"),
                                        "  [%s]" % folder if folder else ""))
    ready = [fid for fid in features if status[fid] == "planned"
             and all(status[d] == "done" for d in graph[fid]["blocked_by"])]
    if ready:
        print("Ready to start: " + ", ".join("%s %s" % (f, features[f][1].get("title")) for f in ready))
    elif all(s == "done" for s in status.values()):
        print("Roadmap complete.")
    return 0
