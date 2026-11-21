---
name: Feature
about: One committed requirement. Filed by a human, per CONVENTIONS.md §7.
title: "FR-<AREA>-<nnn> <short name>"
labels: feature
---

**Spec:** `docs/<path>.md#<anchor>`

**Work:** <what gets built, in one or two sentences. Point at the spec; do not restate it.>

**Done when:** <the AC id and its test; the spec the test encodes in the same commit as the failing test, and the docs describing what was delivered in the same commit as the behavior.>

**Depends on:** <#issue numbers, ADR ids, or "nothing">

**Out of scope:** <the nearby thing this issue is not doing, and where it goes instead.>

<!--
Spec is a path with an anchor, never a place to write the spec — one fact has one
owning file. If there is no owning document yet, that is the first piece of work,
not something to paste in here.
Carries a design choice? docs/checklists/issue-proposal.md before any code.
-->
