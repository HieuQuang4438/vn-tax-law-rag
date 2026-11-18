---
status: approved
updated: 2026-11-19
owner: HieuQuang4438
approved-by: self (built)
issue: 10
---

# BM25 tokenizer

Moved on 2026-11-19 from `docs/reference/index.md`, *Tokenizer experiment* (#32). The text is as it was written there; the only edits are pointers to sections that now live in another file.

Does word segmentation raise recall@8 over syllable tokens? Measured on #10, with the decision
rule fixed before the run: a segmenter replaces `syllable` only if the paired 95% bootstrap
interval of its EVAL-001 change lies entirely above 0 and AC-012 still holds.

Setup, the same for every run: commit `0e6024c`, eval set v1 (`d33b390e4894…`), bge-m3
`5617a9f6`, chunk threshold 800, k = 8, RRF 60, 50 candidates, `rewrite: none`, the dev laptop
(i7-10610U, 16 GB RAM, CPU only). Each variant was built with `--out data/index-<tokenizer>`
from the shared vector cache and scored with `python -m src.eval.run --index`.

| Tokenizer | Version | EVAL-001 | Paired change vs syllable | EVAL-005 | EVAL-007 | BM25 build | Retrieval median / p95 | Results file |
|---|---|---|---|---|---|---|---|---|
| `syllable` | — | 0.633 [0.539, 0.727] | — | 0.575 [0.333, 0.817] | 0.676 [0.571, 0.773] | 0.6 s | 0.40 / 0.78 s | `2026-11-13-0e6024c.json` |
| `underthesea` | 9.5.0 | 0.627 [0.519, 0.731] | −0.006 [−0.058, +0.038] | 0.542 [0.275, 0.808] | 0.674 [0.571, 0.765] | 44.0 s | 0.24 / 0.35 s | `2026-11-13-0e6024c-2.json` |
| `pyvi` | 0.1.1 | 0.601 [0.499, 0.702] | −0.032 [−0.083, +0.013] | 0.542 [0.275, 0.808] | 0.658 [0.557, 0.754] | 13.7 s | 0.43 / 0.56 s | `2026-11-13-0e6024c-3.json` |

- Neither segmenter meets the rule: both paired intervals include 0, and both means are lower.
  `syllable` stays, and no dependency is added to `requirements.txt`.
- Per question, underthesea raised recall on 3 questions and lowered it on 4; pyvi on 2 and 5.
- On `plain` questions underthesea gains slightly (0.581 against 0.572) and pyvi loses (0.544);
  on `reference` questions both lose (0.729 against 0.771).
- Retrieval latency varies by about 0.2 s between runs on this laptop, more than between
  tokenizers, so it does not separate them; every variant keeps AC-012.
- The segmenters stay available, so the experiment can be run again on a later eval set.
