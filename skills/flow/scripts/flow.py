#!/usr/bin/env python3
"""flow.py - state changes and structure checks for a /flow feature.

Commands:
  status  <feature>                         progress and the frontier (tasks ready to start)
  check   <feature>                         validate feature.yaml and spec.md; exit 1 on any error
  approve <feature> spec|tasks              record the user's approval (M: `spec` approves both)
  set     <feature> T<n> doing|verifying [--commit X]
                                            start a task, or record its commit (HEAD by default): it then waits for its checks
  set     <feature> AC<n> pass|fail         record the result of a criterion's checks; a task is done once every
                                            check of the criteria it covers passes (never set by hand)
  finding <feature> --text T --source S [--severity --confidence --file --line --hunk --fix --comment-id N]
                  [--action fix --task T3 | --action wontfix --reason R]
                                            record a review finding in review.yaml with the next R-n id
  finding <feature> R-n --action fix --task T3 | --action wontfix --reason R
                                            set or change the outcome of finding R-n
  finding <feature> --none --axes spec,standards
                                            record a clean review (findings: []) and the axes that ran;
                                            size M and L need both spec and standards
  pr      <feature> --url U                 record the pull request that delivers the feature
  review  <feature>                         every task verifying or done: building -> review
  finish  <feature>                         every check pass and review recorded: review -> done
  roadmap [--approve]                       validate <specs>/roadmap.yaml, write the status of every feature and milestone
                                            into it, show progress and the features ready to start;
                                            --approve stamps today as `approved` once it is valid
  new     <feature> --title T --size S|M|L [--roadmap F] [--repo R] [--decisions D-1,D-2] [--validations V-1] [--test CMD]
                                            create the draft feature.yaml and spec.md

<feature> is a folder name under <specs>/features/, a folder path, or a path to feature.yaml.
<specs> is --specs, default <root>/.specs; --root is the git repository the task commits live in.
A feature's roadmap status comes from the feature.yaml whose `roadmap:` names it, and the script writes it
back into roadmap.yaml (with the milestone status) after every command that changes a feature.
"""
import argparse
import os
import sys

try:
    import yaml  # noqa: F401  (only to say how to install it; the modules below read the files)
except ImportError:
    sys.stderr.write("flow.py needs PyYAML (pip install pyyaml). Without it, check the file by reading it.\n")
    sys.exit(2)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", ".."))
from roadmap import cmd_roadmap, sync_roadmap  # noqa: E402
from review import AXES, CONFIDENCES, REQUIRED_AXES, SEVERITIES, SOURCES, cmd_finding  # noqa: E402
from feature import SIZES, default_specs, resolve  # noqa: E402
from progress import cmd_set  # noqa: E402
from commands import (cmd_approve, cmd_check, cmd_finish, cmd_new, cmd_pr, cmd_review,  # noqa: E402
                      cmd_status)


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".", help="git repository of the task commits (default: current directory)")
    parser.add_argument("--specs", help="folder holding roadmap.yaml and features/ (default: <root>/.specs)")
    sub = parser.add_subparsers(dest="command")
    sub.required = True
    for name in ("status", "check", "review", "finish"):
        sub.add_parser(name).add_argument("feature")
    approve = sub.add_parser("approve")
    approve.add_argument("feature")
    approve.add_argument("step", choices=("spec", "tasks"))
    set_ = sub.add_parser("set")
    set_.add_argument("feature")
    set_.add_argument("target", help="a task id (T1) or a criterion id (AC1)")
    set_.add_argument("value", help="doing | verifying for a task, pass | fail for a criterion")
    set_.add_argument("--commit", help="with verifying: record this commit instead of HEAD (for resume)")
    roadmap = sub.add_parser("roadmap")
    roadmap.add_argument("--approve", action="store_true", help="stamp today as the approval date, once the roadmap is valid")
    finding = sub.add_parser("finding")
    finding.add_argument("feature")
    finding.add_argument("target", nargs="?", help="R-n: set or change the outcome of that finding")
    finding.add_argument("--text")
    finding.add_argument("--action", choices=("fix", "wontfix"))
    finding.add_argument("--task", help="with fix: the task that fixes it")
    finding.add_argument("--reason", help="with wontfix: why, as the user agreed")
    finding.add_argument("--none", action="store_true", help="record a clean review (findings: []); needs --axes")
    finding.add_argument("--axes", help="with --none: the review axes that ran, comma separated (%s); size M and L "
                         "need %s" % (", ".join(AXES), " and ".join(REQUIRED_AXES)))
    finding.add_argument("--source", choices=SOURCES,
                         help="where the finding comes from; a bot review (Copilot) is pr-comment")
    finding.add_argument("--comment-id", type=int, help="with pr-comment: the id of the PR comment")
    finding.add_argument("--severity", choices=SEVERITIES)
    finding.add_argument("--confidence", choices=CONFIDENCES)
    finding.add_argument("--file", help="the file the finding points at, as it stands at HEAD ('-' when none)")
    finding.add_argument("--line", type=int, help="the line in that file at HEAD")
    finding.add_argument("--hunk", help="the quoted code or spec line")
    finding.add_argument("--fix", help="the suggested fix, in one sentence")
    pr = sub.add_parser("pr")
    pr.add_argument("feature")
    pr.add_argument("--url", required=True, help="the pull request that delivers the feature")
    new = sub.add_parser("new")
    new.add_argument("feature", help="the folder name and id, e.g. F1.1-csv-export")
    new.add_argument("--title", required=True)
    new.add_argument("--size", required=True, choices=SIZES)
    new.add_argument("--roadmap", help="the roadmap feature id this delivers")
    new.add_argument("--repo", help="repo name, when the work is a /task story")
    new.add_argument("--decisions", help="task decisions it builds on, comma separated")
    new.add_argument("--validations", help="task validations that prove it, comma separated")
    new.add_argument("--test", help="the whole-suite command")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    specs = os.path.abspath(args.specs) if args.specs else default_specs(root)
    if args.command == "roadmap":
        return cmd_roadmap(specs, args.approve)
    if args.command == "new":
        return cmd_new(specs, args)
    path = resolve(args.feature, specs)
    if args.command == "finding":
        return cmd_finding(path, args, root)
    if args.command == "pr":
        return cmd_pr(path, args.url)
    if args.command == "approve":
        code = cmd_approve(path, root, specs, args.step)
    elif args.command == "set":
        code = cmd_set(path, root, specs, args.target, args.value, args.commit)
    else:
        code = {"status": cmd_status, "check": cmd_check, "review": cmd_review,
                "finish": cmd_finish}[args.command](path, root, specs)
    if code == 0 and args.command in ("approve", "set", "review", "finish"):
        sync_roadmap(specs)
    return code


if __name__ == "__main__":
    sys.exit(main())
