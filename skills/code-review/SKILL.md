---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag or merge-base) on separate axes, each run by its own sub-agent, and report structured findings that /flow can record. Use when the user wants to review a branch, a PR or work in progress, or asks to \"review since X\"."
---

Review of the diff between `HEAD` and a fixed point the user supplies. Each axis runs as its own **sub-agent with a fresh context window**, so axes do not pollute each other; this skill gathers their findings.

The skill only reads and reports. It edits no file and records nothing: fixes and `flow.py finding` calls belong to whoever called it.

## Why separate axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the spec asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
