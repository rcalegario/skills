"""Checks skills.yaml, the record of each own skill and the skills it was built from.

Usage: python scripts/skills.py [--root DIR] validate | test-cmd <skill>
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

RELATIONS = ("fork", "derived", "inspired")
SHA = re.compile(r"^[0-9a-f]{7,40}$")


def load(root):
    return yaml.safe_load((root / "skills.yaml").read_text()) or {}


def own_entries(manifest):
    return manifest.get("own") or []


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


def validate(root):
    manifest = load(root)
    entries = own_entries(manifest)
    own_names = {e.get("name") for e in entries}
    folders = {p.name for p in (root / "skills").iterdir() if p.is_dir()}
    errors = []
    for name in sorted(folders - own_names):
        errors.append(f"skills/{name}: no own entry in skills.yaml")
    for name in sorted(own_names - folders):
        errors.append(f"{name}: own entry has no folder under skills/")
    for entry in entries:
        for i, ref in enumerate(entry.get("references") or []):
            errors.extend(reference_errors(entry.get("name"), i, ref, own_names))
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=Path(__file__).resolve().parent.parent, type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    test_cmd = sub.add_parser("test-cmd")
    test_cmd.add_argument("skill")
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        errors = validate(args.root)
        for e in errors:
            print(e)
        if errors:
            return 1
        print("skills.yaml OK")
        return 0
    if args.cmd == "test-cmd":
        for entry in own_entries(load(args.root)):
            if entry.get("name") == args.skill:
                print(entry.get("test") or "")
                return 0
        print(f"{args.skill}: not an own skill", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
