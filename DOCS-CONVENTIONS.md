# Documentation Conventions — multi-feature, multi-service, multi-version products

Companion to [CONVENTIONS.md](CONVENTIONS.md). The two files are not ranked against each other — they own different subjects. That file owns everything except documentation structure; **this file owns `docs/`** and everything in it. Neither restates the other's rules, so a conflict between them is a bug in one of them rather than a question of precedence.

The one thing inherited from there is the three base rules, restated because everything here derives from them.

1. One fact has one owning file. Everywhere else references it.
2. Docs change in the same commit as the behavior they describe.
3. Decisions are append-only. Supersede, never rewrite.

**Where this comes from:** established practice, not one repo's habits — [Diátaxis](https://diataxis.fr) for splitting doc types by reader intent, [Michael Nygard's Architecture Decision Record format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions), [Keep a Changelog](https://keepachangelog.com), [SemVer](https://semver.org), and docs-as-code (docs in the repo, reviewed in the PR, checked in CI).

---

## 1. The core problem: state vs history

Docs rot because one folder is asked to answer two different questions at once:

| Question | Answer type | Lives in | Edit rule |
|---|---|---|---|
| What is true **now**? | State | `product/`, `services/`, `reference/` | Rewritten freely, always describes HEAD |
| What happened and **why**? | History | `adr/`, `releases/` | Append-only, frozen once written |

Keep them physically separate. A file is one or the other, never both.

**Corollary — do not fork internal docs per version.** `docs/v1/`, `docs/v2/` looks organized and guarantees drift: a fix lands in one copy, the other silently lies. Internal state docs describe HEAD only.

**But "check out the git tag" is not an acceptable substitute.** Forcing a reader into git archaeology to compare v1.2 against v2.0 is a real failure and the most common way this model gets applied badly. The version story must be legible at **one commit — HEAD — as ordinary readable text**. That is what inline version annotations (§6) deliver: each item carries its own version annotations, in the file you are already reading.

The test: *can someone answer "what changed for feature X between v1.2 and v2.0" without running a single git command?* If no, the docs are broken however clean HEAD looks.

**Exception — snapshot copies for external docs.** Published user-facing docs, where customers still run old versions, legitimately do fork per version: Docusaurus `versioned_docs/`, MkDocs `mike`. That is the norm for a public docs site and not a mistake. The line is audience, not taste:

| Audience | Approach | Why |
|---|---|---|
| Internal (team, agents) | HEAD only + inline annotations | only HEAD is true; copies rot unread |
| External (customers on old versions) | Snapshot per version | the v1 page is still true for a real user |

If you do snapshot, take the ecosystem's own advice: most projects need no versioning at all, keep actively built versions under 10, and link older ones as frozen external URLs rather than rebuilding them.

A **public API contract old clients still call** is the same exception in miniature: version it under `reference/api/v1/`, and only it.

## 2. Reader intent (Diátaxis)

Before structure, decide what a page is *for*. Four types, never mixed in one file:

| Type | Reader is | Example |
|---|---|---|
| **Tutorial** | Learning, needs a guaranteed-success path | "Build your first pipeline" |
| **How-to** | Working, has a specific goal | "Rotate the API key" |
| **Reference** | Working, needs a fact | Endpoint list, data dictionary |
| **Explanation** | Studying, wants understanding | "Why we chose event sourcing" |

Most rot comes from a reference page growing tutorial prose, or a how-to guide explaining rationale that belongs in an ADR. When a page feels bloated, it usually has two types in it — split, do not trim.

## 3. Structure

```
docs/
  README.md                  # the DOCS INDEX — not the repo root README.
                             # Index + maintenance rules + support policy (§6),
                             # reading order, source-of-truth order.
                             # status: living. Start here.

  product/                   # product-wide state — true across all services
    brief.md                 # problem, solution, boundaries. One page.
    requirements.md          # PROB, GOAL, FR-CORE, NFR, traceability matrix
    acceptance.md            # AC, EVAL targets, measurement definitions
    roadmap.md               # what is planned, not what exists

  services/                  # one folder per deployable unit
    <service>/
      README.md              # what it is, owner, dependencies, how to run
      requirements.md        # FR-<SVC>-nnn — behavior this service owns
      api.md                 # its contract: endpoints, events, schemas
      runbook.md             # operate it: deploy, rollback, alerts, on-call

  features/                  # only for a feature spanning 2+ services
    <feature>/spec.md        # end-to-end flow, which service owns which step

  adr/                       # decisions, append-only, product-wide numbering
    README.md                # register table: ID, title, status, date
    NNNN-<slug>.md

  releases/
    CHANGELOG.md             # Keep a Changelog format, newest first
    vX.Y.Z.md                # per-release notes: shipped IDs, migration, rollback

  checklists/                # fixed procedure per kind of work. Ticked every
    feature.md               # time that work is done, by a human or an agent,
    bugfix.md                # so sessions stay consistent with each other.
    refactor.md              # Max 10 items each.
    new-service.md
    release.md
    deprecation.md
    issue-proposal.md
    go-public.md
    pr-review.md

  milestones/                # only when the repo has no GitHub remote.
    vX.Y.md                  # Execution state for one version. Deleted at
                             # release. See CONVENTIONS.md §7.

  reference/                 # facts: data dictionary, API schema, glossary
  guides/                    # tutorials + how-to: setup, contributing, testing
  archive/                   # frozen docs of removed features. Never edited.

  discovery/                 # NOT official documentation. No front matter, no
                             # status, no review, no CI, no naming rules.
                             # Product discovery, option analysis, argument over
                             # a technical or product decision, prototypes,
                             # mockups, wireframes, any draft. Governs nothing.
```

Rules on the shape:

- A folder appears when it has content. Do not scaffold empty directories.
- `adr/` is the only folder that grows for the life of the project. Everything else stays roughly constant in file count. Nothing is ever moved out of it; §7 keeps the register readable instead.
- `features/` is for cross-service flows only. A feature inside one service is documented in that service's `requirements.md`.
- `roadmap.md` describes intent. Nothing else in `docs/` may describe a future state as if it exists.

### `checklists/` — one fixed procedure per kind of work

A guide is read once to learn something. A checklist is ticked every time the work is done. Different lifecycle, so a different folder.

Their real value is **consistency across sessions**. Without them, the same task done twice — by you in two different weeks, or by two agent sessions — follows two different procedures, and whichever step one of them skipped is the one that breaks. `bugfix.md` existing means every bug fix starts with a failing test, whoever is doing it.

One file per kind of work. All nine ship in `docs/checklists/` already — cut and add per this repo rather than starting from nothing. The set that earns its keep:

| File | What is specific to it |
|---|---|
| `feature.md` | the FR has an AC, the AC has a test, the version annotation is added |
| `bugfix.md` | a failing test before the fix, always |
| `refactor.md` | behavior unchanged, and the tests are **not** edited — if they had to be, it was not a refactor |
| `new-service.md` | ID prefix registered, runbook written, `docs/README.md` updated |
| `release.md` | changelog, release note, tag, annotation pruning |
| `deprecation.md` | the three-release path in §6 |
| `issue-proposal.md` | the approach is approved in chat, then posted as an issue comment, before any code |
| `go-public.md` | ticked once, the one time this repo is flipped from private to public |
| `pr-review.md` | only what the author cannot establish about their own work |

**Never restate the Definition of Done.** `CONVENTIONS.md` §10 is the universal gate for every change. A checklist holds only what is specific to its kind of work and points at §10 for the rest. Copying it into six files is the duplication this whole convention exists to prevent.

**Keeping them from bloating.** A checklist grows one line per incident and nobody ever deletes one. At forty items nobody reads it, so it catches nothing — the same failure as an ADR register past fifty, or annotations on every sentence. Five rules:

- **Ten items maximum.** Adding an eleventh means removing one or automating one. The cap forces the trade instead of letting it ratchet. A checklist split into phases ticked at different times — `deprecation.md` runs once per release across three releases — caps at ten **per phase**, because the reason for the cap is how much someone reads in one sitting.
- **If CI can check it, it is not a checklist item.** Write the check instead. Checklists are for what a machine cannot verify — which is the same division §8 draws.
- **One incident is not enough to earn a line.** Add on the second occurrence, or the file becomes an incident log.
- **Items are actions, not reminders.** "Be careful with migrations" cannot be ticked, so it can never be removed either. "Run `alembic upgrade head` against a copy of production data" can.
- **Prune on a fixed cadence.** Each release, delete any item that has never once caught anything. If you cannot recall it catching something, it has not.

### `discovery/` — the unofficial half

Every other folder here holds settled material with an owner, a status and a review path. Real work does not start settled: options get weighed, sketches get drawn, arguments get had. That work needs a home, or it pollutes the formal docs as a permanently-`draft` requirements file, or it leaves the repo for a chat thread and is lost.

`discovery/` is that home. **It is exempt from nearly every rule in this file** — no front matter, no `status`, no owner, no review ladder, no ID ownership, no CI checks, no `updated` discipline. Friction is what stops people exploring, so there is none here.

What belongs: product discovery and user research, option analysis before a decision, the argument over an architecture or product choice, prototypes, mockups, wireframes, scratch notes, anything draft.

Four rules, and they exist only to stop the folder corrupting the rest:

- **It governs nothing.** Nothing in `discovery/` is a source of truth. If someone justifies a change by citing a discovery note, that is a defect: the conclusion must be promoted to an ADR or written into its owning document first, and cited from there.
- **Links run one way.** Discovery may link into the formal docs. Formal docs may not link into discovery — the reviewed set must not depend on unreviewed content. The single exception is an ADR's **Context** section, which may cite the note the reasoning came from, explicitly labelled as research rather than authority.
- **Promote, never migrate.** When discovery produces a decision, write a new ADR. When it produces a requirement, write it in the owning document. The discovery file stays exactly where it is, unedited. Do not dress a note up as official by moving it.
- **Staleness is not a bug here.** The "stale docs are bugs" rule in §9 does not apply. A discovery note is a snapshot of thinking at a moment, and being outdated is its normal end state. Let it age.

**Name files however you like.** No pattern, no prefix, no required structure — subfolders, loose files, whatever suits the work. This is the one folder with no naming rule, and that is deliberate: a naming convention is friction, and friction is exactly what stops people writing the note at all. Git records when each file was written if the date ever matters. Nothing is deleted on a schedule either — an ADR may be citing it as provenance.

**This is the one folder a small project needs early.** A two-week lab has no requirements matrix and no release history, but it does make choices worth a paragraph. `discovery/` is where they go before there is anywhere else.

**Monorepo alternative:** put service docs at `services/<svc>/docs/` next to the code instead of under `docs/services/`. Co-location makes the same-commit rule near-automatic and is the better default for a monorepo. Pick one per repo, state which in `docs/README.md`. Split placement is the worst of both.

## 4. Front matter

Every file under `docs/` starts with the block below — except anything in `discovery/`, which carries no front matter at all (§3):

```yaml
---
status: draft | in-review | approved | superseded | removed | living
updated: 2026-09-10
owner: <name or team>
approved-by: peer | self (built) | self (cold read)
                          # required once status is `approved` — says how it
                          # was checked, so a reader knows what the label cost
since: v1.2.0             # optional: when this DOCUMENT became true.
                          # Per-item versions are annotated inline — see §6a.
applies-to: [auth, api]   # optional: services, if not obvious from path
---
```

- `updated` must be at least as recent as the last content change. CI checks it against `git log`.

Front matter is cheap and machine-checkable. Skip it only at tier 0 (§10).

### Status values

`status` answers one question: **how much can a reader trust this file?** It describes the document, never the feature the document describes — a `draft` page can describe shipped code, and an `approved` page can describe something not built yet.

`draft` is not a substitute for `discovery/`. A `draft` file is on the ladder and headed for `approved`; a discovery note is on no ladder and may never become anything.

| Status | Trust it? | Means | Who moves it here |
|---|---|---|---|
| `draft` | no | Being written. May be wrong, incomplete, or contradict another doc. Do not build from it. | author, freely |
| `in-review` | partly | Content complete, correctness not yet confirmed by anyone but the author. Safe to read, not safe to cite as settled. | author, when they stop editing |
| `approved` | yes | Someone other than the author read it and agreed. This is the source of truth for its area. | the reviewer named in `owner` |
| `superseded` | historical | No longer current, replaced by a named successor. Kept so old references still resolve. | whoever approved the successor |
| `removed` | historical | Describes something that no longer exists in the product. Kept so old IDs and release notes still resolve. | whoever shipped the removal |
| `living` | yes | Has no end state and is never "finished" — an index, a changelog, a backlog. Correct by continuous maintenance, not by review. | set once, at creation |

Rules:

- `living` is **not a rung on the review ladder.** It is a statement that the file has no destination. A backlog cannot be `approved`, because approving it would freeze the one thing that must keep changing.
- `superseded` and `removed` files **stay in place**, never deleted. Both carry a forward link: `superseded` to its replacement, `removed` to the release that dropped it. Deleting them breaks every citation in git history, release notes, test names, and commit messages.
- `approved` must **cost something to reach**, or every file ends up approved and the label carries no information. What it costs depends on who is on the project — see below.

### Approving on a solo project

Most repos here have one person. A rule requiring a second reviewer would leave every file stuck at `in-review` forever, which destroys the signal just as thoroughly as approving everything. The requirement is not literally a second person; it is **an independent check the author cannot fake by being confident**. Three qualify, strongest first:

| Mode | `approved-by` | What makes it independent |
|---|---|---|
| Another person read it | `peer` | someone else's judgment |
| Reality confirmed it | `self (built)` | the thing described is built, runs, and is in use — evidence, not opinion |
| Cold read | `self (cold read)` | the author re-read it with the content out of working memory |

**Prefer `self (built)` whenever it applies.** Running code is a harder check than a colleague skimming a page. `self (cold read)` is for documents describing something not yet built — requirements, specs, plans — where no reality exists to check against yet.

**What makes a read "cold".** Not elapsed time — displaced memory. Immediately after writing, the whole document is still in your head, so you read what you *meant* to write rather than what you wrote, and the gaps fill themselves in. That is why nobody proofreads their own text well.

Approving in the same working session is allowed, provided something displaced the content first. In increasing order of effectiveness:

- **Finish one other real task in between.** The minimum bar. Another file, another problem, heavy enough to occupy the space. Not a five-minute break.
- **Read it in a different form.** Rendered output instead of source. Breaking visual familiarity catches noticeably more.
- **Read against a checklist, not freely.** Free reading becomes skimming. A checklist forces specific attention: every ID defined, every link alive, every claim sourced.
- **Have an agent read it and ask it questions a new reader would ask.** Not to approve it — an agent cannot be accountable — but wherever it answers wrong, the document is unclear. Fastest option inside a one-day lab.

Writing and approving in one sitting with no displacement is not a cold read. It is self-certification. Leave the file at `in-review` and say so.

### Allowed transitions

```
draft ──> in-review ──> approved ──> superseded
                            │
                            └──────> removed

living  (set at creation, never moves)
```

- Backwards is allowed only `in-review → draft`, when review finds the content needs real rework rather than edits.
- `approved → draft` is not allowed. To change an approved document, edit it and move it back to `in-review`.
- `superseded` and `removed` are terminal. Nothing leaves them. If a removed feature returns, it gets a **new ID and a new file**, cross-linked to the old one — see §6a1 for the row layout and the one exception, a quick revert. §5 covers why IDs are never reused.

### ADRs use a different set

Decision records carry `proposed | approved | superseded` and nothing else. This is deliberate, not an oversight:

| Absent value | Why an ADR cannot have it |
|---|---|
| `draft` | an unfinished decision is not a decision; keep it in a pull request until it is one |
| `in-review` | a decision is accepted or it is not — there is no partly-decided |
| `removed` | decisions are append-only; a reversed decision becomes `superseded`, never deleted |
| `living` | a decision has an end state by definition; that is what makes it a decision |

`proposed` is the one value unique to ADRs: the decision is written and argued but not yet accepted. Code that depends on it waits (§7).

## 5. ID conventions

IDs are how one fact gets referenced from everywhere without being copied.

| Prefix | Means | Owned by |
|---|---|---|
| `PROB-nnn` | Problem statement | `product/requirements.md` |
| `GOAL-nnn` | Goal | `product/requirements.md` |
| `FR-CORE-nnn` | Product-wide functional requirement | `product/requirements.md` |
| `FR-<SVC>-nnn` | Service-scoped functional requirement | `services/<svc>/requirements.md` |
| `NFR-nnn` | Non-functional requirement | `product/requirements.md` |
| `AC-nnn` | Acceptance criterion | `product/acceptance.md` |
| `ADR-nnnn` | Decision | `adr/NNNN-<slug>.md` |

Hard rules:

- An ID is defined **exactly once**, in its owning file. Referenced elsewhere by ID or relative link.
- **IDs are never reused and never renumbered.** A removed requirement becomes `status: removed` in place. Renumbering breaks every reference in git history, release notes, test names, and commit messages.
- Service prefixes come from a fixed list in `docs/README.md`. Adding a service means adding its prefix there first.
- ADR numbering is product-wide, not per-service — one sequence keeps ordering meaningful.

**Traceability chain.** Every must-have requirement walks end to end:

```
PROB-003  >  GOAL-002  >  FR-AUTH-011  >  AC-024  >  tests/test_auth.py::test_refresh_token_rotates
```

`product/requirements.md` carries the matrix. Test names cite the AC ID. A requirement with no AC is not shippable; an AC with no test is not verified.

**Cost warning:** a hand-maintained traceability matrix is real overhead and goes stale fast without the CI check in §8. Adopt IDs when the same requirement is being cited from three or more places, not before.

## 6. Versions

Where multi-version products break down. Four mechanisms, each with one job:

### Supported versions — define this before anything else here

Three rules in this section depend on knowing which versions are still supported: when to delete a behavior-change block (a3), when to prune annotations (a), and whether external docs need snapshots at all (§1). Without a written answer, all three become judgment calls, and a judgment call under time pressure always resolves to "leave it" — so annotations accumulate forever.

**A supported version is one you still commit to fixing, or one real users still run.** Both halves count. A version nobody runs but you still promise to patch is supported. A version you have stopped patching but people still run is not supported, yet its users still need warnings in the docs.

This is a **product decision, not a documentation decision.** Write it once, in `docs/README.md`, and let every rule here point at it. Four common shapes:

| Shape | Policy | Fits |
|---|---|---|
| **Latest only** | only the deployed build is supported | SaaS, internal tools, a single deployment |
| **N-1 / N-2** | current major plus one or two back | libraries, SDKs, public APIs |
| **Time-based** | 12 or 18 months from release date | enterprise software with procurement cycles |
| **LTS** | a few designated releases supported for years, the rest briefly | platforms, runtimes, operating systems |

**Most repos here are Latest only.** One deployment, no old clients, so the oldest supported version is always HEAD. That makes pruning mechanical — at each major, drop everything the rules below allow — and makes the external-snapshot exception in §1 inapplicable. The question only gets hard when you ship something other people install or call.

**a. Inline version annotations — the primary mechanism.** Every versioned item carries its own version information, in place, in the file a reader already has open. Nothing is copied and nothing requires git. This is how Python's docs, MDN, and the Rust standard library handle it.

There are **three different forms of annotation**, not three levels of one thing. Which you use is decided by the shape of the content, not by how much detail you want:

| Form | Applies to | Name for it |
|---|---|---|
| **a1** | items listed in a table | `Since` / `Until` columns |
| **a2** | behavior described in sentences | **markers** — the four strings below |
| **a3** | a change someone must migrate across | behavior-change block |

Throughout this file, **marker** means an a2 string and nothing else. The general word for all three is **annotation**.

**a1. Per-ID columns.** Requirement and feature tables get `Since` and `Until` columns. This is the workhorse — it makes every table a version map at no extra maintenance cost, because you are editing the row anyway.

```markdown
| ID | Requirement | Since | Until | Status | Note |
|---|---|---|---|---|---|
| FR-AUTH-004 | Session cookie login | v1.0.0 | v2.0.0 | removed | returned as FR-AUTH-021 in v3.0.1 |
| FR-AUTH-009 | Password reset by email | v1.0.0 | — | approved | |
| FR-AUTH-011 | Refresh-token rotation | v1.2.0 | — | approved | |
| FR-AUTH-021 | Session cookie login | v3.0.1 | — | approved | returns FR-AUTH-004, removed in v2.0.0 (ADR-0061) |
```

`—` in `Until` means still live. A removed row **stays in the table**; it is never deleted, because deleting it is exactly what forces the reader back into git. `Note` is empty for the ordinary case and carries cross-row links for the exceptions below.

**When a removed item comes back.** An item dropped in v2.0.0 and reintroduced in v3.0.1 gets a **new ID and a new row**, as FR-AUTH-021 does above. Do not try to fit the gap into one row: `Since`/`Until` can express exactly one continuous interval, and notation like `v1.0.0–v2.0.0, v3.0.1–` is hard to check mechanically and hard to read. Two rows keep one interval each, and the history lives in the **link between them**.

That link must run **both ways** — old row names its successor, new row names its predecessor and the version that dropped it. One direction is not enough, because readers usually arrive from the old side, following a citation in the v2.0.0 release notes.

Why not reuse `FR-AUTH-004`: the v2.0.0 notes would say "removed FR-AUTH-004" and the v3.0.1 notes "added FR-AUTH-004", with nothing to tell a reader whether that is a return or a contradiction. Every existing citation in tests, commits and ADRs would also become ambiguous about which era it meant.

**Exception — a revert is not a return.** If the removal was a mistake and is undone quickly with the contract unchanged (dropped in v2.0.0, restored in v2.0.1), keep the original ID, clear `Until` back to `—`, and record the gap in `Note`: `absent in v2.0.0 only`. Here the hole in one row is the honest record, and minting a new ID for a corrected mistake only creates litter.

Decide between the two with one question: **did the contract change?** Changed means a new ID. Unchanged, and merely restoring something dropped in error, means keep the ID.

Either way, two things are mandatory. The **changelog records both events** — under `Removed` in v2.0.0 and under `Added` in v3.0.1, with the v3.0.1 line naming the old ID. And the return gets **its own ADR**, because reversing a shipped removal is an expensive decision that overturns an earlier one; the ADR that removed it becomes `superseded`.

**a2. Inline badges in prose.** Where behavior is described in sentences rather than rows, mark the sentence:

```markdown
Tokens rotate on every use. <sup>Added in v1.2.0</sup>

Sessions may also be held in a cookie.
<sup>Deprecated in v1.4.0, removed in v2.0.0 — use refresh-token rotation (FR-AUTH-011).</sup>
```

Keep the marker vocabulary to four strings, so it is greppable and checkable: `Added in vX.Y.Z`, `Changed in vX.Y.Z`, `Deprecated in vX.Y.Z`, `Removed in vX.Y.Z`. A `Deprecated` or `Removed` marker must name its replacement.

**a3. Behavior-change blocks.** Only when the old behavior still matters to someone reading today — a migration in progress, a client on the old contract. Keep it adjacent to the current text, visibly subordinate to it:

```markdown
### Token lifetime

Access tokens expire after 15 minutes. <sup>Changed in v2.0.0</sup>

> **Before v2.0.0:** tokens expired after 24 hours and did not rotate.
> Clients pinned to v1.x still see that behavior. Migration: ADR-0042.
```

Delete the block once the old version is no longer supported. It is a migration aid, not an archive — the changelog is the archive.

**Front-matter `since:` is file-level and too coarse on its own.** It says when a *document* became true, which almost never matches when a *feature* did. Keep it, but never let it be the only version signal in a file that describes more than one item.

**Cost and limit.** Annotations are cheap to write and cheap to keep correct, because they live on the line being edited. What they cannot do is show you a whole release at a glance — for that, read the changelog (b) and the release note (c). Annotations answer "when did *this* change"; changelogs answer "what changed in *this release*". You need both.

**Pruning.** At each major release, drop `Added in` markers for versions below the oldest supported one. Keep `Deprecated` and `Removed` markers until the removal itself falls out of support. This applies to a2 markers only — a1 table rows are never deleted (see the removed-row rule above), and a3 blocks have their own deletion rule.

**Precondition — never prune a fact the changelog does not already record.** Before deleting a marker, check that the changelog entry for its version actually describes the change the marker is attached to, not merely that the version has a heading. If it does not, either add it to the changelog first or keep the marker. Deleting a marker whose fact exists nowhere else destroys it.

Three reasons, in order of weight:

- **Annotations everywhere are annotations nowhere.** A marker's job is to stop the eye: *this changed recently, re-check your assumptions*. When most sentences carry one, they become wallpaper and the eye skips all of them — including the one that mattered, like `Removed in v4.0.0`. Keeping too many markers destroys the thing markers are for.
- **They answer a question nobody is asking.** `Added in v1.2.0` helps someone deciding whether the version they run has the feature. Once nothing below v3 is supported, the answer is always yes, and the marker is taking up space to say nothing.
- **Every marker is a constraint CI must check.** Each one must name a version that exists in `CHANGELOG.md` (§8). Dead markers cost check time and can still break a build.

**What pruning costs, stated honestly.** A version fact is *state* while someone can still be affected by it, and *history* once nobody can. §1 says those live in different places, so pruning is a move rather than a delete — but the move is lossy, and pretending otherwise is how conventions lose trust.

What survives, and what does not:

| | Before pruning | After pruning |
|---|---|---|
| Granularity | sentence — this exact behavior | feature — the changelog entry it belonged to |
| How you read it | inline, on the line you are already on | scan the changelog by release |
| Exact answer still recoverable | yes | `git blame`, not the docs |

The precision loss is real: a marker annotates one sentence, a changelog entry usually covers a whole feature. A nuance that was a detail inside a larger entry becomes unrecoverable from the docs alone.

That trade is worth taking because of the first reason above — markers that never get pruned stop being read, so keeping all of them costs more than losing some precision. And nothing is destroyed outright: git holds every version of every line permanently. §1 argues git should not be the **routine** interface, not that git is useless. For a question asked once every couple of years, `git blame` is a fine answer.

**Why `Added` is dropped but `Deprecated` and `Removed` are kept.** `Added in` is *information* — it says a thing exists. `Deprecated in` and `Removed in` are *warnings* — they say a thing will break. A warning has to outlive the change it warns about, because people arrive late. Someone still on v2 reading the v4 docs needs to know the thing they depend on is gone.

**b. `releases/CHANGELOG.md`** — Keep a Changelog format, newest first, grouped `Added / Changed / Deprecated / Removed / Fixed / Security`. Each entry cites the IDs it moved:

```markdown
## [1.3.0] - 2026-09-10
### Added
- Refresh-token rotation (FR-AUTH-011, AC-024, ADR-0042)
### Removed
- Legacy session cookies (FR-AUTH-004, deprecated in 1.1.0, ADR-0039)
```

**c. `releases/vX.Y.Z.md`** — one file per release, written at release time, frozen after. Holds what a changelog line is too short for: migration steps, breaking-change detail, known issues, rollback procedure.

**d. Git tags are the fallback, not the interface.** Tag every release, so the exact doc set at v1.2.0 is always recoverable. But a reader should reach for a tag only to recover a full historical snapshot — never to answer an everyday question like "when did this change?". If tags are the routine answer, the annotations in (a) are missing or stale.

**Deprecation path — three releases, never fewer:**

| Release | What happens |
|---|---|
| N | Add `deprecated-in: vN`, name the replacement. Behavior unchanged. |
| N+1 | Warn at runtime. Changelog under `Deprecated`. Docs point at the replacement. |
| N+2 | Remove. `status: removed`, `until:` set, doc moves to `archive/`. Changelog under `Removed`, breaking change in release notes. |

Never remove and announce the removal in the same release. Under SemVer the removal itself forces a major bump.

## 7. ADRs (Architecture Decision Records)

**What an ADR is.** A short document recording one decision that shaped the system: what forced the choice, what was chosen, and what it costs. One decision per file, numbered, never edited after approval.

**What problem it solves.** Code shows *what* the system does; it cannot show what else was considered, what constraint ruled those out, or what was knowingly traded away. Without that record, every past choice looks arbitrary to whoever arrives next — including you in six months, and including an AI agent reading the repo cold. The usual result is someone "fixing" a deliberate decision, hitting the original constraint again, and paying for the lesson twice.

**Why a file in the repo and not a chat thread or a ticket.** It is versioned with the code it explains, it survives people leaving and tools being cancelled, and it is reviewable in the same pull request as the change it justifies.

**What it is not.** Not a design doc (a decision is not a plan), not a task, not a work log. If it does not record a *choice between alternatives*, it is not an ADR.

The format is Michael Nygard's, from 2011, and is near-universal. One decision per file, four sections, fixed:

```markdown
---
status: proposed | approved | superseded
updated: 2026-09-10
owner: <who accepted it>
---

# ADR-0042: Rotate refresh tokens on every use

## Status
Approved by <who> on <date>. Supersedes ADR-0031.

## Context
What forced a decision. Constraints. What was true at the time.

## Decision
One sentence, present tense. What we do.

## Consequences
What this costs, what it forecloses, what now needs to happen.
```

- Write an ADR when a choice is **expensive to reverse**, or when someone will later ask "why is it like this?". Not for routine implementation choices.
- **Never edit an approved ADR's Context or Decision.** To change course, write a new ADR saying `Supersedes ADR-NNNN`, and set the old one to `superseded` with a forward link. The old reasoning staying readable is the entire value.
- `adr/README.md` holds a register table kept in sync with the files. Split it as the count grows — see below.
- An ADR that gates unwritten code stays `proposed` until decided. Do not implement past a `proposed` ADR.

**Sprawl warning.** ADRs are the easiest thing here to overdo. Past roughly 50 on a single product, the register stops being scannable and people stop searching it — at which point the decisions are archived, not communicated. If the count is climbing fast, the bar for "expensive to reverse" has slipped. Group related choices into one ADR rather than splitting each into its own.

### Retiring superseded ADRs

`adr/` grows for the life of the project and nothing is ever deleted from it, so the register — not the folder — is what has to be kept readable.

**Split the register. Do not move the files.** A superseded ADR is cited from commits, code comments, other ADRs and release notes. Moving it to `adr/archive/0031-*.md` breaks every one of those relative links, which is a worse problem than the one it solves. The principle: **the register is the interface, the folder is storage.** When browsing gets hard, fix the interface.

`adr/README.md` carries two tables instead of one:

```markdown
## Active decisions
| ID | Title | Date | Area |
|---|---|---|---|
| ADR-0042 | Rotate refresh tokens on every use | 2026-09-10 | auth |

## Superseded
| ID | Title | Superseded by | Date |
|---|---|---|---|
| ADR-0031 | Long-lived refresh tokens | ADR-0042 | 2026-04-02 |
```

Files stay at `adr/NNNN-<slug>.md` forever and no link ever breaks. The top table shows only what currently governs, which is what someone consulting the register actually wants. The bottom table keeps the retired reasoning findable for anyone asking why the current decision exists.

**Add an `Area` column and sort by it.** Fifty rows ordered by number cannot be scanned. The same fifty split across eight topic areas can. Areas come from the same fixed list as the service prefixes in `docs/README.md`.

A `proposed` ADR belongs in neither table. Keep it in a short third list at the top, because an undecided decision is the one thing a reader must not mistake for settled.

## 8. Automate what a reviewer cannot see

A `scripts/check_docs.py` run in CI, wired as a test (`tests/test_docs.py`) so it runs with the normal suite rather than as a step people forget. **`discovery/` is excluded from every check below**, except the one that guards the boundary:

- [ ] Every doc has valid front matter with an allowed `status`.
- [ ] Every ID is defined exactly once, in its owning file.
- [ ] Every referenced ID resolves to a definition.
- [ ] Every must-have FR appears in the traceability matrix.
- [ ] The ADR register matches the ADR files and their statuses.
- [ ] Every `superseded` ADR sits in the register's Superseded table, and its `Superseded by` names an ADR that exists.
- [ ] Every ADR named as a superseder actually says `Supersedes ADR-NNNN` in its own Status section.
- [ ] Every relative link resolves to a file that exists.
- [ ] Every `updated` date is at least as recent as that file's last commit.
- [ ] No orphan doc: every file is reachable from `docs/README.md`. Files under `discovery/` are exempt.
- [ ] No file outside `discovery/` links into it, apart from an ADR's Context section.
- [ ] Every a2 marker uses one of the four allowed strings and a version that exists in `CHANGELOG.md`.
- [ ] Every a2 marker's fact is recorded in that version's changelog entry — its ID is cited there, or the entry describes the same behavior. Without this, pruning silently destroys facts.
- [ ] `docs/README.md` declares one of the four support policies in §6.
- [ ] Every `Deprecated in` / `Removed in` marker names a replacement.
- [ ] Every ID with an `Until` version also appears under `Removed` in that release's changelog entry, unless its `Note` marks it as a revert.
- [ ] Every cross-row `Note` link resolves, and its counterpart names it back.

Off-the-shelf alternatives worth using instead of hand-rolling: `lychee` or `markdown-link-check` for links, `vale` for prose style, `markdownlint` for formatting. Write custom code only for the ID and traceability rules, which no generic tool knows about.

## 9. Maintenance rules

- **Same-commit rule** (base rule 2). Behavior change and doc change ship together, in one commit — not merely in one pull request, which most repos here do not have. A change touching behavior and no doc gets asked why.
- **Owning-file rule.** Before writing a fact, find who owns it. If it exists, link. If not, decide the owner and write it once.
- **No copy-paste between docs.** A duplicated sentence is a future contradiction.
- **Stale docs are bugs.** File them as bugs. A `refinement-checklist.md` under `product/` keeps known gaps visible instead of rediscovered. This does not apply to `discovery/`, where going out of date is normal.
- **Reading order is declared** in `docs/README.md`, separately for a new human contributor and for a coding agent. Agents read the owning doc for the area they touch, not the whole folder.
- **The support policy is declared** in `docs/README.md` too, as one of the four shapes in §6. Every pruning and deletion rule in this file resolves against it.
- **Source-of-truth order is written down**, so conflicts resolve without debate: ADRs, then the owning document, then architecture, then everything else.

## 10. Grow into this, do not start here

The full structure fits a product with services and a release history. It is wrong for a two-week lab, and most of the repos here are labs. Add a tier when the pain it solves actually shows up:

| Tier | Trigger | Add |
|---|---|---|
| 0 | Any repo | `README.md`, plus `docs/discovery/` as soon as a choice is worth a paragraph |
| 1 | Second contributor, or code outlives one sitting | `docs/adr/`, front matter, `docs/checklists/bugfix.md` |
| 2 | Requirements outgrow the README | `docs/product/` with FR/AC IDs and the matrix, and the `approved` status |
| 3 | Second deployable service | `docs/services/<svc>/`, service ID prefixes |
| 4 | First external consumer or real release | `docs/releases/`, CHANGELOG, deprecation policy |
| 5 | Docs get contradicted twice | `scripts/check_docs.py` in CI |

Adding a tier later is cheap — IDs can be introduced without renaming anything. The expensive mistakes are the two this file exists to prevent: forking docs per version, and letting the same fact live in three files.

**Below tier 2, drop `approved` entirely.** Use `draft | living | superseded | removed` only. A short solo lab has no review step worth modelling, and a status nobody can reach is worse than one that does not exist. Fewer values, each meaning something.
