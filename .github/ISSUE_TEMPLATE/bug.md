---
name: Bug
about: Behavior that contradicts a document. Filed by a human, per CONVENTIONS.md §7.
title: "<area>: <what goes wrong>"
labels: bug
---

**Spec:** `docs/<path>.md#<anchor>` — the document this contradicts.

**Seen in:** <which run, which results file, which configuration: commit, time limit, seed, model, dataset. A bug report without its configuration cannot be reproduced.>

**Cases:**

- <input or state → observed, versus expected. One line each. Numbers, not adjectives.>

**Work:** <find the cause, fix the implementation. Never relax the checker or the test to make the result pass.>

**Done when:** <a test that fails before the fix and passes after, using the cases above; the affected docs updated.>

**Until fixed:** <what a user sees in the meantime, and whether anything downstream is unsafe to trust.>

**Depends on:** <#issue numbers, or "nothing">

**Out of scope:** <the improvement this bug makes tempting. Fixing the defect is not the place to also make the thing better — that is a separate issue.>
