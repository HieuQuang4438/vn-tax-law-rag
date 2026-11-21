# Checklist: new feature

Tick every time a feature ships.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a feature.

- [ ] The FR and its AC exist in their owning documents, each with an ID, and the AC says how it is judged — all before any code.
- [ ] Wrote a failing test naming that AC, and confirmed it fails for the real reason.
- [ ] Reported the red test and stopped there, or the stop was explicitly waived (§6).
- [ ] Implemented until the test passes, and nothing else changed result.
- [ ] Traceability row added: problem → goal → FR → AC → test.
- [ ] The spec the test encodes shipped in the **same commit as the failing test** — the detail in `reference/`, and the AC where it changed.
- [ ] The docs describing what was delivered shipped in the **same commit as the behavior**.
- [ ] Added the `Added in vX.Y.Z` annotation on what the reader needs to know is new.
- [ ] Changelog entry under `Added`, citing the FR, AC and any ADR.
- [ ] `CONVENTIONS.md` §10 satisfied.
