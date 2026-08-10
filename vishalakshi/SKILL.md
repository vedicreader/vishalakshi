---
name: vishalakshi
description: >
  One searchable vault for everything you have read: web pages, papers, video
  transcripts, local files, code and your own notes in a single SQLite file. Use
  to file material, search across all of it at once, and answer questions with
  citations that resolve back to the text.
---

# vishalakshi

A `Vault` is one SQLite file holding everything you have read, searchable as one corpus and
answerable by a local or hosted model. It is a litesearch `Index` with a `kind` on every document,
shelves in the same file, an entity graph, and the acquisition, extraction and code verbs.

**Read `README.md` for the full API and the measured tradeoffs.** This file is the short version.

There is also a pyskill: `import vishalakshi.skill` then `doc(vishalakshi.skill)` gives the same
material to a harness that discovers skills through Python entry points.

## When to use

- **Something you have already read** (a paper, a page, a transcript, your notes) -> vishalakshi.
- **Source code** -> `kosha` first, through `v.index_code` and `v.code_search`. The vault embeds
  prose; kosha embeds identifiers with a code-trained model.
- **Something nothing has indexed yet** -> `v.grep`, which is ripgrep on the working tree.
- **A single document you can name** -> `v.ask_doc(path, q)`. It reads the document rather than
  retrieving from it, and the path need not be in the vault.

## Getting started

```python
from vishalakshi.skill import vault
v = vault()                      # $VISHALAKSHI_VAULT, else ~/.vishalakshi/vault.db
```

## Filling it

```python
v.add('~/notes')                 # a directory, a file, or a string of text
v.grab('1706.03762')             # arXiv id, YouTube url, GitHub repo, PDF url, path
v.note('what I concluded', tags=['retrieval'])
v.connect()                      # the entity graph, after a batch of adds
```

`grab` routes on what the target is, so it is the one call that handles anything. Ingestion is
content-addressed: re-adding the same source is a no-op, not a duplicate.

## Reading it back

```python
v.context(q)                     # start here: whole sections plus what they connect to
v.ask(q)                         # an answer with [n] citations
v.search(q, limit=10)            # chunk hits, each with a breadcrumb and a node_id
v.sections(q, limit=5)           # ranked sections rather than chunks
v.read(node_id)                  # the section behind a citation, in full
```

`context` is what to hand a model. `search` locates a fact you can already name; `sections` is for a
topic. Every hit carries a `node_id`, and `read(node_id)` opens exactly the text it came from, so a
claim can be checked rather than trusted.

Filter any of them by how the document arrived: `v.search(q, kind='pdf')`, or `'note,web'` for
several. Kinds are `web`, `pdf`, `arxiv`, `youtube`, `file`, `code`, `data`, `note`, plus whatever
the file parser called it. The filter is SQL pushed into the search, not a pass over the results.

## Paperwork, as fields rather than prose

```python
v.categorize(ref, llm='never')   # invoice? paper? contract? a cue table, no model
v.extract(ref)                   # the doctype picks the schema
v.extract(ref, schema='vendor:str, total:float, due_date:str')
v.extract_all(doctype='invoice') # one row per invoice in the vault
```

`decisive=True` on a `categorize` result means the cue table had a clear winner and no model was
needed. Only the fields need one.

## Code

```python
v.index_code(dir)                # fills kosha: AST chunks, symbols, a call graph
v.code_search(q); v.symbol(name); v.where_to_add(desc); v.grep(pat, dir)
v.federate(q, dir=dir)           # vault + kosha + ripgrep, fused by rank
```

Once a repo is indexed, `context` appends code sections on its own. It decides by looking for
`.kosha/code.db` on disk rather than by loading anything, so a question with no use for code pays
nothing.

## What is decided, and what is yours

Retrieval defaults are litesearch's measured ones, and there is nothing to pick: 512-character
chunks, a preprocessed keyword leg, an HNSW vector leg, a document tree, one static 256d encoder,
and a script fold that makes Devanagari and IAST reach the same row.

| yours | what it buys |
|---|---|
| `rerank=True` on `search` / `sections` / `context` | +0.026 to +0.077 weighted MRR, ~10x latency |
| `v.shelf(name)` | a partition, so two corpora stop diluting each other's ranking |
| `llm=` on `categorize` / `extract` | how hard to try before giving up on the cue table |
| `db.graph_search` | the entity-graph leg by name, for bridge queries |

The graph leg is off for ranking and should stay off: it costs 0.070 to 0.160 weighted MRR on
ordinary questions. It wins only where the answer shares no word with the question.

`v.connect()` builds the graph and `v.map()` reads its topics. Neither ranks anything. They answer
what is in here and what connects to what, which is the question you ask before you know what to
search for.

## Knowing what you have

```python
v.stats()                        # counts, by kind
v.sources()                      # every document and why it is in the corpus
v.toc()                          # the shape of it
v.map()                          # topics, after connect()
v.related(node_id)               # what else reads like this
```

## Careful with

`forget`, `drop_shelf`, `unwatch` and `pause` delete things, and are deliberately excluded from the
pyskill's `allow` registry so sandboxed code cannot reach them.

A shelf's encoder cannot be changed in place, because an ANN index holds exactly one vector space.
Drop the shelf and re-ingest.

Ingesting Sanskrit switches on vidyut lemmas and Monier-Williams glosses by itself, once, which is
an ~83 MB download the first time.
