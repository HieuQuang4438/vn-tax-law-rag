# Checklist: bug fix

Copy into `docs/checklists/`. Tick every time a bug is fixed.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a bug fix.

- [ ] Reproduced the bug, and written down the exact input and the wrong output.
- [ ] Wrote a test that **fails because of this bug**, before touching the fix.
- [ ] Confirmed the test fails for the real reason, not a setup or import error.
- [ ] Fixed the cause, not the symptom. A guard that hides the bad value is not a fix.
- [ ] The new test passes and no other test changed result.
- [ ] Searched for the same mistake elsewhere — same pattern, same call site shape.
- [ ] Decided whether users can observe the change; if so, added the version annotation and a `Fixed` changelog line.
- [ ] `CONVENTIONS.md` §10 satisfied.
