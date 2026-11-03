# Checklist: new feature

Copy into `docs/checklists/`. Tick every time a feature ships.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a feature.

- [ ] The requirement exists in its owning document with an ID, before any code.
- [ ] The acceptance criterion exists with an ID and says how it is judged, before any code.
- [ ] Wrote a failing test naming that AC.
- [ ] Implemented until the test passes, and nothing else changed result.
- [ ] Traceability row added: problem → goal → FR → AC → test.
- [ ] Docs updated in the **same commit** as the behavior.
- [ ] Added the `Added in vX.Y.Z` annotation on what the reader needs to know is new.
- [ ] Changelog entry under `Added`, citing the FR, AC and any ADR.
- [ ] `CONVENTIONS.md` §10 satisfied.
