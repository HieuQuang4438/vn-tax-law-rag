# Checklist: issue proposal

Copy into `docs/checklists/`. Use when an issue carries a design choice.
Mechanical work skips this file entirely.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to proposing
an approach. The rule it implements is in `CONVENTIONS.md` §7.

## Procedure

- [ ] Read the issue and the owning document its `Spec:` line points at.
- [ ] Draft the proposal in chat, using the template below. **Nothing posted, nothing coded.** Write it as rendered markdown, not inside a code block: the reviewer has to read it, and a fenced block shows raw `**` and `###` instead of formatting. The code block is only for the exact text being posted, once approved, if it is needed at all.
- [ ] A human approves or edits it in chat.
- [ ] Post the approved version as an issue comment, keeping **every** option that was raised and marking the one chosen.
- [ ] Implement. Where the work departs from what was approved, record it in the owning document with the reason — never by editing the comment.
- [ ] Each new decision approved mid-work — how to handle a measurement, a scope change, a parameter — is posted as a **new** comment before it is acted on, using the second template.
- [ ] What is settled goes into the owning document or an ADR. A comment is not a source of truth.
- [ ] The PR body says `Closes #N`. No summary comment at the end; the commits and the close are the record.

## Comment template — proposing an approach

```markdown
## Approach for <issue title>

<The approach in 2-4 sentences. Point at the owning document's section; do not copy it.>

**Fixed:** <what is not a choice: repo rules, product requirements, files that will be created.>

### Choices

**1. <the decision>**
- ✅ A: <option>. <one line of trade-off>
- ⬜ B: <option>. <one line of trade-off>

**2. <the decision>**
- ...

### Risks
- <what could make the result wrong or hard to interpret, and how it will be reported.>
```

- Every decision carries at least two options, each with its trade-off on one line. One option is not a choice, it is a plan.
- Mark the chosen option ✅ and the others ⬜, not `- [x]` / `- [ ]`: on GitHub a task-list checkbox in a comment can be ticked by a click, which would silently change the record.
- For anything measured, the configuration goes in `Fixed` or in an option: time limit, seed, commit, model, quantization, dataset.

## Comment template — a decision approved mid-work

```markdown
## Approved: <the decision>

**Why.** <the measurement or finding that raised the question, with its configuration; link the owning document if one exists.>

**Chosen.** <the approved option>. Not chosen: <the others, one line of trade-off each>.

**Next.** <the next step; write "not started" if the decision was approved without the work being assigned.>
```
