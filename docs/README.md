---
status: living
updated: 2026-11-03
owner: HieuQuang4438
---

# Docs index — vn-tax-law-rag

Rules for everything in this folder: `DOCS-CONVENTIONS.md` at the repo root.
This file is the index and the place where this repo's two policy choices are declared.
It is **not** the repo root `README.md`, which covers setup and how to run.

## Declare these two before writing docs

**Supported versions.** Pick one of the four forms in `DOCS-CONVENTIONS.md` §6 and state it here.
Version annotations older than the oldest supported version are pruned, so nothing below this
line can be answered without it.

> Supported: none, pre-release

**Progress tracking.** One mechanism, never both — `CONVENTIONS.md` §7.

> Tracking: GitHub issues and milestones

## Reading order

1. `product/brief.md` — the problem and the boundaries, one page.
2. `product/requirements.md` — PROB, GOAL, FR, NFR and the traceability matrix.
3. `product/acceptance.md` — AC and measurable targets.
4. `adr/README.md` — why things are the way they are.
5. The service or feature doc the task actually touches.

## Source of truth, in order

When two documents disagree, the one higher in this list wins and the lower one is a bug:

1. `adr/` — a decision, once approved, outranks any description of it.
2. `product/requirements.md` and `product/acceptance.md` — what the product owes.
3. `services/<service>/requirements.md` and `api.md` — what one unit owes.
4. `features/<feature>/spec.md` — cross-service flow.
5. `reference/`, `guides/` — derived. Never the authority for behavior.

`discovery/` is outside this list. It governs nothing.

## Folders

Only folders with real content exist. The rest are created when their first file is written —
`DOCS-CONVENTIONS.md` §3 describes all of them and where each kind of file belongs.

| Folder | Holds | Present |
|---|---|---|
| `adr/` | decisions, append-only, product-wide numbering | yes |
| `checklists/` | fixed procedure per kind of work, ticked every time | yes |
| `releases/` | `CHANGELOG.md` and per-release notes | yes |
| `product/` | product-wide state: brief, requirements, acceptance, roadmap | when written |
| `services/` | one folder per deployable unit | when there are 2+ |
| `features/` | only a feature spanning 2+ services | when one exists |
| `reference/` | data dictionary, schemas, glossary | when written |
| `guides/` | tutorials and how-tos | when written |
| `discovery/` | unofficial: drafts, option analysis, prototypes. No status, no CI | when used |
| `milestones/` | execution state per version. Only with no GitHub remote | if no remote |
| `archive/` | frozen docs of removed features. Never edited | on first removal |
