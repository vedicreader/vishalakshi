# Plan: books and scans read by models, in vishalakshi; search speed-ups, in litesearch

Three packages change: **litesearch** (search primitives), **vishalakshi** (reading, checking and proofreading documents), and a new **vedicreader package** (verse structure and Indic book helpers). Leela and the vedicreader app then use them. Sources are vedicreader `tools/` and `vr/`; line numbers are from the 2026-10-18 survey.

## What exists today
- vishalakshi: `Vault.pdf` → `litesearch.pdf_parse` → `pdflite.pdf_md`: pdf-oxide text layer, liteparse OCR only when pdf-oxide calls the page scanned. No model reading, no quality check. `06_extract` has `model_cached` and accept/reject flows; `10_quality` has `suggest_noisy`/`accept_noisy`; `11_jobs` is a durable queue (retries, leases, dead letter).
- vedicreader: books are read page by page by a vision model through rishi (`tools/ocr.py:281-363`, 626), proofread by three readers with provenance and crops (`tools/proofread.py`), linted for Indic script faults (`tools/lint.py:59-66`, `tools/common.py:160-184`), reviewed by the owner (`work_steps.py:390-453`, `vr/align/work_steps_ui.py:188-228,638`), and structured into verses (`ocr.py:386-485`, `granth.py`). `vr/align` is the owner UI and job runner (`vr/align/work.py`); it uses none of the pipeline modules, but `tools/proofread.py:300`, `tools/lint.py:15`, `tools/common.py:10` and `tools/work*.py` import `vr.align`.

## Phase L: litesearch (independent, first)
L0. Leela: raise `litesearch>=0.1.34` to the current release (0.1.40 has `rank_fts`, `correct`, `fts_or`, `fts_phrases`, `fts_vocab`, `roman_fold(doubles=)`); vishalakshi already needs `>=0.1.36`.
L1. `Table.fts_sig()`: a persistent content signature from the FTS5 structure row (`_fts_data id=10`) plus an mtime throttle of the DB and WAL. Source `vr/shlokas/setup.py:212-248`, `access.py:917`. In-process caches already see other connections' commits through `pragma data_version` (`core.py:602`); `fts_sig` is the on-disk key L2 needs, stable across processes and restarts.
L2. `litesearch.store.stored(name, build, key)`: build arrays once under an `fcntl` lock, rename atomically, load with `np.load(mmap_mode='r')`, keyed by `fts_sig` + library versions. Source `access.py:916-948`. Several Leela or vault processes share pages.
L3. Memory-mapped exact vector matrix beside `vec_search`/`get_index` (unit float32, `m @ v`), invalidated by a vector meta token. Source `setup.py:121-141,851-920`.
L4. `KeyIndex(keys, rows).lookup(k, prefix=True)` on L2: sorted UTF-8 key blob + offsets, bisect. Source `access.py:871-914`. Typeahead and alternate keys FTS5 cannot express.
L5. `Database.fts_merge()` (the FTS5 `optimize` merge, not `PRAGMA optimize`, which apsw already runs on open, `core.py:559`) and `database(open_optimize=False)`. Source `setup.py:507`, `vr/core/cfg.py:13-21`. Measured 18 ms → 4.4 ms per search after bulk writes.
L6. Folding extras: `roman_fold(numbers=True)`, English kept as spelt beside the folded key, consonant-skeleton near match (`correct(..., skeleton=True)`), Tamil key. Source `access.py:727-738,788-795,969`.
Each lands in its litesearch notebook with tests, then a release; vedicreader switches its copies to the imports.

## Phase D: pdflite (per-page routing)
D1. `pdf_md` OCRs the whole PDF when any page is scanned (`pdflite/core.py:97-99`). Split it so each page carries its own route, and expose the per-page text-layer result with `needs_ocr`, `scrambled_layout` and `orphan_vals` scores, which V3 reuses.

## Phase S: vishalakshi schema
S1. New tables, per store (the `sanskrit_` shelf has its own, `core.py:197-205`): `pages(did, page, version, route, text, quality, at)`, `readings(did, page, reader, model, preset, items, cost, at)`, `proof_changes(id, did, page, before, after, by, crop, state, at)`. litesearch's `docs`/`nodes`/chunks stay the search index.
S2. Re-index from `pages`: rebuild one document's tree from its current page texts. A whole-document re-add for now (`add_doc(force=True)` rebuilds the tree, `tree.py:325-327`); page-level re-index later needs stable node ids in litesearch.
S3. Model reads do not run in `_parse_doc`'s process pool (`tree.py:408`): the text-layer pass ingests as today through a litesearch `Profile` (`data.py:231-272`), and model reads run as jobs after it, updating `pages` and re-indexing.

## Phase J: vishalakshi jobs
J1. `claim(kind=, key=)` and a running-count cap per key (the model), since `drain` is serial and `claim` cannot filter (`jobs.py:117-120,215-228`). Workers in separate processes already claim safely.
J2. Lease longer than a model read, or renewed while it runs (600 s now, `jobs.py:47`). Retries are the queue's alone; the handler does not loop (and `ocr.py:348`'s reuse of `k` is not ported).

## Phase V: vishalakshi reading (new notebooks after 11_jobs)
V1. `12_pages`: render a page with `pdf_oxide.PdfDocument.render_page(page, dpi, format, jpeg_quality)` (bytes; no poppler), and `render_page_fit` for the 3000 px cap; DPI per document, optional spread split and overlapping strips (`ocr.py:281-319`). Images, and scanned image files (png/jpg/tiff), cached in the vault's assets by document id and page.
V2. `13_read`: `read_page(doc, page, model=, preset=)` through `vishalakshi.ask.CachedChat` (`ask.py:340`; its cache key covers image bytes), JSON `{"items":[{kind, n, text}]}`, the queue's retries only, `c.close()` after each call, usage cost recorded, the previous reading kept aside on a re-read (`ocr.py:330-363`). Presets are prompt templates with `{script}` and `{hint}`: generic, `sanskrit` (`SP`, `ocr.py:215-223`), `tamil`, `tables`; a package can register more. Runs as `11_jobs` jobs, N at a time, with a per-model concurrency cap (the missing rate limiter).
V3. `14_check`: page checks that decide the route and flag pages, reusing pdflite's scores (D1):
   - text-layer quality: empty or thin text on an inked page, replacement characters, a Devanagari/Tamil font yielding Latin (legacy-font mojibake, new), plus the Indic lint: a line starting with a dependent sign, malformed akṣaras (`common.py:160-184`), foreign script inside Devanagari (`lint.py:59-66`);
   - two-reader comparison: letter-only Levenshtein ratio, flag at ≥ 10% (`ocr.py:546-585`);
   - `parse='auto'`: text layer when it passes, model reading when it fails (model from `$VISHALAKSHI_MODEL` until V6 names defaults); `'text'`, `'ocr'` (liteparse), `'llm'` force a route. Each page records the route that produced it.
V4. `15_proof`: the three-reader proofread as data: readings, disputes (letter diff), A/B confirm against the image, changes with `by` provenance and a crop (`proofread.py`, `work_steps.py:390-453`). Review follows `10_quality`'s suggest/accept shape: `proof_changes(doc)`, `accept_changes(doc, ids)`, `reject_changes`, then apply as a new text version of the page; `proof_md(doc)` writes PROOFREAD.md (Changed / Not taken).
V5. API on `Vault`: `pdf(..., parse='auto', model=None, preset=None)`, `add_file(...)` likewise for images, `reparse(doc, pages=None, model=, preset=)`, `page_text(doc, page)` with its route and versions; re-chunk and re-index only the pages that changed.
V6. `16_eval`: score models against hand-checked pages, strict and lenient (`data/ocr_eval/score.py`, `refs.py`), so `auto` can name a default model per preset.
Out of scope for vishalakshi: audio (aeneas, Whisper, vocals in `vr/align/engine.py`, `hear.py`).

## Phase P: the vedicreader package (name to choose)
On vishalakshi: verse-number mending and renumbering (`ocr.py:386-485`), colophon and verse-1 chapter assembly, plan/count gating (`granth.py:796`), reference similarity (`granth.py:569`), `wsed` (Wikisource to verses), `synth.meter_of`/`SYNTH_CATS`/`SV`, `fix.py` repairs, morae word spans, the work STEPS. It removes the `tools/* → vr.align` reverse imports. The app keeps routes, UI, `BOOKS` hints, `tools/data/*`, and the DB glue.

## Phase U: Leela
Vault settings: reader route (auto / text / OCR / model) and the model (local or cloud, through the same model picker); a "re-read with a model" action on a document or page range; a review pane showing each change beside its crop, with accept/reject; per-page route badges.

## Order
L0 → L1 → L5 → L2 → L4 → L3 → L6 (each a small release). D1, S1–S3 and J1–J2 before V. V1 → V2 → V3 → V5 → V4 → V6. P after V2–V4 exist. U after V5. vedicreader switches to each piece as it ships.

## Tests per step
Each notebook carries its own tests (nbdev). L: cross-process invalidation (write from a second process changes `fts_sig`), mmap store built once by two processes, KeyIndex prefix/exact, optimize timing smoke. V: render a page, a cached read is not re-requested, a failed read retries then dead-letters, preset rendering, mojibake and orphan-sign detection on fixtures, compare flags a ≥10% page, `auto` routes a garbled page to the model, proofread changes carry provenance and crops, accept applies only chosen ids, reparse re-indexes only changed pages. Model calls in tests use rishi's chat cache (`nbs/chatcache`), never the network.
