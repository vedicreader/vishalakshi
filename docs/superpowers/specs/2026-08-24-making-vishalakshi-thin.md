# Making vishalakshi thin

Date: 2026-08-24
Repos: `vishalakshi`, `litesearch`, `fossick`, `kosha`, `rahasya`, `varga`

## The finding

vishalakshi was 3,210 lines of definitions across ten modules, and 1,446 of them (45%) were three
self-contained products that do not need a vault to exist: a PII detector, a doctype and
extraction library, and a corpus-quality ranker. The vault proper was 1,377 lines, and most of
that is seam.

So "thin" was two problems. The embedded products had to leave, because litesearch is not where
they belong either. The vault machinery had to stop reshaping what the libraries already return.

## Done

| change | repo | result |
|----|----|----|
| PII detector split out | `rahasya` | `pii.py` 416 def-lines → 110 |
| doctypes + extraction split out | `varga` | `extract.py` 551 def-lines → 184 |
| one reader shape | `fossick.read` | the eight readers 66 → 49; `what_is` and `md_title` now live with the readers |

vishalakshi is 3,210 def-lines → 2,527. `pii.py` and `extract.py` re-export their packages, so
every name vishalakshi has ever exported still resolves, and both notebooks assert the re-exported
names are the same objects upstream holds. A drift becomes a failing test rather than two
detectors that disagree.

Three edges were cut on the way out, all pointing the wrong way:

- `pii.person_spans` imported `_noun_ents` from `extract`. The honorific regex is now `PERSON_HON`
  in rahasya and varga imports it, so the doctype scorer and the privacy gate share one definition
  of what a name is.
- varga's keyphrase leg imported litesearch. It is optional and display-only now, with a test that
  runs `guess_type` with the import blocked.
- `varga.schema` borrowed `split_reasoning` from `vishalakshi.ask`. Six lines, now its own.

One live bug surfaced: `gen_aadhaar` was exported and called an undefined `verhoeff_digit`. It had
never run. Fixed in rahasya with the round-trip test against `aadhaar_ok` that would have caught it.

## Queues: honker already does this

Verified, not assumed.

**honker opens the vault file itself.** `honker.open(path)` on a live litesearch database
enqueued, claimed and acked a job, fired a scheduled task, and left the vault searchable. Its
tables are all `_honker_*` prefixed. Two connection stacks, one file, no conflict.

**honker covers the mechanism.** Every primitive `vishalakshi.jobs.Queue` has:

| `Queue` | honker |
|----|----|
| `enqueue` (priority, run_at) | `Queue.enqueue(payload, run_at=, delay=, priority=, expires=, max_attempts=)` |
| `claim` | `Queue.claim_one` / `claim_batch` / `claim` (async) |
| `ack`, `fail` | `Job.ack`, `Queue.fail` — `fail` dead-letters to `_honker_dead` |
| `backoff` retry | `Queue.retry(job_id, worker, delay_s, error)`; the doubling stays the caller's |
| `reclaim` (lease expiry) | `Queue.sweep_expired`, `Queue.heartbeat` |
| `purge` | `Queue.sweep_results` |
| `jobs`, `dead`, `pending`, `stats` | SQL over `_honker_live` and `_honker_dead` |

And it covers the part vishalakshi hand-rolled *outside* the queue: `watch`, `watches`, `pause`,
`schedule`, `_advance` and `_intervals` are 181 lines re-implementing a scheduler.
`honker.Scheduler` plus `honker_scheduler_tick(now)` — a SQL function, so a cron entry is the whole
scheduler — is that, drift-free, with `crontab()` as well as `every_s()`.

Three things honker does not have, and pobblebonk shows the shape for each in 222 lines: a dedupe
key on enqueue (`pob_items` has a partial unique index), a handler registry with a gate that skips
a fire whose pile is empty, and the callback itself.

**Do not attach honker to litesearch.** litesearch has no queue concept and no caller that wants
one; the coupling belongs where the vault file lives. The question is only which door vishalakshi
uses:

- **Depend on pobblebonk.** It already has the gate, the callback registry and the notes stream.
  `Pob(db=self.db)` puts it in the vault file. Deletes `jobs.py` (206) and most of the watch
  machinery (181), and `watch(cron=...)` comes free.
- **Depend on honker directly** and keep ~40 lines of policy here: the backoff curve, the dedupe
  key, and the four handlers.

Either way vishalakshi gains a Rust wheel in its dependency set, which is the real decision.

## Still to move

| move | lines | into |
|----|----|----|
| noise features + `Ranker` | 479 → ~120 | `litesearch.quality`; generic over any store |
| topic presentation (`map`, `topic_tree`, `fmt_topics`) | 117 | `litesearch.graph`; reads only litesearch tables |
| `tidy_bc` | 3, 7 call sites | `litesearch.tree`; `tree.py:183` writes `Pages 1–3:` window titles into breadcrumbs |
| federate row shaping | 122 → ~55 | `kosha`, as `Kosha.rows(q)` in the fused shape |
| image/EXIF ingest | 90 | `fossick`; reads files, not vaults |
| the nine hand-wired pii gates | — | one decorator at the retrieval boundary; needs no release |

## What stays

`ask.py` (the prompts, the citation parse, the local-runtime pii routing), `core.py`'s vault,
shelves and marks, and `cli.py` + `mcp.py`, which are already the target shape: 71 CLI commands and
67 MCP tools from 83 lines of reflection over `Vault`'s signatures.

## The one-file question

With everything above done, vishalakshi is roughly 900 def-lines and could be one module. It is not
one file today because `pii` and `extract` were 967 lines of it; they are now their own packages,
which is the same answer arrived at honestly rather than by moving code into a file that does not
want it.

## Sequencing

Each library change is two pull requests, because vishalakshi cannot import what is not released.
rahasya, varga and the new fossick have to be published before this branch installs; the dependency
floors in `pyproject.toml` name the versions.

## Loose ends

- `label_images` (`acquire.py`) raises `ImportError` asking for `anya`, which is in no dependency
  group. It is registered as an MCP tool.
- Two notebook cells need outbound network and cannot run in a sandbox: `01_acquire` #13 (kosha
  indexing a clone) and `00_core` #25. Both fail identically before and after these changes.
