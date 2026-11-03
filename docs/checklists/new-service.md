# Checklist: new service

Copy into `docs/checklists/`. Tick every time a new deployable unit is added.
The universal gate is `CONVENTIONS.md` §10 — this file only adds what is specific to a new service.

- [ ] Named the one thing this service owns. If it needs "and", it is two services.
- [ ] ID prefix chosen and registered in `docs/README.md` before any requirement is written.
- [ ] `docs/services/<svc>/` created with `README.md`, `requirements.md`, `api.md`, `runbook.md`.
- [ ] The runbook says how to deploy it, roll it back, and what to do when it pages someone.
- [ ] Its contract in `api.md` names the consumers it has, or states it has none yet.
- [ ] Own `.env.example` entries, own config reader. No secret shared by copy-paste.
- [ ] Added to the `docs/README.md` index and to both reading orders.
- [ ] Runs, and its tests run, without any other service present — or the dependency is written down.
- [ ] `CONVENTIONS.md` §10 satisfied.
