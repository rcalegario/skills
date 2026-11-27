"""Checks skills.yaml, the record of each own skill and the skills it was built from.

Usage: python scripts/skills.py [--root DIR] validate | credits [--write] | test-cmd <skill> | test-cmds
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

RELATIONS = ("fork", "derived", "inspired")
WORDING = {"fork": "fork of", "derived": "derived from", "inspired": "inspired by"}
START, END = "<!-- credits:start -->", "<!-- credits:end -->"
SHA = re.compile(r"^[0-9a-f]{7,40}$")


def load(root):
    return yaml.safe_load((root / "skills.yaml").read_text(encoding="utf-8")) or {}


def own_entries(manifest):
    return manifest.get("own") or []


def skill_test_cmds(manifest):
    """Each own skill's name mapped to its test command, "" when it has none."""
    return {e.get("name"): e.get("test") or "" for e in own_entries(manifest)}


def reference_errors(skill, i, ref, own_names):
    where = f"{skill}: reference {i + 1}"
    errors = []
    if ref.get("relation") not in RELATIONS:
        errors.append(f"{where}: relation must be one of {', '.join(RELATIONS)}")
    if "skill" in ref:
        if ref["skill"] not in own_names:
            errors.append(f"{where}: skill '{ref['skill']}' is not an own skill")
        return errors
    if not ref.get("repo"):
        errors.append(f"{where}: an external reference needs repo (or skill: for an own skill)")
    commit = str(ref.get("commit", ""))
    if commit != "unknown" and not SHA.match(commit):
        errors.append(f"{where}: commit must be a 7-40 char hex sha or 'unknown'")
    return errors


def installed_errors(installed, own_names):
    errors = []
    seen = set()
    for i, item in enumerate(installed):
        name = item.get("name")
        where = f"installed: entry {i + 1}" + (f" ({name})" if name else "")
        if not name:
            errors.append(f"{where}: needs a name")
        elif name in own_names:
            errors.append(f"{where}: '{name}' is an own skill")
        elif name in seen:
            errors.append(f"{where}: '{name}' is listed twice")
        seen.add(name)
        if item.get("origin") == "unknown":
            continue
        missing = [k for k in ("repo", "path", "commit") if not item.get(k)]
        if missing:
            errors.append(f"{where}: needs {', '.join(missing)} (or origin: unknown)")
        elif not SHA.match(str(item["commit"])):
            errors.append(f"{where}: commit must be a 7-40 char hex sha")
    return errors


def reference_line(ref):
    took = f" - {ref['took']}" if ref.get("took") else ""
    relation = WORDING.get(ref.get("relation"), ref.get("relation"))
    if "skill" in ref:
        return f"- {relation} [{ref['skill']}](skills/{ref['skill']}){took}"
    repo = ref["repo"].rstrip("/")
    commit = str(ref.get("commit", "unknown"))
    path = ref.get("path", "")
    name = "/".join(repo.split("/")[-2:])
    if path:
        name += " · " + path.rstrip("/").split("/")[-1]
    ref_name = "HEAD" if commit == "unknown" else commit
    url = f"{repo}/tree/{ref_name}/{path}".rstrip("/").replace("(", "%28").replace(")", "%29")
    meta = [ref["license"]] if ref.get("license") else []
    meta.append("commit unknown" if commit == "unknown" else f"`{commit}`")
    return f"- {relation} [{name}]({url}) ({', '.join(meta)}){took}"


def credits(manifest):
    lines = [START, "<!-- Generated from skills.yaml by `python scripts/skills.py credits --write`. -->", ""]
    for entry in own_entries(manifest):
        lines += [f"### {entry.get('name')}", ""]
        refs = entry.get("references") or []
        lines += [reference_line(r) for r in refs] or ["- No outside references."]
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def replace_credits(readme, section):
    if START not in readme or END not in readme:
        return None
    head, rest = readme.split(START, 1)
    return head + section + rest.split(END, 1)[1]


def credits_errors(root, manifest):
    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").exists() else ""
    expected = replace_credits(readme, credits(manifest))
    if expected is None:
        return [f"README.md: no {START} / {END} markers for the credits"]
    if expected != readme:
        return ["README.md: credits differ from skills.yaml; run `python scripts/skills.py credits --write`"]
    return []


def validate(root):
    manifest = load(root)
    entries = own_entries(manifest)
    own_names = {e.get("name") for e in entries}
    folders = {p.name for p in (root / "skills").iterdir() if p.is_dir() and not p.name.startswith(".")}
    errors = []
    for name in sorted(folders - own_names):
        errors.append(f"skills/{name}: no own entry in skills.yaml")
    for name in sorted(own_names - folders):
        errors.append(f"{name}: own entry has no folder under skills/")
    for entry in entries:
        for i, ref in enumerate(entry.get("references") or []):
            errors.extend(reference_errors(entry.get("name"), i, ref, own_names))
    errors.extend(installed_errors(manifest.get("installed") or [], own_names))
    if not errors:
        errors.extend(credits_errors(root, manifest))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    credits_cmd = sub.add_parser("credits")
    credits_cmd.add_argument("--write", action="store_true")
    test_cmd = sub.add_parser("test-cmd")
    test_cmd.add_argument("skill")
    sub.add_parser("test-cmds")
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        errors = validate(args.root)
        for e in errors:
            print(e)
        if errors:
            return 1
        print("skills.yaml OK")
        return 0
    if args.cmd == "credits":
        section = credits(load(args.root))
        if not args.write:
            print(section)
            return 0
        readme_path = args.root / "README.md"
        updated = replace_credits(readme_path.read_text(encoding="utf-8"), section)
        if updated is None:
            print(f"README.md: add {START} and {END} where the credits go", file=sys.stderr)
            return 1
        readme_path.write_text(updated, encoding="utf-8", newline="\n")
        return 0
    if args.cmd == "test-cmd":
        cmds = skill_test_cmds(load(args.root))
        if args.skill in cmds:
            print(cmds[args.skill])
            return 0
        print(f"{args.skill}: not an own skill", file=sys.stderr)
        return 1
    if args.cmd == "test-cmds":
        # One call for every skill, so the pre-commit hook starts one process instead of one per skill.
        print(json.dumps(skill_test_cmds(load(args.root))))
        return 0


if __name__ == "__main__":
    sys.exit(main())
