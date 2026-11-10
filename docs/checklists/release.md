# Checklist: release

Tick every time a version ships.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a release.

- [ ] Every issue in the milestone is closed, or moved out of it deliberately.
- [ ] Version number follows SemVer. A removal or a changed contract forces a major.
- [ ] `CHANGELOG.md` entry complete, grouped, and every line cites the IDs it moved.
- [ ] `releases/vX.Y.Z.md` written: migration steps, breaking changes, known issues, rollback.
- [ ] Deprecations each advanced exactly one step along the three-release path.
- [ ] Version annotations pruned — **only** those whose fact the changelog already records.
- [ ] `Since`/`Until` columns updated for anything added or removed this release.
- [ ] `docs/milestones/<version>.md` deleted, if that mechanism is in use.
- [ ] Tagged after merge, not before.
- [ ] `CONVENTIONS.md` §10 satisfied.
