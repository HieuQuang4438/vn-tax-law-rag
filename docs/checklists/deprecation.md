# Checklist: deprecation

One pass per release, three releases in total.
Never announce and remove in the same release — the warning must reach people before the break.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a deprecation.

## Release N — announce

- [ ] The replacement exists and works. Nothing is deprecated without somewhere to go.
- [ ] `deprecated-in: vN` recorded, naming the replacement.
- [ ] `Deprecated in vN` annotation added wherever the old behavior is described.
- [ ] Changelog entry under `Deprecated`, citing the replacement's ID.
- [ ] Behavior unchanged this release. Nothing breaks yet.

## Release N+1 — warn

- [ ] Runtime warning emitted on use, naming the replacement.
- [ ] Docs point at the replacement first; the old path is described second.
- [ ] Migration steps written in that release's notes.

## Release N+2 — remove

- [ ] Major version bump.
- [ ] `status: removed`, `Until` set to this version, row kept in place.
- [ ] Feature doc moved to `archive/`, unedited.
- [ ] Changelog entry under `Removed`; breaking change spelled out in the release note.
- [ ] `CONVENTIONS.md` §10 satisfied.
