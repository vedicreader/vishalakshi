# Porting `Vault` onto litesearch's `Index`

Date: 2026-08-11
Repos: `litesearch` (0.1.23 → 0.1.24), `vishalakshi`

## Why

litesearch 0.1.23 collapsed four ways to search a corpus into one route, `litesearch.api.Index`,
whose defaults are the configuration `evals/` measures as best or tied-best across three genres.
Its changelog nominates vishalakshi as the first caller to port, and its api page asks three
questions the port should answer. This spec answers them and does the port.

The answers, from reading both sources:

1. **Does `Index.add` cover the ingest vishalakshi does by hand?** No, and that is a gap in
   `Index`, not in the caller. `Vault` needs `kind`, `meta`, `force`, per-file shelf routing and
   per-shelf batching, none of which `Index.add` can express. `Vault` keeps its ingest methods,
   but reshapes `add` so it is a proper *superset* of `Index.add` rather than an incompatible
   shadow of it.
2. **Is the default encoder wrong for it?** No. `static_embedder()` returns
   `potion-multilingual-128M`, which is already vishalakshi's `DFLT_ENC`. The sharper finding is
   that vishalakshi's *per-shelf* encoder map is not supported by any measurement and is removed.
3. **Does `context()` carry the read path?** Yes; `Vault` is already built on
   `context`/`read`/`sections` rather than `search`. But `db.context` now defaults `graph=False`,
   so `Vault.context`'s documentation is stale and its `related` rows are vector-reached only.

## Evidence the design rests on

- **The encoder is not the lever.** Across four encoders the spread is 0.018–0.046 weighted MRR,
  and the static model wins one genre outright while indexing ~1,700x cheaper.
- **Glosses beat the encoder on the Sanskrit corpus.** litesearch's `09_sanskrit` records, measured
  against *vishalakshi's own Sanskrit shelf*, that "a static encoder with glosses beat a 300M ONNX
  transformer without them, at a fraction of the cost." vishalakshi currently pays for the ONNX
  model (`SHELVES['sanskrit'] = 'gemma'`) and gets no glosses: `register_profiles()` runs at import
  with `nlp=None, mw=None`, so `sanskrit_meta` returns `verse_meta` alone: metre, no lemmas, no
  glosses.
- **Rerank is the one lever worth a decision.** +0.026 to +0.077 weighted MRR, positive in all
  twelve paired cells, at ~10x query latency. It needs a fanout of 30 candidates; reranking ten
  only reorders ten.
- **The graph leg is negative on ordinary queries.** −0.070 to −0.160, monotonically worse as
  `graph_w` rises. vishalakshi's traffic is ordinary queries, so it stays off.
- **Vector widths differ across today's shelves**: `potion-multilingual-128M` is 256d,
  `potion-retrieval-32M` and `potion-science-32M` are 512d, `embeddinggemma-300m` is 768d. This is
  the sole reason `Vault` must pass `ndim=` and cannot currently be an `Index`.

## Decisions

| Decision | Choice |
|---|---|
| Sanskrit encoder | static default (256d), with gloss facets switched on |
| Other shelf encoders | collapse to the static default; `SHELVES` stops being an encoder map |
| `Vault`↔`Index` | `class Vault(Index)` |
| Rerank lives | in litesearch's tree legs, so every caller inherits it |
| Gloss facets | lazy and automatic on first Sanskrit ingest |
| `find` vs `search` | `find` is dropped; `search` is the name |
| Migration | none; stale shelves are deleted via a new `drop_shelf` |
| Entity graph | code stays, documentation gains "when this pays off" |

## Part A: litesearch (0.1.24)

### A1. `Index` gains `db=`

```python
def __init__(self, path=':memory:', encoder=None, name='store', ann=True, db=None):
    ...
    self.db = db if db is not None else database(path)
```

This is the only addition needed. With every shelf now at 256d, `ndim=` is unnecessary:
`Index` already relies on `get_store(ndim=None)`. Shelves in one vault file share one connection,
and vishalakshi's `:memory:` tests depend on that sharing: a second `database(':memory:')` is a
different database.

### A2. `rerank=` on the tree legs

`Database.doc_search` and `Database.sections` (in `litesearch/tree.py`, from `nbs/06_tree.ipynb`)
gain `rerank:bool=False`. Each fans out to `max(limit, RERANK_FANOUT)` internally, then calls
`rerank_hits(q, hits, limit=limit)` before returning. For `sections`, the rerank happens on the
chunk hits *before* they are grouped into sections, so grouping sees the reordered list.

`RERANK_FANOUT = 30` moves somewhere both `api.py` and `tree.py` can import it. `Database.context`
needs no change: it already forwards `**kw` to `sections`. `Index.search` drops its hand-rolled
`n = max(limit, RERANK_FANOUT)` branch in favour of the shared one.

Rationale: the fanout discipline is a measured property of reranking, not of any one caller. Put in
`tree.py`, `Index`, `Vault` and every future caller inherit it; put in vishalakshi, the next caller
re-solves it.

### A3. Documentation fix

`CHANGELOG.md` 0.1.23 and the ladder table in `nbs/index.ipynb` both state the default encoder is
`potion-retrieval-32M`. `static_embedder()` returns `potion-multilingual-128M` (commit 470a3b6).
The api page is correct. Reconcile all three to the code.

### A4. Release

`nbdev-prepare`, then release 0.1.24. Part B cannot begin before this lands, because it imports the
new kwargs.

## Part B: vishalakshi core (`nbs/00_core.ipynb`)

### B1. `class Vault(Index)`

```python
class Vault(Index):
    def __init__(self, path=None, encoder=None, store='store',
                 offline=False, dims=256, db=None):
        self.enc = mk_encoder(encoder, dims=dims, offline=offline)
        super().__init__(ifnone(path, Path.home()/'.vishalakshi'/'vault.db'),
                         encoder=self.enc.model, name=store, db=db)
        self._register()
```

Renames, all mechanical:

- `self.g` → the inherited `self.t`
- `self.g.store` → the inherited `self.store`
- `self.g.prefix` → `self.t.prefix`
- `self.qv(q)` → the inherited `self.qemb(q)`
- `self.dtype` → the module-level `DTYPE` imported from `litesearch.api`

`read` and `toc` are inherited. `read` keeps a thin override for its `store=` argument, which
`elsewhere()` needs in order to open a citation that lives on another shelf.

**Collision to handle deliberately:** `Index.docs` is a *list* property; `Vault` uses
`self.g.docs(where=…)` as a callable table. They do not merge. The table stays reachable as
`self.t.docs`, and `Index.docs` coexists harmlessly beside `Vault.sources()`.

**`mk_encoder` shrinks.** Its hash fallback becomes a small object exposing `.encode`, so
`Index` builds `_doc`/`_qry` from it exactly as it would from any model2vec or ONNX encoder. What
survives of `mk_encoder` is: resolve the alias, try to load, warn and fall back, and report
`name`/`dims`/`method` for the `vault_stores` registry. The `doc`/`query`/`dtype` fields of its
`AttrDict` go away, because `Index` now owns them.

### B2. `add` becomes a superset of `Index.add`

```python
@patch
def add(self:Vault, src, title=None, source=None, kind=None,
        meta=None, force=False, **kw)
```

If `src` is an existing path, dispatch to `add_file` or `add_dir` (routing intact); otherwise treat
it as text and dispatch to `add_doc`. This is backward compatible with every existing
`v.add(text, 'Title', kind=…)` call site, folds three entry points into one, and makes `Vault.add`
a proper override rather than a signature-incompatible shadow of the parent.

`add_file`, `add_files` and `add_dir` remain as the narrower explicit forms, which `acquire.py`
calls directly.

### B3. `search` replaces `find`

`Vault.find` is deleted. `Vault.search` overrides `Index.search` with the tree-level behaviour:
`db.doc_search` (span merging, breadcrumbs) plus the `kind` filter, `tidy_bc`, and `rerank`
forwarded to A2. One search behaviour under one name; the flat non-breadcrumb path is not reachable
by accident.

`sections` and `context` stay as overrides (they add the `kind` filter, `tidy_bc`, and (for
`context`) the cross-shelf and code legs) and both forward `rerank`.

### B4. `ENCODERS` and `SHELVES` collapse

`SHELVES` stops being an encoder map and becomes a tuple of known partition names:

```python
SHELVES = ('store', 'papers', 'sanskrit', 'code', 'data')
```

`shelf()` no longer looks an encoder up from it. `ENCODERS` survives only as an override table for
experiments, keeping the four static potions plus `gemma` and dropping `bge-micro`, `modernbert`,
`nomic` and `sanskritgemma`, none of which any measurement here supports.

The `sanskrit_fast` shelf goes with the map, and with it a latent broken assertion: an
`#|eval: false` cell asserts `SHELVES['sanskrit-fast']` (hyphen) while the dict defines
`'sanskrit_fast'` (underscore). It never ran, so it never failed.

`_register` stays. It is now the mismatch detector for a shelf written at 512d or 768d being
reopened at 256d, and its existing "distances across the two are meaningless" warning is the right
message.

### B5. `drop_shelf`

```python
@patch
def drop_shelf(self:Vault, name:str, force:bool=False) -> dict
```

Drops the shelf's `docs`/`nodes`/chunk tables, its ANN index file and its `vault_stores` row.
Refuses `'store'` unless `force=True`. This is the migration story: while datasets are throwaway,
"change the encoder, delete the shelf" should be one call rather than manual SQL.

### B6. Sanskrit gloss facets, lazily

A once-only helper calls
`register_profiles(nlp=vidyut_pipe(), mw=mw_lexicon())` the first time a file is routed to the
`sanskrit` shelf. Guarded by a module flag so it fires once per process, and wrapped so a failure
to download degrades to metre-only rather than raising.

Lazy and automatic, because the measured configuration should be the default, and the ~83 MB
download should only be paid by someone who actually ingests Sanskrit. This matches vishalakshi's
contract: opt-in things, but never cumbersome.

### B7. `graph=` documentation

The markdown above `search` stops promising `related` sections reached "by the entity graph
(`via='graph'`)". `db.context` defaults `graph=False` and vishalakshi does not override it, so
`related` is vector-reached. No `graph=True` is added anywhere: −0.070 to −0.160 on ordinary
queries.

## Part C: `03_code.ipynb`

`Vault.kosha(share_encoder=True)` reads `self.enc.model`. That field survives B1, so this does not
break, but `Index` now holds the same object as `self.encoder`, which is the one to read:
`kw['efn'] = lambda: self.encoder`. One line, but it means the code notebook is touched by the
port, and the `share_encoder` path needs a test since nothing currently exercises it.

## Part D: the front door (`nbs/index.ipynb`, `README.md`)

110 cells to roughly 35, and README from 1037 lines to ~300, on litesearch's structure. The cut
criterion is litesearch's: a section goes only if it already has its own page. vishalakshi has
pages for core, acquire, ask, code, cli, mcp, extract and concepts, so most of it does.

Kept inline:

- **One route**: `grab` → `ask` → `read`, with every `[n]` in an answer resolving to a `node_id`.
- **A decided-vs-opt-in table.** Decided: chunk size, `pre()`, ANN, the tree, the encoder, the FTS
  ASCII fold. Opt-in: `rerank`, shelves, `graph`. Automatic when relevant: Sanskrit glosses. This
  states the "opt-in but never cumbersome" contract once, in a table.
- **Extract**: fields, not prose, with the cue table and `decisive`, because that is the seam
  showing no model was needed.
- **Asking questions about one document with the vault as context**: kept whole; it is what
  `document()` and `context()` exist for.
- **Watches**: `watch`/`poll` as the "keeping it current" close.
- **When `connect()` and `map()` pay off**: multi-hop and cross-shelf discovery, and seeing the
  shape of what you have collected; explicitly *not* ranking. `map()` reads the persisted topic
  nodes after `connect()`, so it is the cheap call.
- **Two cells for the wrapped tools**: `v.grab(target)` for the fossick side, and
  `v.index_code(dir)` then `v.context(q, code=4)` for the kosha side, showing code sections
  numbered alongside prose ones in one answer.

Cut to links: CLI, MCP, the harvest walkthrough, code federation depth, the Sanskrit-shelf and
run-the-code runs, and the doctype/schema reference depth.

Both kosha and fossick are already `@patch`ed onto `Vault` (`url`, `crawl`, `web`, `arxiv`, `pdf`,
`youtube`, `github`, `gh_file`, `grab`, `apis`, `harvest`, `add_records`; and `kosha`, `index_code`,
`code_search`, `symbol`, `where_to_add`, `grep`). Both import lazily inside function bodies, so
they stay optional dependencies. Nothing needs pulling under `Vault`; the front door just needs to
present them that way.

## Files touched

litesearch: `nbs/07_api.ipynb`, `nbs/06_tree.ipynb`, `nbs/index.ipynb`, `CHANGELOG.md`,
`README.md`.

vishalakshi: `nbs/00_core.ipynb`, `nbs/03_code.ipynb`, `nbs/04_cli.ipynb` (`CMDS`),
`nbs/05_mcp.ipynb` (`TOOLS` and the tool-description prose that names `find`), `nbs/index.ipynb`,
`README.md`, `pyproject.toml` (pin `litesearch>=0.1.24`).

## Testing

litesearch: `Index(db=…)` shares the passed connection; `rerank=True` on `doc_search` and
`sections` returns `limit` rows and reorders them; `rerank=False` is byte-identical to today.

vishalakshi, in `00_core`:

- `isinstance(v, Index)`
- a shelf shares `v.db`: the existing `:memory:` assertion must keep passing
- `add()` dispatch across text, a file path and a directory, including the backward-compatible
  `v.add(text, 'Title', kind=…)` form
- every shelf reports 256d in `shelves()`
- `search` hits carry a tidied breadcrumb, and `read(node_id)` opens what the snippet came from
- `drop_shelf` removes the tables, the index and the registry row, and refuses `'store'`

Marked `#| eval: false`: rerank (flashrank is a 4 MB download on first use) and the gloss facets
(vidyut data is ~83 MB). The gloss test asserts `register_profiles` fired once and that a Sanskrit
chunk's `metadata` gained a `gloss` key.

`nbdev-prepare` must pass in both repos.

## Non-goals

- Changing the entity graph beyond documentation. `connect()` keeps serving `map()` and entity
  browsing.
- Turning `graph=True` on anywhere.
- Any migration tooling beyond `drop_shelf`. Stale shelves are deleted, not migrated.
- Making `Index.search` itself use `doc_search`. The ladder puts the tree at a wash for *ranking*,
  so `Index`'s choice of the flat leg is deliberate; `Vault` overrides because it always wants
  breadcrumbs.
