# Making vishalakshi thin

Date: 2026-08-24
Repos: `vishalakshi`, `litesearch`, `fossick`, `kosha`, `rahasya`, `varga`, `pobblebonk`

## The finding

vishalakshi was 3,210 lines of definitions across ten modules, and 1,446 of them (45%) were three
self-contained products that do not need a vault to exist: a PII detector, a doctype and
extraction library, and a corpus-quality ranker. Another 387 were a job queue and a scheduler
written by hand. The vault proper was under 1,400 lines, and most of that is seam.

## Where it went

| module | was | now | into |
|----|----|----|----|
| `extract.py` | 551 | 184 | `varga` |
| `pii.py` | 416 | 108 | `rahasya` |
| `quality.py` | 479 | 268 | `litesearch.quality` |
| `jobs.py` | 206 | 0 | `pobblebonk` over `honker` |
| `acquire.py` | 481 | 467 | `fossick.read`, and the whole watch surface |
| `ask.py` | 304 | 301 | |
| `code.py` | 122 | 119 | |
| `core.py` | 568 | 573 | the `@gate` decorator costs what the eight copies did |
| `cli.py` + `mcp.py` | 83 | 83 | already the target shape |
| **total** | **3,210** | **2,103** | **−34%** |

The CLI is unchanged: 71 commands and 67 MCP tools, from 83 lines of reflection over `Vault`'s
signatures. Every command still resolves.

## What each move actually bought

**rahasya** (the detector). 34 kinds, 19 regional checksums, the honorific name pass. `fastcore`
is its only dependency. `pii.py` re-exports it, so every name still resolves, and a test asserts
the re-exports are the same objects upstream holds: a drift becomes a failing test rather than two
detectors that disagree.

**varga** (doctypes and extraction). 26 doctypes scored from cue phrases, with `decisive` saying
whether a model call is needed, plus the ten built-in shapes and `structured`. `rishi` is an extra,
so the doctype half installs without a model runtime.

**litesearch.quality** (the noise arithmetic). Nine features over the vectors already in the store,
the rank normaliser and the pairwise `Ranker`. The only thing it needed a vault for was
`promiscuity`, now a `seen` dict a caller passes if it keeps a retrieval log.

**pobblebonk** (the queue and the scheduler). honker opens the vault file itself — verified —
and its tables are `_honker_*` prefixed. `watch(cron='0 9 * * 1')` is new and free.

**fossick.read** (one reader shape). The saving here landed in fossick, where it is reusable, not
in vishalakshi: the readers went 66 lines to 49 and the module net was −14. What vishalakshi gains
is one shape instead of eight reshapers, and a target kind whenever fossick gets one.

**The `@gate` decorator.** `search`, `sections`, `context`, `read`, `document`, `toc`, `federate`
and `doc_context` each declared `pii=`/`pii_ner=` and called `_gate` themselves. Not a line
saving; what it buys is that a primitive handing back section text cannot forget the gate.

## Three edges that pointed the wrong way, now cut

- `pii.person_spans` imported `_noun_ents` from `extract`. The honorific regex is `PERSON_HON` in
  rahasya and varga imports it, so the doctype scorer and the privacy gate share one definition of
  what a name is. A test asserts they are the same object.
- varga's keyphrase leg imported litesearch. Optional and display-only now, with a test that runs
  `guess_type` with the import blocked.
- `varga.schema` borrowed `split_reasoning` from `vishalakshi.ask`. Six lines, now its own.

## Bugs the moves surfaced

- `gen_aadhaar` was exported and called an undefined `verhoeff_digit`. It had never run. Fixed in
  rahasya with the round-trip test that would have caught it.
- pobblebonk's notebook said "honker keeps the job for a retry". honker's `fail` dead-letters
  outright, so every raising callback died on its first attempt. Fixed with `backoff` and the
  attempt budget spent in `_run`.
- A claimed honker `Job` reports `max_attempts=3` whatever the row says, and `Job.retry` enforces
  no limit, so `Pob(retries=5)` still died on the third attempt. `_budget` reads the live row.
- `pobblebonk/__init__.py` never re-exported `core`, so `from pobblebonk import Pob` raised.

## What the queue migration cost

Retries with backoff and the five-attempt dead letter are preserved and verified. Two behaviours
are gone:

- A watch no longer counts `runs`, `missed` or `last_status` on its own row; honker's scheduler
  owns the cadence.
- A job waiting out a backoff carries no error text, because `_honker_live` has no `last_error`
  column. It becomes readable once the job dies.

And one constraint is new: honker watches `PRAGMA data_version` on a file, so an in-memory vault
gets a temporary queue file rather than holding its own.

## Still to move

| move | lines | into |
|----|----|----|
| topic presentation (`map`, `topic_tree`, `fmt_topics`) | 117 | `litesearch.graph`; reads only litesearch tables |
| `tidy_bc` | 3, 7 call sites | `litesearch.tree`; `tree.py:183` writes `Pages 1–3:` window titles into breadcrumbs |
| federate row shaping | 122 → ~55 | `kosha`, as `Kosha.rows(q)` in the fused shape |
| image/EXIF ingest | 90 | `fossick`; reads files, not vaults |
| `CachedChat` | 52 | `rishi` |

That would put vishalakshi near 1,700 def-lines. The floor is `ask.py` and what is left of
`core.py`: the vault, its shelves, its marks and the retrieval seam.

## The one-file question

Reachable, and no longer the interesting question. `pii` and `extract` were 967 lines of the old
total and are now their own packages, which is the same answer arrived at honestly rather than by
moving code into a file that did not want it.

**litesearch is the next one to look at.** It is 8,395 lines across seven modules and is now
carrying quality as well. Its `Index` is six methods over a `Database` that has thirty; the same
split that helped here — what is measured, what is policy, what is seam — has not been done to it.

## Sequencing

Nothing on this branch installs until rahasya, varga, the new fossick, litesearch 0.1.33 and
pobblebonk 0.0.2 are published; the dependency floors in `pyproject.toml` name the versions.

## Loose ends

- `label_images` (`acquire.py`) raises `ImportError` asking for `anya`, which is in no dependency
  group. It is registered as an MCP tool.
- `nbs/chatcache/cache.db` is a fixture a test run overwrites. Restore it before committing or
  `06_extract` fails on the next run against a live model.
- `00_core` #25 downloads an encoder and cannot run in a sandbox. It fails identically before and
  after every change on this branch.
