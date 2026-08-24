# Making vishalakshi thin

Date: 2026-08-24
Repos: `vishalakshi`, `litesearch`, `fossick`, `kosha`

## The finding

vishalakshi is not one library. It is 3,210 lines of definitions across ten modules, and 1,446 of
them (45%) are three self-contained products that do not need a vault to exist:

| product | lines | depends on the vault for |
|----|----|----|
| PII detector (`pii.py`) | 416 | nothing. `pii_spans`, `pii_report`, `redact` import `re` and `fastcore` |
| doctype + extraction (`extract.py`) | 551 | `document()` for text, `new_chat` for a model |
| corpus-quality ranker (`quality.py`) | 479 | the chunk table and its stored vectors |

The vault proper is 1,377 lines (`core` 568, `acquire` 481, `jobs` 206, `code` 122), `ask` is 304,
and the entire CLI plus MCP surface is 83. The CLI is already the right shape: 71 commands and 67
MCP tools from 83 lines of reflection over `Vault`'s signatures.

So "thin" is two separate problems. The vault machinery is 1,377 lines wrapping three libraries
that already do the work, and that number should fall. The 1,446 lines of embedded products will
not fall by leaning on litesearch, because litesearch is not where they belong.

## Why the vault machinery is not already thin

Four causes, each measured.

**1. Eight acquisition methods that are one method (178 lines).** `url`, `crawl`, `web`, `arxiv`,
`pdf`, `youtube`, `github`, `gh_file` all do the same three steps: ask fossick to read the target,
turn what came back into markdown, hand it to `add` with a `kind` and a `meta`. They are eight
methods because fossick returns a different shape from each reader (`read_arxiv` a dict with
`summary`, `read_yt` a dict with `source`, `fetch` a page object needing `to_md`, `research` a list
of sources), so vishalakshi reshapes each one by hand. `what_is` then re-derives from the target
string what the caller was about to say anyway.

**2. A cross-cutting gate wired by hand at nine sites.** `pii=` and `pii_ner=` are parameters on
`search`, `sections`, `context`, `read`, `document`, `toc`, `federate`, `ask` and `explain`. Each
one calls `_gate` itself. The policy is one thing; it is spelled out nine times.

**3. Three things litesearch should own (326 lines).**

- `Queue` (206 lines). Its own docstring is "an at-least-once job queue inside an open litesearch
  database". It imports `write_txn` and `BUSY_TIMEOUT_MS` from litesearch and nothing from
  vishalakshi. The only mention of the vault in the file is its module docstring.
- Topic presentation: `map`, `_map_from_graph`, `topic_tree`, `fmt_topics`, `show_topics`,
  `_sql_in` (117 lines). Reads `entities` where `kind='topic'` and `mentions` — tables litesearch's
  `topic_nodes` writes. Nothing in it is vault-specific.
- `tidy_bc` (3 lines, 7 call sites). litesearch `tree.py:183` opens window nodes titled
  `Pages 1–3: <lead>`, and `Database.breadcrumb` puts them in the path. vishalakshi strips them
  out of every breadcrumb it shows. The fix belongs at line 183, not at seven call sites.

**4. 119 public `Vault` methods, 39 of them one or two statements.** `code_search`, `where_to_add`,
`symbol` forward to `Kosha`. `dead`, `pending`, `history`, `ack`, `on`, `register` forward to
`Queue`. `assets`, `add_file`, `forget` forward to `Database`. Each costs a signature, a docstring,
a `_modidx` entry, a CLI slot and an MCP tool.

## What moves, and where

Additive changes to the libraries first; vishalakshi deletes after each one releases.

| # | move | lines out of vishalakshi | into | notes |
|----|----|----|----|----|
| 1 | `Queue`, `Retry`, `backoff` | 206 | `litesearch.jobs` | pure move, no API change |
| 2 | topic presentation | 117 | `litesearch.graph` | `topic_tree(db, store)`, `fmt_topics` |
| 3 | `tidy_bc` | 3 (+7 call sites) | `litesearch.tree` | strip window titles in `breadcrumb` |
| 4 | one reader shape | 178 → ~40 | `fossick.read` | see below |
| 5 | noise features + `Ranker` | 479 → ~120 | `litesearch.quality` | generic over any store |
| 6 | federate row shaping | 122 → ~55 | `kosha` | `Kosha.rows(q)` in the fused shape |
| 7 | image/EXIF ingest | 90 | `fossick` | `exif_meta`, `image_md` read files, not vaults |

Totals: 1,195 lines of vishalakshi become roughly 215.

### 4 in detail: `fossick.read`

The one change with the best ratio. fossick already has every reader; what it lacks is a single
shape and a single door.

```python
# fossick
def read(target:str,      # url, arXiv id, YouTube link, GitHub repo or file, PDF, local path
         **kw
) -> AttrDict:            # (kind, title, md, source, meta)
    'Read anything into markdown, by looking at what it is.'
```

`what_is` moves with it: fossick already knows how to tell an arXiv id from a YouTube link, it just
does not say so out loud. vishalakshi's whole acquisition surface then becomes:

```python
@patch
def grab(self:Vault, target:str, title:str=None, shelf:str=None, **kw):
    r = fossick.read(target, **kw)
    v = self.shelf(shelf) if shelf else self.route(r.kind)
    return v.add(r.md, title or r.title, source=r.source, kind=r.kind, meta=r.meta)
```

`url`, `arxiv`, `pdf`, `youtube`, `github`, `gh_file` stay as named methods only because the CLI and
MCP surface them; each is then one line.

### 5 in detail: what actually moves

The measured part stays measured. `NOISE_FEATURES`, `NOISE_W` and the 0.988 AUC in
`evals/RESULTS.md` are properties of the feature set, not of the vault, and the features are
computed from `chunk_matrix`: chunk ids, doc ids, texts and stored vectors. Every litesearch store
has those. What stays in vishalakshi is the policy layer: `mark_noisy`, `accept_noisy`, `use_noise`,
and `_noisy_sql` splicing the anti-join into `_where`.

## What does not move

- **`pii.py`.** 34 kinds, 19 regional checksums, 1.000 precision at recall 1.000 held out. It is
  the reason to use vishalakshi and it belongs to no other repo. It should be its own package for
  the same reason litesearch is: other callers want it without a vault.
- **`extract.py`.** Doctype cues and the schema set are vishalakshi's own. `structured()` is rishi
  plumbing and could go there; the rest stays.
- **`ask.py`.** The prompts, the citation parse, the local-runtime pii routing. `CachedChat`
  (52 lines) belongs in rishi.
- **`cli.py` and `mcp.py`.** Already the target shape.

## The one-file question

Not reachable, and not the right target. With every move above done, vishalakshi is:

| file | lines |
|----|----|
| `pii.py` | 416 |
| `extract.py` | 551 |
| `core.py` (vault, shelves, marks, retrieval seam) | ~300 |
| `ask.py` | ~250 |
| `acquire.py` | ~90 |
| `quality.py` (policy only) | ~120 |
| `code.py` | ~55 |
| `cli.py` + `mcp.py` | 83 |

About 1,865 lines against 3,210 today, a 42% cut, with the acquisition and job-queue surfaces gone
entirely. The floor is set by `pii` and `extract`, which are 967 lines of the 1,865 and are not
seam. One file is achievable only by splitting those two out as their own packages, at which point
`vishalakshi` is roughly 900 lines and could be one module. That is a packaging decision, not a
simplification, and it should be made on whether anyone wants the PII detector without the vault.

## Sequencing

Each move is two pull requests, because vishalakshi cannot import what is not released.

1. Library PR: add to litesearch / fossick / kosha, with tests, no behaviour change to existing
   callers.
2. Release the library.
3. vishalakshi PR: delete the local copy, raise the dependency floor in `pyproject.toml`.

Moves 1, 2, 3 and 7 are pure lifts and can go in one library release each. Move 4 changes fossick's
public surface and should land alone. Move 5 needs `evals/noise.py` re-run against the moved code
before vishalakshi deletes its copy; the RESULTS.md number is a claim about this code and has to
survive the move.

Three changes need no library release and can land in vishalakshi immediately:

- Collapse the nine hand-wired pii gates into one decorator applied at the retrieval boundary.
- Reduce the 39 passthrough methods to forwarding, or drop the ones the CLI does not need.
- Table-drive the eight acquisition readers behind one dispatcher, so move 4 later becomes a
  deletion rather than a rewrite.

## Loose ends found on the way

- `label_images` (`acquire.py:595`) raises `ImportError` asking for `anya`, which is in no
  dependency group. It is registered as an MCP tool.
- `Vault` overrides `search`, `sections`, `context` and `read` to add a `where` clause, but
  litesearch's `Index` already forwards `**kw` to `Database.sections`/`context`/`read`, and `where=`
  reaches `Database.search` through `doc_search`. The overrides exist for `tidy_bc`, `_gate` and
  `_post`; once those three are handled, three of the four can go.
