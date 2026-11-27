"""summary.py: the step's blockers grouped into the short reason a task row shows."""
import summary


def b(ident, kind, state, waiting=False):
    return {"id": ident, "kind": kind, "state": state, "waiting": waiting}


def text(step, blockers, reason="the reason status.py wrote"):
    return summary.reason({"step": step, "reason": reason, "blockers": blockers, "your_turn": True}, [])["text"]


def test_one_group_per_kind_and_state():
    assert text("decide", [b("D-01", "decision", "open")]) == "D-01 open"
    assert text("decide", [b("D-01", "decision", "open"), b("D-04", "decision", "open")]) \
        == "2 decisions open (D-01, D-04)"
    assert text("spike", [b("V-02", "spike", "pending")]) == "spike V-02 pending"
    assert text("spike", [b("V-02", "spike", "failed"), b("V-03", "spike", "failed")]) \
        == "2 spikes failed (V-02, V-03)"
    assert text("build", [b("F1.1-vm-ssh-key", "feature", "review")]) == "F1.1 in review"
    assert text("build", [b("F1.2", "feature", "planned"), b("F1.3", "feature", "planned")]) \
        == "2 features planned (F1.2, F1.3)"
    assert text("review", [b("AC-1", "item", "built")]) == "AC-1 without pr_note"
    assert text("review", [b("AC-1", "item", "built"), b("X-1", "item", "deciding")]) \
        == "2 items without pr_note (AC-1, X-1)"
    assert text("pr", [b("F1.1-go-skeleton", "feature", "no-pr")]) == "F1.1 without PR"


def test_ids_listed_up_to_three_then_a_range():
    three = [b("F%d.1-x" % n, "feature", "no-pr") for n in (1, 2, 3)]
    assert text("pr", three) == "3 features without PR (F1.1, F2.1, F3.1)"
    six = [b(name, "feature", "no-pr") for name in ("F1.1-go-skeleton", "F1.2-keygen", "F2.1-setup",
                                                    "F2.2-verify-revert", "F2.3-explicit-port", "F3.1-cutover")]
    assert text("pr", six) == "6 features without PR (F1.1–F3.1)"
    assert text("build", [b("mine", "feature", "draft")]) == "mine draft"


def test_groups_join_in_status_order():
    blockers = [b("D-03", "decision", "proposed"), b("D-01", "decision", "open"), b("D-02", "decision", "proposed")]
    assert text("decide", blockers) == "2 decisions proposed (D-03, D-02), D-01 open"
    built = [b("F1.1-a", "feature", "review"), b("F1.2", "feature", "planned"), b("F1.3", "feature", "planned")]
    assert text("build", built) == "F1.1 in review, 2 features planned (F1.2, F1.3)"


def test_consolidate_plan_and_finish_phrases():
    assert text("consolidate", [b("brief.md", "brief", "missing")]) == "no brief"
    assert text("consolidate", [b("brief.md", "brief", "no-date")]) == "brief has no date"
    assert text("consolidate", [b("brief.md", "brief", "no-sources")]) == "brief has no sources"
    assert text("consolidate", [b("decisions", "source", "changed")]) == "brief behind decisions"
    assert text("consolidate", [b("context", "source", "changed"), b("decisions", "source", "changed")]) \
        == "brief behind context, decisions"
    assert text("plan", [b("roadmap.yaml", "roadmap", "missing")]) == "no roadmap"
    assert text("finish", [b("skills", "repo", "worktree")]) == "worktree skills left"
    assert text("finish", [b("a", "repo", "worktree"), b("b", "repo", "worktree")]) == "2 worktrees left (a, b)"


def test_unknown_kind_falls_back_to_the_reason():
    assert text("build", [b("F1.1-a", "feature", "review"), b("x", "gadget", "odd")], "raw words") == "raw words"
    assert text("consolidate", [b("brief.md", "brief", "torn")], "raw words") == "raw words"
    assert text("build", [b("F1.1-a", "feature", None)], "raw words") == "raw words"
    assert text("decide", [b("D-01", "decision", None)], "raw words") == "raw words"
    assert text("finish", [], "every feature has a PR; worktrees remain: none listed") \
        == "every feature has a PR; worktrees remain: none listed"


def test_done_has_no_text():
    assert text("done", [], "no repo has a worktree") == ""


def test_hover_is_the_reason_word_for_word():
    step = {"step": "build", "reason": "F1.1-a is review", "blockers": [b("F1.1-a", "feature", "review")],
            "your_turn": True}
    assert summary.reason(step, []) == {"text": "F1.1 in review", "hover": "F1.1-a is review", "failed": False}


def test_failures_win_on_any_step():
    for step in ("decide", "build", "done"):
        got = summary.reason({"step": step, "reason": "r", "blockers": [], "your_turn": False}, ["one is wrong"])
        assert got == {"text": "1 check failure", "hover": "one is wrong", "failed": True}


# Next actions: the step's blockers worded as what to do, for the task page.

TITLES = {"F1.1-next-and-checks": "Next actions in the JSON", "F1.1": "task-dashboard: next actions",
         "F1.2": "task-dashboard: the Summary tab", "F2.1-solo": "A feature with no roadmap entry",
         "D-01": "How it works", "D-02": "Where the actions are worded", "V-03": "Does it boot",
         "AC-1": "The thing works."}


def acts(step, blockers):
    return summary.next_actions({"step": step, "reason": "r", "blockers": blockers, "your_turn": True},
                                TITLES, {"F1.1-next-and-checks": "F1.1"})


def verbs(step, blockers):
    return [(a["verb"], a["short"], a["name"]) for a in acts(step, blockers)]


def test_next_has_one_action_per_blocker_in_order(home):
    import state
    got = state.task_detail(str(home), "skills", "2026-11-12-0900-alpha")["next"]
    assert got == [{"verb": "Decide", "id": "D-01", "short": "D-01", "name": "How it works", "state": "open",
                    "waiting": False}]
    blockers = [b("F1.1-next-and-checks", "feature", "review", True), b("F1.2", "feature", "planned"),
                b("F2.1-solo", "feature", "draft")]
    assert acts("build", blockers) == [
        {"verb": "Finish review", "id": "F1.1-next-and-checks", "short": "F1.1",
         "name": "task-dashboard: next actions", "state": "review", "waiting": True},
        {"verb": "Spec", "id": "F1.2", "short": "F1.2", "name": "task-dashboard: the Summary tab",
         "state": "planned", "waiting": False},
        {"verb": "Approve spec", "id": "F2.1-solo", "short": "F2.1", "name": "A feature with no roadmap entry",
         "state": "draft", "waiting": False}]


def test_feature_verbs_by_state():
    expected = {"planned": "Spec", "draft": "Approve spec", "approved": "Build", "building": "Build",
                "review": "Finish review", "no-pr": "Open PR for"}
    for state, verb in expected.items():
        assert verbs("build", [b("F1.2", "feature", state)]) == [(verb, "F1.2", "task-dashboard: the Summary tab")]
    # A built feature reads by its roadmap title; without a roadmap entry, by its own title.
    assert verbs("pr", [b("F1.1-next-and-checks", "feature", "no-pr")]) \
        == [("Open PR for", "F1.1", "task-dashboard: next actions")]
    assert verbs("pr", [b("F2.1-solo", "feature", "no-pr")]) \
        == [("Open PR for", "F2.1", "A feature with no roadmap entry")]


def test_decision_spike_item_repo_verbs():
    assert verbs("decide", [b("D-01", "decision", "open"), b("D-02", "decision", "proposed")]) \
        == [("Decide", "D-01", "How it works"), ("Confirm", "D-02", "Where the actions are worded")]
    assert verbs("spike", [b("V-03", "spike", "pending")]) == [("Run spike", "V-03", "Does it boot")]
    assert verbs("spike", [b("V-03", "spike", "failed")]) == [("Rerun spike", "V-03", "Does it boot")]
    for state in ("built", "deciding", "decided"):
        assert verbs("review", [b("AC-1", "item", state)]) == [("Close", "AC-1", "The thing works.")]
    assert verbs("finish", [b("skills", "repo", "worktree")]) == [("Remove worktree", "skills", "")]


def test_brief_and_roadmap_actions():
    got = acts("consolidate", [b("context", "source", "changed"), b("decisions", "source", "changed", True)])
    assert got == [{"verb": "Update brief", "id": "brief.md", "short": "brief.md",
                    "name": "context, decisions changed since brief.md was stamped", "state": "changed",
                    "waiting": True}]
    assert verbs("consolidate", [b("acs", "source", "changed")]) \
        == [("Update brief", "brief.md", "acs changed since brief.md was stamped")]
    assert verbs("consolidate", [b("brief.md", "brief", "missing")]) == [("Write brief", "brief.md", "brief.md")]
    assert verbs("consolidate", [b("brief.md", "brief", "no-date")]) == [("Restamp brief", "brief.md", "brief.md")]
    assert verbs("consolidate", [b("brief.md", "brief", "no-sources")]) \
        == [("Restamp brief", "brief.md", "brief.md")]
    assert verbs("plan", [b("roadmap.yaml", "roadmap", "missing")]) \
        == [("Plan", "roadmap.yaml", "write the roadmap")]


def test_unknown_blocker_reads_resolve():
    blockers = [b("x", "gadget", "odd"), b("F1.2", "feature", None), b("D-01", "decision", "weird"),
                b("V-03", "spike", "passed"), b("brief.md", "brief", "torn"), b("skills", "repo", "gone"),
                b("F1.2", "feature", "planned")]
    got = acts("build", blockers)
    assert len(got) == len(blockers)
    assert [(a["verb"], a["id"], a["state"], a["name"]) for a in got[:-1]] == [
        ("Resolve", "x", "odd", ""), ("Resolve", "F1.2", None, ""), ("Resolve", "D-01", "weird", ""),
        ("Resolve", "V-03", "passed", ""), ("Resolve", "brief.md", "torn", ""), ("Resolve", "skills", "gone", "")]
    assert got[-1]["verb"] == "Spec"
    # An id the task has no name for still reads, with an empty name.
    assert verbs("decide", [b("D-09", "decision", "open")]) == [("Decide", "D-09", "")]


def test_done_has_no_next():
    assert acts("done", []) == []
    assert acts("done", [b("skills", "repo", "worktree")]) == []


# Check groups: status.py's failures and warnings by kind, in plain words, for the Checks card.

def groups(failures, warnings):
    return summary.check_groups(failures, warnings)


def test_checks_grouped_by_kind_failures_first(home):
    import state
    got = state.task_detail(str(home), "skills", "2026-11-12-0900-alpha")["checks"]
    assert got == []
    failures = ["D-02: decided while spike V-04 has not passed",
                "context/now.md: cites D-99, which does not exist",
                "AC-2.1: requirement without a validation",
                "brief.md: cites D-03, superseded by D-05",
                "brief.md: cites D-06, which is dropped",
                "brief.md: block requirements is stale (run `task.py sync`)",
                "D-07: orphan (not in the tree of any requirement)",
                "AC-3.1: requirement without a decision",
                "AC-1.1: status is decided but the decisions, features and validations say built (run `task.py sync`)",
                "F1.2: roadmap status is planned but the features say approved (run `task.py sync`)",
                "AC-4: no status (run `task.py sync`)",
                "brief.md: cites D-98, which does not exist",
                "AC-2.2: requirement without a validation",
                "D-05: decided while spike V-04, V-05 has not passed",
                "brief.md: no requirements block (run `task.py sync`)"]
    warnings = ["D-01: decided and needs code, but no feature links it",
                "V-09: proves no requirement",
                "D-08: decided and needs code, but no feature links it",
                "README: no main repo (old layout); mark one repo with `main: true`"]
    got = groups(failures, warnings)
    assert [(g["severity"], g["title"], g["ids"]) for g in got] == [
        ("failure", "2 decisions decided before their spike passed", ["D-02", "D-05"]),
        ("failure", "2 references to ids that do not exist", ["D-99", "D-98"]),
        ("failure", "2 requirements with nothing to prove them", ["AC-2.1", "AC-2.2"]),
        ("failure", "2 superseded or dropped ids cited in brief.md", ["D-03", "D-06"]),
        ("failure", "brief.md out of sync with the folder", []),
        ("failure", "1 decision outside every requirement's tree", ["D-07"]),
        ("failure", "1 requirement with no decision", ["AC-3.1"]),
        ("failure", "3 statuses out of date", ["AC-1.1", "F1.2", "AC-4"]),
        ("warning", "2 decisions with no feature to build them", ["D-01", "D-08"]),
        ("warning", "1 validation proving no requirement", ["V-09"]),
        ("warning", "README has no main repo", [])]
    for g in got:
        assert g["fix"] and g["kind"] and g["messages"]
    assert got[1]["messages"] == ["context/now.md: cites D-99, which does not exist",
                                  "brief.md: cites D-98, which does not exist"]
    assert got[7]["fix"] == "Run task.py sync."
    assert groups([], ["D-01: decided and needs code, but no feature links it"])[0]["title"] \
        == "1 decision with no feature to build it"


def test_unknown_message_is_its_own_group():
    got = groups(["something odd happened", "D-07: orphan (not in the tree of any requirement)"],
                 ["gate pr: P-1 is still open", "another odd one"])
    assert got == [
        {"severity": "failure", "kind": "other", "title": "something odd happened", "fix": "", "ids": [],
         "messages": ["something odd happened"]},
        {"severity": "failure", "kind": "orphan", "title": "1 decision outside every requirement's tree",
         "fix": got[1]["fix"], "ids": ["D-07"], "messages": ["D-07: orphan (not in the tree of any requirement)"]},
        {"severity": "warning", "kind": "other", "title": "gate pr: P-1 is still open", "fix": "", "ids": [],
         "messages": ["gate pr: P-1 is still open"]},
        {"severity": "warning", "kind": "other", "title": "another odd one", "fix": "", "ids": [],
         "messages": ["another odd one"]}]
