# Checklist: reviewing a PR

Tick every time a PR is reviewed. `CONVENTIONS.md` §7 says who reviews what.
Every item here is something the author **cannot** establish about their own work — §10 is the
author's own gate, and restating it here would just move the self-assessment one page over.

- [ ] Opened the `Spec:` anchor the issue points at and read it. Reviewing against the PR body is checking a change against its own account of itself.
- [ ] The test encodes the **AC**, not the implementation. Rewrite the code a different way and the test must still be the right test.
- [ ] Re-ran the commands under `Ran` and got the output that was pasted. A reported result is only a claim.
- [ ] The test really fails without the change — `git stash` the source, keep the test.
- [ ] No test loosened, no checker loosened, no assertion weakened to make this pass.
- [ ] Read `Done when:` and `Out of scope:` on the issue, then read the diff. Every divergence found must already have an issue comment predating the `Closes #` line (§7). A divergence no comment covers blocks the merge — that is the one failure this review exists to catch. This item only covers the PR path; a direct push to the integration branch gets no review, so there the §7 audit is the only gate.
- [ ] `Not in here` is honest: nothing a reviewer would expect is quietly missing from it.
- [ ] `CONVENTIONS.md` §10 satisfied.
