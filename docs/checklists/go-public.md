# Checklist: go public

Copy into `docs/checklists/`. Tick **once**, the one time this repo is flipped from private to
public. This is not the checklist for shipping a snapshot to a separate public repo — that is a
different, recurring process and belongs in whichever repo does it.

Flipping is close to irreversible. Making the repo private again does not un-publish what was
read, cloned, forked, or indexed in the meantime, and it does not retract a licence already
granted. Every step below runs **before** the flip.

## 1. Decide the licence

- [ ] Pick one, and write the choice and the reason into `WORKLOG.md`:

      | Choice | When |
      |---|---|
      | No `LICENSE` file | A portfolio piece. Readable and forkable on GitHub, but nobody is granted the right to reuse it |
      | MIT | Others should use it freely; no strong attribution and no patent terms needed |
      | Apache-2.0 | There is a real method or algorithm here and the patent grant matters |

- [ ] Check the dependencies before choosing. A copyleft dependency (GPL, AGPL) can make a
      permissive licence on the whole wrong.
- [ ] Understand that this one does not come back: publishing a version under MIT or Apache-2.0
      grants rights **for that version** that deleting the file later does not withdraw. Adding
      a licence later is one commit, so when it is not clear, ship no `LICENSE`.

## 2. Scan the whole history, not the working tree

- [ ] `gitleaks detect --source .` — with no `--no-git`, this walks the commit history. Do not
      substitute a working-tree scan; a key deleted three commits ago is still published.
- [ ] Grep the history for every internal identifier named in `CONVENTIONS.md` §3 — machine and
      VM names, cloud project IDs and resource names, deploy hostnames, client or employer
      names:

      ```bash
      git grep -i -n -e "<term>" $(git rev-list --all)
      ```

- [ ] Anything found means **rewriting history** (`git filter-repo`), not deleting a file in a
      new commit. Rotate any key that was ever committed, whatever the history now says: treat
      it as leaked.
- [ ] After a rewrite, rewritten commits can still be reachable by SHA on the hosting side until
      the host garbage-collects them. Ask the host to do it, or create a fresh repo and push the
      cleaned history there.

## 3. Everything else that becomes public with the code

- [ ] `WORKLOG.md`: read it end to end. It is the file most likely to name a machine, a cost, an
      employer, or a competition, because it was written as a private journal.
- [ ] Issue and pull request bodies and comments, **including closed ones**. A history rewrite
      does not touch these — each one has to be edited or deleted by hand.
- [ ] Releases, tags and their notes; CI logs and workflow run output; the wiki; any attachment
      uploaded to an issue.
- [ ] `docs/`: no link into a note repo or any other private repo. Such a link returns 404 for
      every visitor while still resolving for you (`CONVENTIONS.md` §8).
- [ ] Commit messages: no internal references that read as nonsense in public.

## 4. Make it worth reading

- [ ] Root `README.md` replaced with the outward-facing one, every placeholder filled, the
      screenshot or GIF in place and committed to the repo.
- [ ] A visitor can run it from the README alone: required accounts and keys named, rough cost
      stated, hardware assumptions stated.
- [ ] `Status` section is honest about what is unfinished. A named gap costs nothing; a hidden
      one found by a reader discredits the rest.

## 5. Flip

- [ ] `AGENTS.md` `Visibility:` line now reads `public`.
- [ ] Flip the repo's visibility — a human action, like every other remote operation
      (`CONVENTIONS.md` §7).
- [ ] Open the repo while signed out, or in a private window: README renders, images load, every
      link resolves.
- [ ] Record the flip in `WORKLOG.md`, with the licence decision and what the history scan found.
