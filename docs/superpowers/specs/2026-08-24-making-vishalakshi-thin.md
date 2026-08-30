# Making vishalakshi thin

Date: 2026-08-24
Repos: `vishalakshi`, `litesearch`, `fossick`, `kosha`, `rahasya`, `varga`, `pobblebonk`

## The finding

vishalakshi was 3,210 lines of definitions across ten modules. 1,446 of them, 45%, were three
self-contained products that do not need a vault: a PII detector, a doctype and extraction
library, and a corpus-quality ranker. Another 387 were a job queue and a scheduler written by
hand. The vault itself was under 1,400 lines, and most of that is seam.

## Where it went

| module | was | now | into |
|----|----|----|----|
| `extract.py` | 551 | 184 | `varga` |
| `pii.py` | 416 | 108 | `rahasya` |
| `quality.py` | 479 | 268 | `litesearch.quality` |
| `jobs.py` | 206 | 206 | kept. See the queue note below |
| `acquire.py` | 481 | 467 | `fossick.read`, and pobblebonk for the clock |
| `ask.py` | 304 | 301 | |
| `code.py` | 122 | 119 | |
| `core.py` | 568 | 573 | the `@gate` decorator costs what the eight copies did |
| `cli.py` + `mcp.py` | 83 | 83 | already the target shape |

The CLI is unchanged: 71 commands and 67 MCP tools, from 83 lines of reflection over `Vault`'s
signatures. Every command still resolves.

## What each move bought

rahasya holds the detector. 34 kinds, 19 regional checksums, the honorific name pass. `fastcore`
is its only dependency. `pii.py` re-exports it, so every name still resolves. A test asserts the
re-exports are the same objects upstream holds, so a drift becomes a failing test rather than two
detectors that disagree.

varga holds the doctypes and the extraction. 26 doctypes scored from cue phrases, with `decisive`
saying whether a model call is needed. It also holds the ten built-in shapes, `structured`, and
the two prompts that drive them.

litesearch.quality holds the noise arithmetic. Nine features over the vectors already in the
store, the rank normaliser, and the pairwise `Ranker`. The only thing it needed a vault for was
`promiscuity`, which counts how many different questions a document was retrieved for. That is now
a `seen` dict a caller passes if it keeps a log.

pobblebonk holds the clock. honker opens the vault file itself, verified, and its tables carry a
`_honker_` prefix. `watch(cron='0 9 * * 1')` is new and free.

fossick.read holds one reader shape. The saving is in fossick, where it is reusable, rather than here.
The readers went from 66 lines to 49 and the module net was 14 lines. What vishalakshi gains is one
shape instead of eight reshapers, and a target kind whenever fossick gets one.

The `@gate` decorator is not a line saving. It costs about what the eight copies did. What it buys
is that a primitive handing back section text cannot forget the gate.

## The queue stays

I moved the queue onto honker and was wrong. `jobs.py` is restored.

`evals/RESULTS.md` section 4 is the argument. 400 jobs across 8 processes, 0 lost and 0
double-claimed. 4 workers SIGKILLed mid-handler, all 4 stranded jobs recovered. 6 handlers
outliving their lease, 0 jobs acked by two workers, because `ack` is fenced inside the same
transaction as the update. honker has none of that: `fail` dead-letters on the first failure, and
a claimed `Job` reports `max_attempts=3` whatever the row says.

So pobblebonk keeps the clock and `Queue` keeps the work. The scheduling half was the handrolled
part worth replacing: `_intervals`, `_advance`, a `next_run` column, and a duration parser that
only knew s, m, h, d and w.

## Three edges that pointed the wrong way

`pii.person_spans` imported `_noun_ents` from `extract`. The honorific regex is `PERSON_HON` in
rahasya now, and varga imports it. The doctype scorer and the privacy gate share one definition of
what a name is, and a test asserts they are the same object.

varga's keyphrase leg imported litesearch. It is optional and display-only now. A test runs
`guess_type` with the import blocked.

`varga.schema` borrowed `split_reasoning` from `vishalakshi.ask`. Six lines, now its own.

## No extras anywhere

Nothing in these repos declares an optional-dependency group. Every extra guarded a lazy import
that already existed and already raised. The messages named the extra to install. They now name
the package, which is what a caller can act on without knowing how anything is packaged.

Rishi is the backend package. Vishalakshi imports it through `urai()` when a chat is first built.
Importing Vishalakshi, adding documents, searching, categorising on cues and running the PII gate
work without Rishi. `ask` raises `asking needs rishi: pip install rishi` when it is absent.

Urai is a direct dependency because Vishalakshi imports its portable chat API. Rishi remains a
runtime dependency because it registers the backends. The default model uses its LiteRT backend.

litesearch lost two runtime dependencies it never imported. `notebook` alone pulls 93
distributions, JupyterLab included.

## Bugs the moves surfaced

`gen_aadhaar` was exported and called an undefined `verhoeff_digit`. It had never run. Fixed in
rahasya, with the round-trip test that would have caught it.

pobblebonk's notebook said "honker keeps the job for a retry". honker's `fail` dead-letters
outright, so every raising callback died on its first attempt.

A claimed honker `Job` reports `max_attempts=3` whatever the row says, so `Pob(retries=5)` still
died on the third attempt. The budget is read off the live row now.

`pobblebonk/__init__.py` never re-exported `core`, so `from pobblebonk import Pob` raised.

The review branch's `extract.py` imported `TYPE_SP` and `EXTRACT_SP` from varga, and neither had
been released there. Both prompts now ship with the code they prompt for, pinned by a test: a
reflow keeps every word and changes what a model is told.

## What the queue migration cost

A watch no longer counts `runs`, `missed` or `last_status` from a hand-rolled column. honker's
scheduler owns the cadence.

A job waiting out a backoff carries no error text, because `_honker_live` has no `last_error`
column. The text becomes readable once the job dies.

honker watches `PRAGMA data_version` on a file, so an in-memory vault gets a temporary queue file
rather than holding its own.

## Still to move

| move | lines | into |
|----|----|----|
| topic presentation: `map`, `topic_tree`, `fmt_topics` | 117 | `litesearch.graph`, which owns the tables it reads |
| `tidy_bc` | 3, at 7 call sites | `litesearch.tree`. `tree.py:183` writes `Pages 1-3:` window titles into breadcrumbs |
| federate row shaping | 122 to about 55 | `kosha`, as `Kosha.rows(q)` in the fused shape |
| image and EXIF ingest | 90 | `fossick`, which reads files rather than vaults |
| `CachedChat` | 52 | `rishi` |

That would put vishalakshi near 1,700 lines of definitions. The floor is `ask.py` and what is left
of `core.py`: the vault, its shelves, its marks, and the retrieval seam.

## The one-file question

Reachable, and no longer the interesting question. `pii` and `extract` were 967 lines of the old
total. They are their own packages now, which is the same answer arrived at honestly rather than by
moving code into a file that did not want it.

litesearch is the next one to look at. It has its own spec.

## Sequencing

Nothing on this branch installs until rahasya, varga, the new fossick, litesearch 0.1.33 and
pobblebonk 0.0.2 are published. The dependency floors in `pyproject.toml` name the versions.

## Loose ends

`label_images` in `acquire.py` raises `ImportError` asking for `anya`, which is in no dependency
group. It is registered as an MCP tool.

`nbs/chatcache/cache.db` is a fixture a test run overwrites. Restore it before committing, or
`06_extract` fails on the next run against a live model.

`00_core` #25 downloads an encoder and cannot run in a sandbox. It fails the same way before and
after every change on this branch.
