# Decisions

This page lists the decisions that a maintainer must know. Each entry gives the decision, the reason, the version or date, and the place in the code.
The rules of daily work (what is here and what is borrowed, prose, docstrings, evals) are in [CLAUDE.md](../CLAUDE.md). This page does not repeat them.
The numbers are in [evals/RESULTS.md](../evals/RESULTS.md). The old specs (vault on `Index`, making vishalakshi thin) and the plan for reading and search are in the git history under `docs/`.

## The vault and search

- **`Vault` is a litesearch `Index`.** `find` is gone; `search` is the name. Rerank lives in litesearch's tree legs, so the vault gets it with no code here.
  Why: the encoder is not the lever (0.018 to 0.046 MRR across four encoders), and one route is less to keep. (11 Aug 2026, 0.1.x) `class Vault(Index)` in `nbs/00_core.ipynb`.
- **One static encoder for all shelves.** `potion-multilingual-128M` covers Devanagari too. `SHELVES` names the shelves; it is not an encoder map. A stale shelf is deleted with `drop_shelf`, not migrated. (11 Aug 2026) `DFLT_ENC`, `SHELVES`, `drop_shelf`.
- **The entity graph stays off.** Its leg gave -0.07 to -0.16 MRR on ordinary queries. The typed graph is vruksha's. (Aug 2026)
- **`Vault()` opens `$VISHALAKSHI_VAULT`, else `~/.vishalakshi/vault.db`.** Tests use `Vault.temp()`, so a test never opens the real vault. (0.1.36, 0.1.37)
- **A copied vault still points at the real `.usearch` files.** Before you open a copy, copy the `.usearch` files and rewrite the paths in `usearch_indices`. Else the copy writes the real indexes. (Owner note) `usearch_indices` table.
- **Follow litesearch's one-text rule.** A source already filed returns `skipped='already filed'`. `doc(ref)` finds a document by any source. (0.1.33)

## What lives here and what is borrowed

- **The detectors are upstream.** PII detection is rahasya, doctypes and schemas are varga, the noise features are `litesearch.quality`, the readers are `fossick.read`, the clock is pobblebonk. vishalakshi re-exports them. A test checks that the re-exports are the same objects. A gap gets an upstream patch, not a local copy.
  Why: 45 % of the old code (1,446 of 3,210 lines) did not need a vault. (24 Aug 2026; owner, 1 Nov 2026) `nbs/06_extract.ipynb`, `nbs/09_pii.ipynb`, `nbs/10_quality.ipynb`.
- **The queue stays here; the clock goes to pobblebonk.** `Queue` holds the lease (600 s), the fenced ack and the dead letter. honker dead-letters on the first failure, so the move to honker was undone. pobblebonk keeps only the cadence of a watch.
  Why: 400 jobs over 8 processes, 0 lost, 0 claimed two times; 4 killed workers, all jobs recovered. (24 Aug 2026) `nbs/11_jobs.ipynb`, `watch` in `nbs/01_acquire.ipynb`, `evals/RESULTS.md` section 4.
- **`Ledger` records jobs that run outside the queue.** It never retries. Call `close_running()` when an app starts. `Queue` does not change. (0.1.38) `jobs.Ledger`.
- **rishi is a runtime dependency, loaded late.** `urai()` imports it when a chat is first built. Import, add, search, cue-based categorize and the PII gate work without a model. (24 Aug 2026, 0.1.29) `urai` in `nbs/02_ask.ipynb`.
- **The CLI and the MCP server are reflection over `Vault`.** A method named in `CMDS` becomes a command, with its parameters read from its signature. Add a name to `CMDS`; do not write a command by hand. `nbs/04_cli.ipynb`, `nbs/05_mcp.ipynb`.

## Privacy

- **Three levels: Open, Personal, Local only.** A document's level is its mark, else its type and findings, never below the shelf floor. A Local only document goes to no hosted model, whatever the policy. (0.1.22) `nbs/09_pii.ipynb`.
- **Only a person lowers a level.** `by='agent'` raises `PermissionError` for a lower level, a cleared mark, a rejected finding, a lower floor and the proof undo calls. MCP always passes `by='agent'`, so these are CLI commands only. (0.1.22, 0.1.24)
- **MCP gates every result.** Strings under a Local only document are withheld; others go through `redact`. `pii='off'` over MCP raises. (0.1.27) `nbs/05_mcp.ipynb`.
- **Titles, headings and sources are judged and masked with the text.** A note titled with an email address must not reach a hosted model. Each hosted send is in `send_log`. (0.1.26)
- **Every retrieval method goes through `@gate`.** It is not a line saving. A method that gives section text cannot forget the gate. (24 Aug 2026) `gate` in `nbs/00_core.ipynb`.
- **The gate raises on a database error.** It must not treat a Local only shelf as Open. (0.1.34)

## Reading and proofreading

- **Each page has a route.** `parse='auto'` keeps a sound text layer, OCRs a scanned page and sends a flagged page to a vision model. Each reading is a version in `pages`, with its route and flags. Model reads run after ingest, not in litesearch's parse pool. (18 Oct 2026, 0.1.19) `nbs/12_read.ipynb`.
- **Readings are cached per file** (relative path and extension) as JSON. A cached page is not sent again; `redo=` moves the old reading to `_prev`. (0.1.25, 0.1.34)
- **A read never loses a stored reading.** A blocked, failed, cancelled or unrequested page keeps its reading. A shorter PDF marks the extra pages stale; search leaves them out. (0.1.34)
- **The proofread is data.** Readers agree or dispute; each change has `by`, a `box` and a state. `accept` refuses overlapping changes and writes a new page version. One model named two times counts as one reader. (0.1.23 to 0.1.34) `nbs/13_proof.ipynb`.
- **Tests call no model.** They replay recorded replies through `CachedChat` from `nbs/chatcache`. A test run overwrites `nbs/chatcache/cache.db`; restore it before a commit. (0.1.28)
- **Do not reflow `PII_SP`, `VAULT_SP` or `TYPE_SP`.** A reflow changes what a model is told. See CLAUDE.md.
