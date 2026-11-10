# Coding Conventions — vn-tax-law-rag

These are **this repo's** conventions. Seeded from `git-repos/templates/`, owned here. When a rule does not fit this project, edit, add or delete it directly in this file — no approval, and nothing to sync anywhere. There is no copy of this file elsewhere that outranks it.

**Precedence:** this file > tool defaults. `AGENTS.md` holds project facts — what this is, where things live, how to run it. Rules live here. If the two disagree, `AGENTS.md` is the one that is wrong.

**Scope split with [DOCS-CONVENTIONS.md](DOCS-CONVENTIONS.md):** the two files are not ranked against each other — they own different subjects. This file owns everything except documentation structure. That file owns `docs/`: its layout, front matter, IDs, versioning, ADR practice and release records. Neither restates the other's rules, so a conflict between them is a bug in one of them, not a question of precedence.

**Default stack:** Python 3.12 (3.11+ compatible), `pytest`, `python-dotenv`, FastAPI for services, LangChain / Google GenAI / OpenAI SDK for LLM work.

---

## 1. Repo layout

Every code repo uses this skeleton. Do not invent a new shape per project.

```
<repo>/
  README.md            # required: what, how to run, how to test
  AGENTS.md            # required if AI agents touch this repo: project facts
  CLAUDE.md            # one line, `@AGENTS.md` — Claude Code reads this name
  CONVENTIONS.md       # this file. The repo's own rules.
  DOCS-CONVENTIONS.md  # rules for docs/. Drop it if this repo has no docs/.
  WORKLOG.md           # append-only session journal — §8
  .env.example         # required if any secret/config is read
  .gitignore           # required
  .gitattributes       # required: `* text=auto eol=lf`
  .github/
    ISSUE_TEMPLATE/    # feature.md, bug.md, experiment.md, convention-change.md,
                       # config.yml — §7
  requirements.txt     # or pyproject.toml — pick ONE per repo
  src/                 # all importable code (package with __init__.py)
    config.py          # single place that reads env vars
    main.py            # entrypoint (or app.py for Streamlit/FastAPI)
  tests/               # mirrors src/ structure, test_*.py
  data/                # inputs; raw data is gitignored, samples are not
  docs/                # design notes, ADRs, guides.
                       # Full tree for a multi-service product: DOCS-CONVENTIONS.md §3
  scripts/             # one-off / ops scripts, not imported by src/
```

Rules:
- Code that is imported lives in `src/`. Code that is run once lives in `scripts/`.
- No notebooks as the source of truth. Notebooks explore; `src/` implements. Move anything reused into `src/`.
- No generated artifacts committed: `chroma_db/`, `outputs/`, `__pycache__/`, `.venv/`, `*.zip`.

## 2. Environment & dependencies

- One virtualenv per repo, always named `.venv/`. Never install into base/conda root.
  ```bash
  python -m venv .venv
  .venv\Scripts\activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
- Pin with lower bounds (`package>=1.2.0`), not exact pins, unless a version actually breaks.
- New dependency = add to `requirements.txt` / `pyproject.toml` **in the same commit** that uses it.
- Windows notes (this machine): there is no `python3`, use `python`. For anything printing Vietnamese set `PYTHONIOENCODING=utf-8` and open files with `encoding="utf-8"` — default cp1252 mangles it.

## 3. Secrets & config

- **Never** commit a real key. `.env` is gitignored; `.env.example` lists every variable with a dummy value and a one-line comment.
- All env reads happen in `src/config.py` (or equivalent). No `os.getenv()` scattered across modules.
- Fail loud at startup if a required key is missing — do not fall back to a silent default.
  ```python
  # src/config.py
  from dotenv import load_dotenv
  import os

  load_dotenv()

  def required(name: str) -> str:
      value = os.getenv(name)
      if not value:
          raise RuntimeError(f"Missing required env var: {name}")
      return value

  GOOGLE_API_KEY = required("GOOGLE_API_KEY")
  LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
  ```
- Never print or log a key, even truncated. Never paste keys into chat, issues, or commit messages.
- Loose key files (e.g. a plain `keys.txt`) do not belong anywhere in this repo, gitignored or not. Keep secrets in `.env` only.
- **Internal identifiers do not go in a public repo**: machine and VM names, cloud project IDs and resource names, deploy hostnames, client or employer names, documents issued to you by someone else. One public demo link is the exception. These are not secrets — there is nothing to rotate — so none of the rules above reach them; they leak **context** rather than access, and that is still a leak. If `AGENTS.md` says `private` but the repo may ever be flipped to public, this rule applies **from the first commit**, because history is permanent: a name removed later is still in the history, and taking it out means rewriting history, not deleting a file.

## 4. Python style

- Follow PEP 8. `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants.
- Type hints on every public function signature. Return types included.
- Docstrings only where the name is not enough — one line, says *why*, not *what*.
- Functions do one thing. If a function needs a section comment to explain its second half, split it.
- No wildcard imports. Imports grouped: stdlib, third-party, local.
- Prefer `pathlib.Path` over string paths. Prefer f-strings over `%` / `.format()`.
- Data shapes crossing a module boundary are `dataclass` or `pydantic.BaseModel`, not raw dicts.
- Errors: catch the specific exception. A bare `except Exception:` must log the error and re-raise or return a typed failure — never swallow silently.

## 5. LLM / AI-specific rules

These matter more than general style — most repos here are AI projects.

- **Model IDs are config, not literals.** Read from env with a documented default. No `"gpt-4"` hardcoded mid-file.
- **Prompts live in files**, not inline string soup: `src/prompts/<name>.md` or a `prompts.py` module of named constants. A prompt change must be visible in a diff.
- **Every LLM call is wrapped.** One client wrapper per repo that handles: timeout, retry with backoff, and error logging. Nothing calls the vendor SDK directly from business logic.
- **Structured output over parsing prose.** Ask for JSON with a schema (pydantic / `response_schema`) and validate it. Never regex an LLM's free text when structured mode exists.
- **Log every call**: model, prompt name, token counts, latency, and cost if available. Cost surprises come from unlogged loops.
- **Non-determinism is not an excuse for no tests.** Test the deterministic parts (prompt assembly, parsing, routing, guardrails) with mocked responses. Test the model behavior separately in `eval/`.
- **Evals are code.** A quality claim ("accuracy improved") must be reproducible by running a script over a fixed dataset with a recorded score. No claims from a single manual chat.
- Set `temperature=0` for anything expected to be repeatable (extraction, classification, routing).
- Cache/persist expensive artifacts (embeddings, vector stores) outside git; make the build step re-runnable from scratch.

## 6. Testing

- `pytest`. Tests in `tests/`, mirroring `src/`. Files `test_*.py`, functions `test_<behavior>`.
- Test names state behavior: `test_missing_api_key_raises`, not `test_config_2`.
- **The test comes before the implementation, for every change in behavior** — a new feature, a bug fix, a changed default, a changed error. Not only bug fixes. A test written after the code encodes *what the code does* instead of *what was asked for*, and once both exist nobody can tell those apart any more, least of all at review time, which is exactly when it matters.
- **Confirm the test fails for the real reason.** Read the failure. An `ImportError`, a missing fixture, a collection error or a typo in the test name is not a red test — it is a broken test, and implementing against it proves nothing.
- **An agent stops at the red test.** It reports three things — the test, the line of spec the test encodes, and the failure — and then does nothing further until a human says to implement. The human may waive the stop, but a waiver is **explicit and per assignment**: silence is not a waiver, and a waiver on one task does not carry to the next. The stop exists because this is the last moment the test can still be compared against the *requirement*; by the time a PR is reviewed the test and the code agree with each other, and whether either agrees with the spec is no longer visible.
- **Measurement work is exempt from the ordering, and only from the ordering.** An experiment answers with a number, not with behavior, so there is nothing to encode as a test first. Its equivalent gate lives in `.github/ISSUE_TEMPLATE/experiment.md`: the metric, the threshold and the whole configuration are fixed **before** the run. When code that started as an experiment becomes behavior something depends on, it comes back under the rule above.
- No network in unit tests. Mock the LLM/HTTP boundary. Live-API tests go behind a marker:
  ```python
  @pytest.mark.live  # run with: pytest -m live
  ```
- Before saying "done", run the narrowest relevant tests and paste/report the real result. Never report a pass you did not observe.
- **Report the bad results too.** A heuristic that loses to the baseline gets its number and its reason written down, not filtered out. Selective reporting is how a project convinces itself something works.
- **A measurement carries its configuration**, next to the number, every time: time limit, seed, commit, model, quantization, dataset version — whichever of those the number depends on. Without them the number cannot be interpreted or reproduced, so it is not evidence.

## 7. Git

- Branch: `<type>/<short-slug>` — e.g. `feat/rag-reranker`, `fix/env-loading`, `docs/readme-setup`.
  Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
- Commit messages: `<area>: <what changed>`, imperative mood, English, no period. One subject line plus at most a few short bullets.
  ```
  src: add cross-encoder reranking to retrieval
  src: raise on missing GOOGLE_API_KEY instead of defaulting
  docs: document eval dataset format
  repo: ignore personal *.me.md notes
  ```
  `<area>` is the top-level directory touched — `docs`, `src`, `tests`, `scripts`, `data` — or `repo` for a file at the root. Body, when there is one, explains *why*, wrapped at ~72 chars.
- **Conventional Commits** (`feat(rag):`, `fix(config):`) is a valid alternative. Pick one form per repo and say which here; a repo that releases from its commit history has a reason to prefer it.
- **This repo uses `<area>: <what changed>`**, the form above. Conventional Commits is not used here: releases are cut from the milestone (see the release block below), not from the commit history, so its type prefixes would carry no weight. Two early commits, `feat:` and `test:`, predate this declaration and are left as they are.
- One logical change per commit. Do not mix a refactor with a feature.
- Never commit: `.env`, real data dumps, `node_modules/`, `.venv/`, model weights, `*.zip` outputs.
- Branch/push/merge/PR/delete are **human actions**. An agent performs one only when explicitly told to, and does not chain a follow-up git action after it. Committing does not imply permission to push.
- Creating, editing and closing a GitHub issue are **human actions**, for the same reason plus one more: an issue is outward-facing, it notifies people, and GitHub does not let you delete one — a wrong issue is wrong permanently. An agent performs one **only when a human explicitly assigns that specific step**, and does not chain a further issue or git action after it. Assigning "file this one issue" is not permission to file the other nineteen, and closing one issue is not permission to close its siblings. With no explicit assignment, the agent proposes in chat and the human decides.
- Never `--no-verify`, never force-push a shared branch.

### Issue-driven work

For a repo with a GitHub remote, progress lives in issues and milestones — not in a checklist file. A markdown progress list needs manual ticking and therefore drifts; an issue closes because a PR merged, so it cannot.

**Issues track work. Docs hold facts.** Roadmap, requirements, acceptance criteria and ADRs stay as files. Only "how far along are we" moves to the tracker.

Planning, done by a human: one milestone per version, one issue per committed requirement. The issue body **points at the owning document rather than copying it**:

```
Title: FR-AUTH-011 refresh-token rotation
Body:  Spec:         docs/services/auth/requirements.md#fr-auth-011
       Work:         rotate on use, revoke the parent, keep the family id
       Done when:    AC-024 green; docs/services/auth/api.md updated
       Depends on:   #38, ADR-0044
       Out of scope: device fingerprinting — separate issue if needed
```

Those five labels are fixed, and the four templates in `.github/ISSUE_TEMPLATE/` carry them: `feature.md`, `bug.md`, `experiment.md` and `convention-change.md`. A bug adds `Seen in`, `Cases` and `Until fixed`; an experiment adds `Question`, `Setup`, `Where it runs` and `Metric`; a convention change adds `Why` and `Now false`. `config.yml` sets `blank_issues_enabled: false`, so every new issue starts from one of the four — the alternative is what happens without them, which is a different body shape per week.

`convention-change.md` is the only one whose sections are headings instead of bold labels. The other three are built to stay short — `Work:` is one or two sentences pointing at the spec — so a heading would cost three lines for a path. A convention change has no document to point at and runs long, and headings there get anchors worth linking to.

`Spec:` is a path with an anchor, never a place to write the spec. One fact has one owning file (§8), and an issue is not it.

**`Spec:` has an answer at every tier, including a repo with no `docs/`.** FR and AC identifiers and a traceability matrix arrive at Tier 2 of `DOCS-CONVENTIONS.md` §10, so a Tier 0 or Tier 1 repo has nothing to cite yet — and the issue templates are mandatory, because `config.yml` sets `blank_issues_enabled: false`. Point `Spec:` at the narrowest anchor that already exists: a heading in `README.md`, an ADR, a file under `docs/` if the repo has one. If nothing covers it, **the first step of the issue** is writing those few lines into the file that owns them — not moving the spec into the issue body. The spec has to exist outside the issue before any test can claim to encode it; a test written against an issue body encodes something no one reviewed.

The exception is an issue whose work **is** a change to `CONVENTIONS.md` or `DOCS-CONVENTIONS.md`. The owning file is then the file being changed, so "write the spec into the owning file first" would be the entire task. There, `Spec:` points at the section about to change — `CONVENTIONS.md#6-testing` — and the issue body may carry the reasoning for the change, because no other file owns it. `convention-change.md` is the template for that case: it adds `Why` for the reasoning and `Now false` for the sentences elsewhere the change makes wrong.

**A long body does not license renaming the fields.** `Spec`, `Work`, `Done when`, `Depends on` and `Out of scope` keep those exact names in every template, whatever language the prose around them is written in, because the audit step above reads them **by name** before `Closes #N` is written. Rename them and the audit has nothing to take one line at a time, and whoever performs it has to invent a mapping that exists nowhere — which is a claim about the issue that no one can check.

Execution, per issue:

```bash
gh issue list --milestone v1.3 --state open   # what is left
gh issue view 42                              # then open the spec it points to
```

Then branch and write the failing test for the AC. **Stop there and report it** — §6 — because an agent does not run on from a red test to an implementation on its own. Once the test is cleared or the stop is explicitly waived: implement, update the docs in the same commit, add the version annotation and changelog line, and open a PR whose body says `Closes #42`.

**A branch and a PR are the default; working straight on the integration branch is the human's call, taken when the work is assigned.** An agent never picks the path and never proposes one — §9. There is no threshold, because no threshold cuts in the right place: the judgment is about volume, not about kind, so a large documentation change earns a branch exactly as a large code change does. On the direct path the audit below is the only gate.

**Before writing `Closes #N` — in a PR body, a PR title, or a commit message — re-read the issue and diff it against what was done.** Take the issue's `Spec:`, `Work:`, `Done when:` and `Out of scope:` lines one at a time and say, for each, whether the work matches it. Anything that diverged — a different approach, a dropped item, an acceptance line that turned out to be wrong, scope that grew — is a decision taken after the issue was filed, and it goes in an **issue comment first**, before the closing phrase is written anywhere. The comment carries the reasoning; a PR does not restate it, because a decision only reads correctly next to the body it departed from, and a PR closing several issues would otherwise carry pointers into all of them.

The audit is reported, not assumed: an agent states the result line by line, **including the lines that matched**. "No divergence" is a claim about every line, so it is made explicitly or not at all.

The anchor is the moment the closing phrase is **written**, not the moment it fires. It fires on merge, or on a direct push to the integration branch, and the author may not be the one who merges. `.github/workflows/close-issues-on-develop.yml` matches `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves` and `resolved`, so a commit message can arm the close without anyone intending one.

On a direct push there is no PR and therefore no review, so the audit is the only gate on that path: a PR review checklist, where the repo has one, cannot back it up.

Like the subagent bans in §9, this step is **enforced by the prompt, not by the tooling**. No workflow can tell a reasoned deviation from an unreasoned one: that comparison is against the intent in the issue body, which is prose. A CI job here would be a gate in name only, which is worse than none.

**An issue carrying a design choice gets a proposal before any code.** The agent drafts the approach in chat, the human approves or edits it there, and only then is the approved version posted as a comment on the issue. Mechanical work skips this. A new decision taken mid-work — how to handle a measurement, a scope change, a parameter — is posted as a **new** comment before it is acted on; earlier comments are never edited.

A comment is not a source of truth. What is settled goes into the owning document or an ADR, and the commit points there. The procedure and both comment templates are in `docs/checklists/issue-proposal.md`.

Two reasons this is worth the step. A proposal in chat is cheap to reject; a proposal already implemented is not. And the comment thread is the only record of the options that were *not* chosen, which is exactly what is missing when the same question comes back three months later.

**Never close an issue directly.** Let a merge, or a push to the integration branch, close it through `Closes #`, so "done" is tied to committed, tested code rather than to somebody's claim. This is the same rule as §4 of DOCS-CONVENTIONS.md, where a document cannot be approved by the person asserting it is finished.

In this repo work merges into `develop`, while `main` stays the default branch, so GitHub's own `Closes #` handling would wait for the release merge. `.github/workflows/close-issues-on-develop.yml` closes the issue when the PR or commit lands on `develop` instead. Same rule, earlier branch.

At release, the milestone is the release note's source:

```bash
gh issue list --milestone v1.3 --state closed --json number,title
```

**Without a remote, use a file instead** — a repo with no GitHub remote cannot use this at all. Then keep one `docs/milestones/<version>.md`, tick an item only when its AC test is green, and delete the file at release once the release note replaces it. Pick one mechanism per repo and say which in `docs/README.md`. Running both guarantees one of them is lying.

That file tracks *progress*. It is not `docs/checklists/`, which holds the fixed procedure for each kind of work and is ticked afresh every time — see DOCS-CONVENTIONS.md §3.

**On a non-GitHub remote**, read `gh`, PR and `Closes #` throughout this file as whatever that host calls the same thing — on GitLab, `glab`, merge request, and `Closes #` in the MR description. The rules do not change; only the tool names do. Issue templates move to `.gitlab/issue_templates/` and the PR template to `.gitlab/merge_request_templates/`. Both move or neither works: a template left in `.github/` is not read and nothing says so — it just stops appearing. State the substitution once in this file rather than restating every rule.

### Review

**An agent opening the PR means a human reviews it.** That is the common case here, and it is the only configuration in which review catches anything: the author of the code is not the one judging it.

**A human opening the PR has no reviewer**, and §10 is then the whole gate. Say that plainly rather than staging a review to look like one happened — a self-approval records that the step was performed while establishing nothing, which is worse than an honest gap, because later it reads like evidence.

What blocks a merge: a red test, a test that does not encode the spec, a result nobody re-ran, a behavior change with no doc change, and a divergence from the issue that no issue comment covers. Nothing else blocks: an opinion about style becomes a comment and the branch merges anyway. `docs/checklists/pr-review.md` holds the procedure, for a repo that carries it.

## 8. Documentation

The **repo root `README.md`** answers, in this order:
1. What this is, in two sentences.
2. Setup — exact commands, copy-pasteable, including `.env` setup.
3. How to run it.
4. How to test it.
5. Layout — what lives where.

That is a different file from the **docs index** at `docs/README.md`, which indexes `docs/` and is governed by DOCS-CONVENTIONS.md. A repo without a `docs/` folder has only the root README.

**Personal notes are `*.me.md` and gitignored.** They govern nothing: no agent and no reviewer is bound by one, and nothing may cite one as a reason. A note that turns out to matter gets its content moved into the owning spec or an ADR — the note itself is never promoted. This keeps the line between what the repo has decided and what one person was thinking about from blurring.

### Material that does not live in this repo

`*.me.md` is untracked, so it has no history and no backup and must not be depended on. That leaves a gap: material worth versioning that still cannot sit in this repo. Sort it by one question — **does a decision in this repo depend on it?**

| Material | Depended on? | Where it goes |
|---|---|---|
| Competitor analysis, competition rules, sensitive ADR context | **Yes** — docs must be able to link it | In this repo. A lot of this is the signal the repo should stay private, or should be split dev-private / public-snapshot |
| Pitch decks, slides, images, exploratory notes, documents issued by a third party | No | A note repo — see the ladder below |
| VM names, project IDs, hostnames, keys | Never, a note repo included | `.env`, a password manager, the provider's console (§3) |

**The note repo ladder.** Do not decide this up front:

- **Default: a per-project folder in one shared private notes repo.** Zero setup, which is the point — setup friction is paid at the start of a project, when it is least clear the notes will ever matter, and friction is what stops notes being written at all. Most projects produce two or three.
- **Split it into its own repo when** either trigger fires: (a) the notes need different access from other projects' notes — someone is about to be given it; or (b) their volume or binaries make cloning the shared repo unpleasant.
- **Cross-project material never splits.** Anything belonging to a programme, a cohort, or to you rather than to one project stays in the shared repo.

Splitting later is cheap — notes are documents and binaries, with no CI, no imports and nothing referencing their paths, so one `git filter-repo` preserves the history. Creating N repos up front has already paid the friction and cannot get it back. The two directions are not symmetric, so the default is the cheap one. This is the same ladder as `DOCS-CONVENTIONS.md` §10: adopt structure when a trigger fires, not before.

**Links run one way across the repo boundary.** This repo never links into a note repo. A link into a private repo returns 404 for everyone else while resolving normally for its author, so it is broken without anyone being able to see it — the worst kind. This is `DOCS-CONVENTIONS.md` §3's one-way rule for `discovery/`, extended across repos.

`discovery/` is **not** the home for the second row once this repo is public. It is exempt from nearly every documentation rule, but not from the repo being readable by anyone.

Three base rules, inherited by everything written anywhere in a repo:
- One fact has one owning file. Reference it from elsewhere; do not copy-paste it.
- Docs that describe behavior are updated **in the same commit** as the behavior change. Stale docs count as bugs.
- Decisions are append-only. Never rewrite an approved decision — supersede it with a new one.

### `WORKLOG.md` — append-only session journal

One file at the repo root, committed. Newest entry on top. It answers *what happened in this repo and why*, which no other file answers: `docs/` holds current state, `CHANGELOG.md` holds what a release shipped, issues hold what is left. A decision made and then reversed two sessions later leaves no trace in any of those.

One block per working session, three parts, nothing else:

```markdown
## Session 12 — 2026-11-01 · Mode B no worse than baseline (#27)

**Done**

- <what changed, with file paths and the IDs touched>

**Decided + why**

- <the choice, and the reason it beat the alternative>

**Real state / warnings**

- <what is verified, what is assumed, what is still broken>
```

Rules:

- **Append only.** Never edit an earlier entry. A later session correcting an earlier one writes a new block saying so.
- **Separate verified from assumed**, explicitly. "Tests pass" belongs under *Real state* only if they were run this session; otherwise it is an assumption and must be labelled one. This is §9's honesty rule applied to the journal.
- **Remaining work does not go here.** Progress lives in issues and milestones (§7). A worklog that also tracks what is left becomes a second, stale copy of the tracker.
- Written at the end of a session, and when something is discovered that the next session would otherwise rediscover.
- No secrets (§3). No raw error dumps — quote the one decisive line.

The journal grows without bound and that is correct: it is history, not state, so nothing in it goes stale. Nothing is ever pruned from it.

Everything else about documentation lives in [DOCS-CONVENTIONS.md](DOCS-CONVENTIONS.md) and is not restated here: the `docs/` tree, front matter and `status` values, ID conventions, inline version annotations, the support policy, `CHANGELOG.md` and release notes, when an ADR is warranted and how the register is kept readable, and the tier ladder saying when to adopt each piece. A short solo lab needs none of it — the root README above is enough.

## 9. Working with AI agents

- `AGENTS.md` holds project facts (what it is, where things live, how to run). This file holds the rules. `CLAUDE.md` is one line importing `AGENTS.md`, because that is the filename Claude Code looks for.
- Agents read the task first, then only the docs that task routes to. No blanket context loading.
- Agents do not broaden scope. Out-of-scope problems get reported, not fixed unasked.
- Keep changes scoped, reversible, secret-free. Do not edit generated files.
- **Before adding a fact to the docs, find the file that owns it.** Writing it in the file currently open is how the same fact ends up in three places with two of them stale. If no file owns it, that is the finding to report — a new fact without an owner usually means a missing document, not a free choice of location.

### Verification and honesty

- **Run it, then report what actually happened.** Never state that tests pass, a script works, or a file changed without having observed it. A failing result reported plainly is worth more than a confident guess.
- **Claims about code cite `file:line`.** Assertions from memory about how something behaves are not acceptable when the file is one read away.
- **Say what was skipped.** Finishing three of four tasks means naming the fourth and why it was left. Scaling the work down is the user's decision, not the agent's.
- **Stop after two failed approaches** to the same problem. Report the two attempts and what each revealed instead of starting a third. Blind retry loops burn tokens and usually make the state worse.

### When to ask, when to proceed

- **Proceed** when the action is reversible and only one reading of the request is sensible.
- **Ask** when the action is hard to undo, or when two readings lead to materially different work.
- **Block** — stop with nothing delivered until answered — only when guessing wrong would be unsafe or would waste the whole effort. Otherwise do every part that does not depend on the answer first, then ask.

### How far an agent runs on its own

An agent with `gh` available can read, create, edit and close issues, so the tempting conclusion is that it can run the tracker unattended. It should not. The limit is not capability, it is that some of these actions assert something the agent cannot independently establish, and some are visible outside the repo.

| Action | Default | With an explicit assignment |
|---|---|---|
| Read issues, pick up an assigned one, write the failing test | yes | — |
| Implement after the test is red | no — stop, report, wait (§6) | may implement the step that was cleared |
| Open a PR once the implementation is cleared | yes | — |
| Push straight to the integration branch | no | may push exactly the work the human put on that path |
| Comment progress or findings on an issue | yes | — |
| Create an issue | propose in chat, human files it | may file exactly the ones named |
| Edit an issue | no | may make exactly the edit described |
| Close an issue | no — a merge or a push closes it via `Closes #` | may close exactly the issue named |
| Write `Closes #N` without reporting the issue audit line by line | no | — |
| Set priority, milestone or scope | no, that is a product decision | may apply exactly what was specified |

**"Explicitly assigned" means one named step on named issues** — "close #42", "file the two issues we just discussed". It is not a standing grant. Doing the assigned step ends the authority: no follow-up issue action, no follow-up git action, no extending the same treatment to similar issues found along the way.

Even when closing is assigned, `Closes #` in a PR is still the better mechanism, because it ties "done" to merged and tested code rather than to somebody's claim. Assign a direct close for issues no PR will resolve — a duplicate, a question answered, something dropped.

Creating issues is the one that quietly goes wrong without this rule: an agent sweeping a codebase can file twenty issues, most of them noise, and now someone has to triage them. That costs more than it saved.

What stays with the human is not typing commands — it is **product judgment**: what is worth building, in what order, and what "good enough" means here.

### Delegating to subagents

**Confirm before spawning.** How many subagents, how the work is split, and which model each one runs — all three are proposed to the user and **confirmed before any subagent starts**. This holds even when the plan obviously follows the rules below. Subagents cost real tokens and their work is hard to inspect mid-flight, so the user decides whether to spend that, every time.

**When delegation is worth it.** Only when the output is far smaller than the input that must be read — sweeping many files for a conclusion — or when genuinely independent work can run in parallel. If the file to change is already known, doing it directly is cheaper than briefing an agent.

**The delegation contract.** A subagent starts with **zero conversation context**. Its prompt carries all five of these or it will guess:

| Part | Content |
|---|---|
| Goal | one sentence, stating what "done" means |
| Boundary | what it may touch, and explicitly **what it must not** |
| Starting point | exact paths, or an explicit "find it yourself" |
| Return format | table, list, diff — say which |
| Inherited constraints | this file, no commits, no pushes |

A missing boundary is the single most common cause of a subagent editing things nobody asked about.

**Hard rules:**

- **Read-only by default.** Agents that search or analyse do not write. Write access is granted only for work already scoped to named files.
- **One subagent, one deliverable.** Never "investigate this and also fix it".
- **Never delegate the decision.** Subagents return findings; the main thread decides and owns the answer, because the main thread is what the user is talking to.
- **A returned report is a claim, not a fact.** Spot-check before acting on it.
- **Relay the result.** A subagent's report does not reach the user. The main thread restates what matters. Never invent the result of an agent still running.

**How many at once:**

| Situation | Cap |
|---|---|
| Read-only, independent | 2 |
| Writing, file sets declared upfront and disjoint, no shared file touched | 2 |
| Writing, and they build or run tests | one per worktree |
| Writing, disjointness not provable | 1 |
| Later work depends on earlier findings | 1, run sequentially |

Two is not a technical limit and not a measured one — it is a **cost ceiling**. Each subagent reads its own context from scratch, so the bill grows with the count while the work does not. Raise it when a specific job shows the parallelism pays for itself, and say so when asking.

**Parallel writers.** Several agents may write at once when both conditions hold: every path is listed in the prompt rather than discovered, and none of them writes a shared file. Shared state is easy to miss, so check for it explicitly:

| Kind | Examples |
|---|---|
| Counters and ID allocation | the next ADR number, the next requirement ID |
| Index files | `docs/README.md`, the ADR register, the traceability matrix |
| Dependency manifests | `requirements.txt`, `pyproject.toml` |
| Append-only files | `CHANGELOG.md` |
| Package exports | `__init__.py` |

The principle: **agents write leaves, the main thread writes the index.** Each agent creates only its own files and reports what it created; indexes, changelogs, manifests and sequence numbers are updated once by the main thread afterwards. Before accepting the results, compare the returned file lists and stop on any overlap rather than merging blindly.

Splitting files prevents contention in the source tree only. Agents that run builds or tests still collide over `__pycache__`, `.pytest_cache`, `.venv`, ports and scratch databases — those need separate worktrees.

**Model choice.** Default is **Sonnet**. Upgrade to Opus when the work is genuinely hard; do not inherit the parent's model, because the parent is usually Opus and inheriting turns every subagent into one.

| Work | Model |
|---|---|
| Mechanical, high volume, little judgment — listing files, extracting one fixed field, reformatting | the cheapest available |
| Ordinary work: search, summarise, locate, apply a described edit | Sonnet |
| Genuinely hard: design, security, eval-failure analysis, geometry, choosing between options | Opus |
| Anything expensive to get wrong | Opus, and never downgraded to save tokens |

The rule that matters more than the table: **downgrade only what you can verify.** A cheap model plus an unchecked output is a silent error. If an agent definition in `.claude/agents/` already names a model, do not override it at the call site — its author already made that judgment.

**Subagents do not write to anything outside this repo.** Two bans, and both are inherited constraints that go into every delegation prompt verbatim:

| Target | Rule |
|---|---|
| GitHub | **Read only.** `gh issue view`, `gh pr diff`, `gh api` with GET. No creating, editing or closing an issue or PR, no comments, no labels, no `gh api` with any other method. |
| Cloud and any account-backed service | **Banned entirely, reads included.** CLI, console, API and SDK alike. AWS, GCP, every GPU provider (RunPod, Vast.ai, Lambda, Colab, Kaggle), and anywhere models or experiments are stored (Hugging Face Hub, W&B). |

The cloud ban covers reads too, for three reasons: a "read-only" command still prints secrets and log contents into a transcript; the read/write line is not where the command name suggests, since `gcloud compute ssh` mutates instance metadata and `aws ssm send-command` executes code; and a GPU instance created by mistake or left running costs real money with no error to notice. When a subagent needs cloud data, the main thread fetches it and passes it in the prompt.

**Both bans are enforced by the prompt, not by the tooling.** There is no `deny` rule behind them. A subagent that ignores its prompt is not blocked by anything, which is the actual reason the write side is kept with the main thread.

## 10. Definition of done

A change is done when **all** hold:

- [ ] Code follows sections 4–5 (types, config-driven models, wrapped LLM calls).
- [ ] A test for this change existed and failed before the implementation, failed for the real reason, and was run again after; result reported honestly (§6).
- [ ] The test was reviewed against the spec before implementing, or the stop was explicitly waived (§6).
- [ ] No secret added; `.env.example` updated if a new variable exists.
- [ ] Dependencies declared in the same commit.
- [ ] README/docs updated if behavior or setup changed.
- [ ] Commit message follows the form stated in §7.
- [ ] Nothing generated or private is staged.
