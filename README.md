# vishalakshi

> one vault for everything you read: web, papers, video, files and code, searchable together and answerable by a local or hosted model

Vishalakshi is the thin layer that makes five tools one thing. [fossick](https://github.com/vedicreader/fossick) gets material off the web, [litesearch](https://github.com/Karthik777/litesearch) stores and retrieves it, [rishi](https://github.com/vedicreader/rishi) answers from it, [kosha](https://github.com/vedicreader/kosha) does the same for code, and [rgapi](https://github.com/AnswerDotAI/rgapi) greps what nothing has indexed yet. A `Vault` is one SQLite file where all of it lands in the same store, so a single question crosses a paper you read in March, a page you scraped last week, a talk you watched, your own notes, and the source tree on your disk.

Thin is the design: each method is one call into the library that already does the work, plus the provenance that says why the result is in your corpus. There are no wrappers over their APIs to keep in sync.

## Install

```sh
pip install 'vishalakshi[all]'   # + rishi to answer, + kosha & rgapi for code, + mcp for the server
pip install vishalakshi          # vault + acquisition only; no LLM, no MCP
```

## The loop

```python
from vishalakshi import Vault

v = Vault()                                     # ~/.vishalakshi/vault.db

v.web('late chunking retrieval', n=5)           # search the web, read the hits, file them
v.arxiv('2409.04701')                           # a paper, full text
v.youtube('https://youtu.be/...')               # a talk, transcribed
v.add_dir('~/papers')                           # PDFs and markdown you already have
v.code('~/src/litesearch')                      # a source tree
v.note('Late chunking beats naive chunking '
       'mainly because context survives the split.')

v.connect()                                     # build the entity graph over all of it
```

`v.grab(target)` does whichever of those the target names — a URL, an arXiv id, a YouTube link, a PDF, a file or a directory — which is the one call a script or an agent needs.

Then ask it something:

```python
r = v.ask('why does late chunking help?')
print(r.answer)
for c in r.cited:
    print(c['n'], c['breadcrumb'], c['node_id'])
    print(v.read(c['node_id'])['text'])          # the exact text behind the claim
```

Every `[n]` in the answer resolves to a `node_id` you can read. That round trip is the point: an answer you can check, not one you have to believe.

## What retrieval actually returns

`v.context(q)` is the primitive underneath `ask`. It returns whole **sections** — the unit worth reading — not fragments:

```python
c = v.context('how does multi-head attention work')
for r in c.results:  print(r.breadcrumb, r.pages, len(r.text))
for r in c.related:  print(r.breadcrumb, 'via', r.via)   # 'graph' or 'vector'
```

`results` are the sections that answer the question. `related` are sections reached *by association* — along the entity graph (`via='graph'`) or by embedding similarity (`via='vector'`) — which is how you find the thing you did not know to search for. `c.encoder` always says which embedder answered, because degrading from real semantics to hashing changes what the results mean.

## Everything in one corpus

Each document carries a `kind`: `web`, `pdf`, `arxiv`, `youtube`, `file`, `code`, `data`, `note`. Filter when you want to, don't when you don't:

```python
v.find('attention', kind='note')          # only what you concluded
v.find('attention', kind='arxiv,web')     # only what you collected
v.find('attention')                       # everything, ranked together
```

The filter is a SQL `WHERE` pushed into litesearch's search, not a pass over the results afterwards, so a narrow filter over a large vault still returns a full page of hits.

Notes are ordinary documents, deliberately. The graph, the clusters and `context()` all see them for free, so what you concluded about a corpus comes back next to the evidence you concluded it from.

## Knowing what you have

```python
v.sources()        # every document, where it came from, and which query found it
v.toc()            # the table of contents across the whole vault
v.map()            # labelled topic clusters — the shape of the collection
v.related(node_id) # what else reads like this section
v.stats()          # counts by kind, and the active encoder
```

Provenance is kept at ingest, so months later `sources()` still says *why* a document is in your corpus.

## CLI

```sh
vishalakshi grab https://example.com/post     # or a file, a directory, an arXiv id, a YouTube URL
vishalakshi web "late chunking retrieval"     # search and ingest in one step
vishalakshi note "..." --tags retrieval
vishalakshi connect                           # build the graph after a batch of adds
vishalakshi context "why does late chunking help"
vishalakshi ask "why does late chunking help"
vishalakshi sources; vishalakshi map; vishalakshi toc
```

Every `Vault` method is a command, and every command's `--help` is generated from the method's own signature and docments — so `vishalakshi <cmd> --help` is never out of date, and there is no wrapper per command in the source.

`$VISHALAKSHI_VAULT` picks the vault file, `$VISHALAKSHI_MODEL` the model `ask` uses, `$VISHALAKSHI_OFFLINE` forces the hashing encoder.

## MCP

`vishalakshi-mcp` exposes the vault to any MCP client — Claude Code, Codex, or anything else that speaks the protocol:

```json
{"mcpServers": {"vishalakshi": {"command": "vishalakshi-mcp",
                                "env": {"VISHALAKSHI_VAULT": "~/.vishalakshi/vault.db"}}}}
```

Thirty-two tools, built from the same `Vault` methods the CLI uses, so each tool's schema and description are the method's signature and docstring. `context` and `find` for reading, `ask` for answering, `grab` / `web` / `arxiv` / `youtube` / `add_file` / `add_dir` / `note` for filling it, plus `toc`, `map`, `sources`, `related`, `read`, `connect` and `forget`. An agent that can write notes back into the same vault it reads from accumulates rather than restarts.

## Models and backends

`ask` goes through rishi, which has four backends. rishi picks one from the **shape** of the model id, so a bare marketing name (`gemma-3-4b-it-int4`) matches nothing and is rejected rather than guessed at. Name a real id, use an alias, or say the runtime.

| runtime | what it is | model ids look like | needs |
|---|---|---|---|
| `litert` | Google LiteRT, CPU — **the default** | `litert-community/…`, `*.litertlm` | nothing; runs anywhere |
| `mlx` | Apple silicon | `mlx-community/…` | macOS on ARM |
| `llama` | llama.cpp, any GGUF | `*-GGUF`, `*.gguf` | `pip install 'rishi[llama]'` |
| `remote` | hosted, via fastllm | `claude-sonnet-5`, `gpt-…`, `gemini-…` | an API key |

```python
v.ask(q)                                   # litert-community/gemma-4-E2B-it-litert-lm on CPU
v.ask(q, model='qwen-4b-mlx')              # alias -> mlx
v.ask(q, model='sonnet')                   # alias -> hosted Claude
v.ask(q, model='mlx-community/Qwen3-4B-4bit')    # full id, runtime inferred
v.ask(q, model='my-local.gguf', runtime='llama') # say it outright when the id can't
```

`vishalakshi.ask.MODELS` lists the aliases. The vault never needs the network to *retrieve* — only to answer with a hosted model.

## Code: kosha, ripgrep, and federated search

`v.code(dir)` files source files as ordinary documents. `v.index_code(dir)` is the real code path — it fills **kosha's** stores: AST chunks, symbol names, and a call graph with PageRank.

```python
v.index_code('~/src/litesearch')            # {'files': 42, 'graph_nodes': 1982, ...}

v.code_search('rank fusion')                # semantic + keyword over the repo
v.code_search('retry package:httpx')        # kosha's key:value filters work
v.symbol('litesearch.core.rrf_merge')       # pagerank, degree, callers, callees
v.where_to_add('cache the encoder per store')   # file:line where a change belongs
v.grep('rrf_all', '~/src/litesearch')       # ripgrep, gitignore-aware
```

Then search all of it at once:

```python
f = v.federate('rank fusion of ranked lists')
for h in f.hits: print(h.source, h.where)
# prose  Reciprocal Rank Fusion › RRF › Why it works
# repo   /src/litesearch/graph.py:697
# grep   /src/litesearch/core.py:365
```

Three kinds of evidence, three kinds of blindness. The vault embeds prose; kosha embeds identifiers with a code-trained model, deliberately, because code embeds badly under a prose encoder; ripgrep embeds nothing and sees the file as it is on disk right now — including the file nothing has indexed and the edit made a minute ago. **The legs share no vector space**, so `federate` fuses their *rankings* with RRF, never their distances. Ranking is the one thing that survives a change of encoder, and it is the same mechanism litesearch already uses to combine FTS with vectors. Each leg runs independently: `f.legs` reports what each contributed, or why it could not.

## Harvest: read a page's API, not its HTML

Listing, product and dashboard pages render from an internal JSON API. fossick can watch a page and capture those calls; the vault turns them into searchable records.

```python
v.apis('https://www.example-retailer.com/browse/dairy')
# [0] .../api/bff/products?page=1   records: 24   {"results":[{"sku":...

v.harvest('https://www.example-retailer.com/browse/dairy', pages=5)
# {'kind': 'data', 'records': 120, 'endpoint': '.../api/bff/products'}

v.find('free range eggs')     # each product is its own retrievable section
```

Each record becomes a `##` section, so it gets its own tree node and breadcrumb rather than being buried in one blob. `session=True` captures through your logged-in Chrome, so pages behind a login work too. `add_records(...)` files a list of dicts you already have.

## Watches: keeping it current

```python
v.watch('https://example.com/changelog', action='url',     every='6h')
v.watch('late chunking retrieval',       action='web',     every='1d', n=5)
v.watch('https://shop.example/dairy',    action='harvest', every='12h', pages=5)
v.watch('Re-read the eval numbers',      action='remind',  every='1w')

v.watches(due_only=True)   # what is ready to run
v.poll()                   # run them; failures are recorded, never raised
```

`poll()` is the tick — call it from cron, a scheduler, or a frontend button. An action is just the name of an acquisition method, so anything you can file once you can file on a schedule; `remind` writes a note with no network involved. One dead URL never stops the loop.

## Encoders

The vault wants a real embedder and will fetch a small model2vec one by default. Where that is impossible — an air-gapped box, a blocked registry — it degrades to litesearch's deterministic `hash_embed` rather than failing, and says so in `stats()['encoder']` and on every `context()` result. Retrieval still works; it is lexical rather than semantic, and you should know which you are getting.

```python
Vault(encoder='minishlab/potion-science-32M')   # pick a different one
Vault(offline=True)                             # never attempt a download — also the CI default
```

## Development

The notebooks in `nbs/` are the source; the modules are generated.

```sh
pip install -e '.[all]'
nbdev_prepare
```
