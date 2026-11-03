---
name: Experiment
about: A question answered by measurement, not by argument. Filed by a human.
title: "<area>: <the question>"
labels: experiment
---

**Question:** <one sentence, answerable by a number. "Does X beat Y on Z" — not "try X".>

**Spec:** `docs/<path>.md#<anchor>` — where the metric and the dataset split are defined.

**Setup:** <the configuration, fixed before the run: commit, model, quantization, seed, time limit, dataset version. Anything left unfixed here becomes an uncontrolled variable.>

**Where it runs:** <this machine, or a specific instance type. Creating and deleting cloud resources is the main thread's job with a human's approval — never a subagent's, per §9. Record the machine type next to the numbers.>

**Metric:** <the number that decides, and the threshold that counts as an answer. Decide both before running, or the result gets interpreted to fit.>

**Work:** <the runs to perform and the comparison between them: which configurations, how many seeds, which slice of the data.>

**Done when:** <the record written, with the configuration; the decision taken, or an ADR if an option is dropped for good.>

**Depends on:** <#issue numbers for whatever must exist before the run, or "nothing">

**Out of scope:** <acting on the result. A bad result opens its own issue.>

<!--
Report the bad results too — CONVENTIONS.md §6. A run that disproves the
hypothesis is the experiment working, and filtering it is how a project
convinces itself of something false.
-->
