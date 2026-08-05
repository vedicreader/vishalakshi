# vishalakshi

> one vault for everything you read: web, papers, video, files and code, searchable together and answerable by a local or hosted model

Vishalakshi is the layer that makes four tools one thing. [fossick](https://github.com/vedicreader/fossick) gets material off the web, [litesearch](https://github.com/Karthik777/litesearch) stores and retrieves it, [rishi](https://github.com/vedicreader/rishi) answers from it, and [kosha](https://github.com/vedicreader/kosha) does the same for code. A `Vault` is one SQLite file where all of it lands in the same store, so a single question crosses a paper you read in March, a page you scraped last week, a talk you watched, your own notes, and the source tree on your disk.

## Install

```sh
pip install 'vishalakshi[all]'   # + rishi for answering, + mcp for the server
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

Each document carries a `kind`: `web`, `pdf`, `arxiv`, `youtube`, `file`, `code`, `note`. Filter when you want to, don't when you don't:

```python
v.find('attention', kind='note')          # only what you concluded
v.find('attention', kind=['arxiv','web']) # only what you collected
v.find('attention')                       # everything, ranked together
```

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
vishalakshi add https://example.com/post      # or a file, a directory, an arXiv id, a YouTube URL
vishalakshi web "late chunking retrieval"     # search and ingest in one step
vishalakshi note "..." --tags retrieval
vishalakshi connect                           # build the graph after a batch of adds
vishalakshi context "why does late chunking help"
vishalakshi ask "why does late chunking help"
vishalakshi sources; vishalakshi topics; vishalakshi toc
```

`$VISHALAKSHI_VAULT` picks the vault file, `$VISHALAKSHI_MODEL` the model `ask` uses.

## MCP

`vishalakshi-mcp` exposes the whole vault to any MCP client — Claude Code, Codex, or anything else that speaks the protocol:

```json
{"mcpServers": {"vishalakshi": {"command": "vishalakshi-mcp",
                                "env": {"VISHALAKSHI_VAULT": "~/.vishalakshi/vault.db"}}}}
```

Eighteen tools: `context` and `search` for reading, `ask` for answering, `add_url` / `add_web_search` / `add_arxiv` / `add_youtube` / `add_file` / `add_dir` / `add_note` for filling it, plus `toc`, `topics`, `sources`, `related_sections`, `read_section`, `build_graph` and `forget`. An agent that can write notes back into the same vault it reads from accumulates rather than restarts.

## Models

`ask` goes through rishi, which picks its backend from the model id: a `litert-community` id or a `.litertlm` build runs on LiteRT, a `.gguf` on llama.cpp, an `mlx-community` id on MLX, and a hosted name like `claude-sonnet-5` through fastllm. Local and cloud are the same call, and the vault never needs the network to *retrieve* — only to answer with a hosted model.

## Encoders

The vault wants a real embedder and will fetch a small model2vec one by default. Where that is impossible — an air-gapped box, a blocked registry — it degrades to a deterministic char-n-gram hashing embedder rather than failing, and says so in `stats()['encoder']` and on every `context()` result. Retrieval still works; it is lexical rather than semantic, and you should know which you are getting.

```python
Vault(encoder='minishlab/potion-science-32M')   # pick a different one
Vault(offline=True)                             # never attempt a download
```

## Development

The notebooks in `nbs/` are the source; the modules are generated.

```sh
pip install -e '.[all]'
nbdev_prepare
```
