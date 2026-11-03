# Checklist: refactor

Copy into `docs/checklists/`. Tick every time code is restructured without changing what it does.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a refactor.

- [ ] Recorded the full test result **before** starting: how many passed, which failed.
- [ ] Named the reason in one sentence. "Tidier" is not a reason; "three call sites duplicate this parsing" is.
- [ ] **No test file edited.** If a test had to change, the behavior changed — stop, this is not a refactor.
- [ ] Public signatures, return values, raised exceptions and log output are unchanged.
- [ ] No dependency added or removed.
- [ ] Same tests, same count, same result afterwards.
- [ ] No documentation content changed — only paths, and only if files moved.
- [ ] Committed separately from any feature or fix. One logical change per commit.
- [ ] `CONVENTIONS.md` §10 satisfied.
