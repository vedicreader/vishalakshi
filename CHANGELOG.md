# Release notes

<!-- do not remove -->

## 0.1.35
- Needs litesearch>=0.1.61. litesearch 0.1.61 loads adhara, a native SQLite extension, into the vault's connection. A search with a `kind` filter now ranks its vectors with adhara on all cores. The hits are the same as before.

| 10 searches on a vault of 181,290 chunks | 0.1.34 | 0.1.35 |
|---|---|---|
| no filter | 46 ms | 49 ms |
| `kind='web'` | 100 ms | 110 ms |
| `kind='note,pdf,md'` | 517 ms | 89 ms |

## 0.1.34
- Re-reading a shorter PDF marks pages beyond its end stale and keeps their reading history. Retrieval excludes stale pages by default. Pass `stale=True` to include them through a temporary in-memory index. `prune_stale(doc_id=None, dry_run=False)` reports or deletes stale page readings on the current shelf.
- Default change: the privacy gate raises database query errors. Before, it ignored these errors and could treat a Local only shelf as Open.
- Default change: `reshelf` raises `ValueError` when a document to move exceeds `max_chars`. The original stays on its shelf. Before, it saved a truncated copy and deleted the original. Increase `max_chars` to move documents longer than the default 2,000,000 characters.
- `reshelf` keeps the original when the destination returns no document id or chunks, or has no stored document. It raises `RuntimeError` in these cases. Before, it deleted the original without checking the destination result.
- `Vault.read_doc(pages=...)` keeps stored readings of pages you did not request. Before, text-layer rows replaced those pages' model readings.
- `Vault.read_doc` keeps an existing page reading when privacy rules block a new reading. Before, the blocked page's text layer replaced its model reading.
- `Vault.read_doc` keeps stored readings of unread or failed pages. Before, cancellation or an exhausted retry replaced those readings with text-layer rows.
- Default change: `Vault.read_doc` gives each file in a folder its own cache path, including its relative path and extension. Before, files with the same stem shared cached readings. Folder reads do not reuse the old stem-only caches. Read those files again to fill the new caches.
- Folder reads include files when the requested folder or one of its parents has a hidden name. They still skip hidden files and subfolders below the requested folder. Before, a hidden name anywhere in the full path excluded the file.
- `add(directory, force=True)` passes `force` to `add_dir`. Before, `add` ignored `force` for a directory.
- Default change: `add` raises `ValueError` if you pass `source` or `meta` with a file or directory path. Use these arguments with text instead. Before, `add` ignored them for paths.
- `reject(doc_id, ids)` rejects only open proof changes for that document on the current shelf. It returns the number of changes it rejected. Before, it could reject changes from another document or shelf and overwrite accepted decisions. Its count included duplicate and unknown ids.
- Default change: `accept` refuses overlapping proof changes before it changes any page. Accept one change from each overlapping pair. Before, it applied overlapping changes to the same text.

## 0.1.33
- Follows litesearch 0.1.50, which stores one text once and replaces a source whose text changed. `add(refresh=False)` now returns `skipped='already filed'` for a source already in the vault. litesearch no longer skips changed text on its own. A source whose text another source filed first counts as filed.
- `doc(ref)` finds a document by any source it is filed under, including a copy recorded only in litesearch's `sources` table.
- A Local only document's `sources` list is withheld with its `source`. Before, `toc` showed it.
- Raises the floor to litesearch 0.1.50.

## 0.1.32
cache check checks both halves of the ocr page.

## 0.1.31
- `grab` takes `stop` and `progress` for a local file, a PDF and a GitHub file URL. `add_file`, `pdf` and `gh_file` take both, as `url`, `arxiv` and `youtube` do: `stop()` is asked before the read or fetch, and `progress(1, 1, [target])` is called once the target is filed. When `stop()` returns True, nothing is filed and the result has `cancelled` set and `unread` holding the target. Before, `grab` passed `stop` to these methods, which did not accept it, and raised `TypeError`.
- `add_files`, `add_dir` and `add_tree` pass `stop` to litesearch's `add_dir`, which asks it before each file in a batch. A stop inside a batch keeps the files before it, and `unread` lists that batch's remaining files and every later file. `progress` is called for that batch with only the files filed, or not called when none were. Before, a batch of `batch` files (50) always finished before `stop` was asked again.
- Raises the floor to litesearch 0.1.46.

## 0.1.30
- `add_tree`, `add_dir` and `add_files` take `stop` and `progress`. `stop()` is asked before each batch of `batch` files (50) and before kosha; `progress(done, total, batch)` is called after each batch, and an error in it is ignored. When `stop()` returns True, the batches already filed stay in the vault and the result has `cancelled` set and `unread` listing the files not reached. Nothing is raised.
- `github` asks `stop` before the clone and passes both to `add_tree`. `url`, `arxiv` and `youtube` ask it before the fetch; `crawl` and `web` ask it between the pages they file. Given `stop`, their results carry `cancelled` and `unread` too. Without `stop` every result is as before.
- `run_steps(items, f, size, stop, progress)` is the loop behind these, for a caller with its own list.
- The CLI and the MCP server do not offer `stop` or `progress`.

## 0.1.29
- `CachedChat` built directly registers Rishi's runtimes, as `new_chat` does, so `runtime` names the backend. Before, `CachedChat(path=...).runtime` raised "Can't tell which backend" for the default model unless something had already imported Rishi.

## 0.1.28
- `quality` imports `robust_z` and `TOKEN_RE` by their public names in litesearch 0.1.44. The evals read rahasya 0.0.5's public tables (`luhn_digits`, `NRIC_LETTERS`, `COMPILED`, `nhs_ok` and the rest), and `evals/pii.py` runs again.
- Raises the floors to litesearch 0.1.44 and rahasya 0.0.5.
- The tests that build the entity graph replay recorded replies through `CachedChat`, so CI loads no model.

## 0.1.27
- The MCP server gates every result before the client sees it. Each string under a Local only document is withheld, title, heading and source included. Every other string goes through `redact`, which masks the identifiers of a Personal document. A document a person cleared comes back as stored. Before, `search`, `read`, `context`, `document`, `sources`, `ask` and the rest returned stored text. A client model received the email address of a Personal document and the title of a Local only document.
- A tool that takes `pii` defaults to `redact` over MCP. A client may ask for `refuse`. `pii='off'` raises `PermissionError`, as lowering a level does. The CLI and Python defaults are unchanged.
- `ask` and `ask_doc` over MCP return no `prompt`. When a local model read a Local only section whole, the answer, thinking and fields are withheld.
- Raises the floors to rahasya 0.0.4, varga 0.0.7, fossick 0.1.18, koshas 0.1.11, pdflite 0.0.4, litesearch 0.1.43, rishi 0.1.44 and uraiyadal 0.0.13.

## 0.1.26
- `ask` masks each section's heading line, title and source under `redact`, as it masks the text. Before, the heading went as stored. A note titled with an email address sent the address to a hosted model.
- A Local only section reaches a hosted model as a bare `[n] [withheld: local only]` line, through `ref=` or retrieval. Before, its heading and source went with the placeholder.
- `explain` goes through the same gate as `ask`: the section title and the related headings are masked or withheld, a Local only related section is dropped, and a hosted send is written to the send log.
- `categorize` and `extract` send the title and source under the same `send_check` decision as the text: masked under `redact`, nothing when withheld. `extract` decides through `send_check` and logs every hosted send. A file read off disk is judged on its name too. Under `redact` a local model now reads the document whole, as `send_rule` says.
- `gated` withholds a Local only row's title, breadcrumb and source with its text. `pii_ctx` and the row detector read titles, breadcrumbs and sources as well as text.
- `level` counts an identifier in a document's title, on every page.
- `read_page` judges the title with the page text. The title goes into the reading prompt.
- `build_graph` and `connect` refuse a hosted chat when the shelf holds a document above Open; nothing is sent and the result has `refused`, `kind` and `why`.
- `new_chat`, `use_chat`, `is_stock_chat` and `local_ok` read `CHAT` and `LOCAL_OK` on the module at call time. A copy run from a notebook obeys the same switch. Notebooks pass in one process as well as in parallel.

## 0.1.25
- `read_doc` and `Vault.read_doc` take `cache=`: a folder, or `cache(page, half)` returning a path. Each page's reading is kept there as JSON, `{page, items, cost, model}`, with `page` the file's stem. A cached page is not sent again; its row has `cached` set and `cost` None. An empty reading is kept too.
- `redo=` reads pages again though they are cached. The old reading moves to the folder's `_prev` sibling once the new one is in, numbered `.1`, `.2` when one is there already.
- `spread=True` reads a landscape page, a two-page spread, as its two halves in turn (`halves`), kept as `p0001a.json` and `p0001b.json`. `strips=k` sends each image as `k` overlapping strips (`page_strips`), and the model is told to read the page once. Both are cut from the page at full size; each piece is then held to the size limit.
- `clean=` is a function applied to the text of every block before the block is kept.
- `tries=n` tries a failing page `n` times, waiting `RETRY_WAIT` seconds more each time. A page that still fails keeps its text layer, carries its `error` and is listed in `failed`. Without `tries` the error is raised, as before. `Vault.read_doc` results carry `failed`.
- `read_page` takes `strips` and `fresh`. A reply that is not JSON raises and is dropped from the recorder, so asking again reaches the model. `fresh=True` drops the recorded reply before asking; `read_doc` asks fresh on a retry and on a `redo` page.
- `fit(img)` holds a page image to the size `render` allows: within `max_bytes` as it is, else a JPEG within `max_px`. An image file given to `read_doc` is held to it.
- `reading_prompt` fills `{title}` in a whole prompt as well as `{of}`, `{script}` and `{hint}`. A prompt that is no template, its JSON braces not doubled, is used as it is.
- `Vault.accept` makes each change in the page's blocks too (`block_changes`), so what is assembled from the blocks after a proofread has it. A table's cells and a heading's `##` stay as read. Before, an accepted page lost its blocks.
- `Vault.read_doc` files a page again only when its text, route or blocks changed. Before, every page with blocks was filed as a new version on every read.
- `Vault.proofread` takes a reader named twice as one reader, so one model cannot agree with itself.
- `CachedChat` keeps its recordings in `$VISHALAKSHI_CHAT_CACHE` when `path` is not given.

## 0.1.24
- `Vault.edit_change(doc_id, id, after, by='person')` replaces an open change's proposed text. It returns `{ok, change}`, or `kind: not_found` or `stale` for a change that is not `proposed` or `doubt`.
- `Vault.revert_page(doc_id, page, version, by='person')` files an old version of a page as its newest version, route `revert`, and re-indexes the document. It returns `{ok, doc_id, page, version}`, or `kind: not_found`.
- `Vault.undo_decision(doc_id, ids, by='person')` takes decisions back. A rejected change returns to `proposed` or `doubt`, whichever it was. An accepted change's page is reverted to its text before the accept, and every change that accept applied is `proposed` again against the new version. It returns `{ok, doc_id, undone, pages}`, or `kind: stale` when the change is not decided or its page has changed since the accept.
- `Vault.reset_pii(ref, ids, by='person')` sets findings back to `found`, every occurrence of the value with them.
- Only a person may call these four: `by='agent'` raises `PermissionError`. They are CLI commands. They are not MCP tools, and neither are the other proof and finding verdicts.
- `reject` records the state a change had in a new `was` column of `proof_changes`. The column is added on first use.

## 0.1.23
- `read_doc`, `Vault.read_doc`, `Vault.reparse` and `Vault.proofread` take `progress=`. It is called as `progress(done, total, page, route, cost)` once with `done=0` and after each page sent to a model. Errors in it are swallowed. Returning False stops the rest: unread pages keep their text layer or OCR, and a cancelled `reparse` leaves them as they were.
- Results carry `cancelled` and `unread`. `read_doc` sets them as attributes on the returned `L`.
- `doc_cost(rows)` sums the cost of model-read pages. `Vault.read_doc` and `reparse` results carry `cost` and `model_pages`. `proofread` carries `cost`, the readers' summed usage.
- Every preset asks for an optional `box`, `[x0, y0, x1, y1]` in page fractions, per item. `read_page` keeps a sane box clamped to 0-1 and drops any other (`sane_box`). Boxes are stored with the blocks.
- `crop(img, box, pad=.02)` returns that region as PNG. Without a sane box or without Pillow it returns the whole image.
- Proof changes carry the `box` of the block they fall in (`change_box`) when the page's blocks read as its text. `proof_changes` gains a `box` column on first use.

## 0.1.22
- Privacy levels: Open, Personal, Local only. `level(ref, page=)`, `set_level(ref, level, reason, by=)`, `floor()`, `set_floor(level, by=)`. `pii_override` takes `local`. A document's level is its mark, else its type and findings, never below the shelf's floor.
- Only a person lowers a level, clears a mark, rejects a finding or lowers a floor: `by='agent'` raises `PermissionError`. MCP tools always pass `by='agent'`. `mark_not_pii` over MCP now raises.
- `pii_findings`: every ingest files each page's identifiers as fingerprints, kinds and offsets, never values. `scan_pii`, `findings` (masked `preview`), `accept_pii`, `reject_pii` (`kind: stale` for an id from before a re-read). A verdict follows the fingerprint through a re-read.
- `send_check(refs|pages|text, model, policy, allow=, image=)` returns `{ok, send, masked, withheld, kinds, kind, why, rows}`. `send_rule`, `model_local`, `send_line`. Hosted sends are logged in `send_log`, read with `sends`.
- `TYPE_POLICY` and `type_policy(doctype, text=)`: invoice, receipt, quote and catalogue read with `tables`; id_card, passport, bank_statement, payslip, tax_return and clinical_record start Local only.
- Default change: a Local only document goes to no hosted model, whatever the policy, in `ask`, `explain`, `categorize`, `extract` and page reads. `gated(pii='redact')` withholds it as well.
- Default change: `categorize(pii='redact')`. The model leg was unchecked. A hosted model now receives a Personal document masked.
- Default change: `extract` categorises with the model its privacy routing picks, and scans with names on. It used to send an undecided private document to the caller's model. A local Ollama counts as local, as it does in `ask`.
- Default change: `read_page`, `read_doc`, `reparse` and `proofread` take `pii='redact'`. A Personal page image goes to a hosted model only with `allow=True`, and a Local only page never does. `local_model=` / `local_chat=` read those pages instead. Results carry `blocked`.
- `read_doc` raises a document to Local only when its text layer reads as a sensitive type.
- `extract(save=True)` stores `extracted_src` (`{field: {page, block, quote}}`); `cite=True` asks for quotes.
- `ask` and `explain` results carry `level`; `ask` carries `send`.
- Needs rahasya>=0.0.3 and varga>=0.0.6.

## 0.1.21
- `read_page` registers rishi's backends first: in 0.1.19-0.1.20 a model name such as `claude/sonnet` did not resolve. `backends()`.

## 0.1.20
- A model-read page keeps its `blocks` (kind, n, text) in `read_doc`, `read_pages` and `pages`.

## 0.1.19
- `read_doc(path, parse=, model=, preset=, script=, hint=, pages=)`: a PDF or page image page by page; a sound text layer kept, scanned pages OCRed, pages still scanned or flagged read by a vision model. `Vault.read_doc` reads a file or folder into the vault, keeping each page's text, route and flags as versions (`pages`). `reparse` reads pages again.
- `flags`, `disagree`, `render`, `PRESETS` (generic, sanskrit, tamil, tables), `reading_prompt`.
- `proofread(doc, readers)`: other readers' word changes, `proposed` where two agree; `changes`, `accept`, `reject`, `proof_md`.
- CLI: `read_doc`, `pages`, `reparse`, `proofread`, `changes`, `accept`, `reject`, `proof_md`.
- Needs litesearch>=0.1.41 and pdflite>=0.0.3.

## 0.1.18
- `search`, `sections` and `context` take `where=`, ANDed with the kind and noisy filter. `context(where="doc_id='…'")` scopes to one document and no longer raises `TypeError`.
- `rerank=True` without flashrank raises naming the new `rerank` extra: `pip install 'vishalakshi[rerank]'`.
- Needs litesearch>=0.1.36 (plain-English spellings fold with IAST and Devanagari) and vruksha>=0.1.1 (one-word names merge across romanisations).

## 0.1.17


## 0.1.16
- `federate` leads its note with `search incomplete, <leg> (<error>) failed;` when a leg raised.

## 0.1.15
- `connect()` builds the typed entity graph with vruksha and writes the topic nodes; `graph_search` walks it.
- The offline encoder has a name. litesearch stamps the store it writes with that name.
- Shelf encoders live in litesearch's `store_meta`; `vault_stores` rows are read once and migrated; a wrong-width reopen raises `StoreMismatch`.
- `extract` checks pulled values with varga's `check_fields`.
- `categorize` proposes an undecided doctype instead of writing it: `proposed_types`, `accept_type`, `reject_type`.
- A job that retrying cannot fix is dead-lettered.
- `CachedChat` is urai's recorder with this package's defaults; `VISHALAKSHI_RECORD_CHAT` still switches it; recorded replies re-recorded under the new keys.
- Sanskrit detection imports ganapati, so Sanskrit files reach the sanskrit shelf.
- PII gate `is_local` counts ollama only when `$OLLAMA_HOST` is local.
- Needs litesearch 0.1.35, varga 0.0.5, vruksha 0.1.0, uraiyadal 0.0.7.

## 0.1.14
using urai, rahasya, varga, pobblebonk and litesearch index

## 0.1.13
litert model string bug fix

## 0.1.12
changes to make pollers in vishalakshi. 

## 0.1.11

Retrieval takes a privacy policy. `ask` used to be the only method with one. `search`, `sections`,
`context`, `read`, `document`, `toc`, `doc_context` and `federate` handed raw section text to
whatever read it next. Each takes `pii=` and `pii_ner=` now.

- `gated` applies a policy to rows, an assembled context, or one section. The default is `off`. A
  caller that does not ask sees no change.
- `redact` masks what was found. `refuse` replaces the body and keeps the row, with `pii` naming the
  kinds. A caller that asked what matched still learns that something did.
- `local` is not a retrieval mode. It answers a question on a model here, and retrieval has neither.
- `mark_pii` and `mark_not_pii` reach every primitive, not `ask` alone.
- Labels (`title`, `breadcrumb`) are masked rather than withheld. A note is titled by its own first
  line, and a row with no label left cannot be opened or asked about.
- `_pii_marks` and `_section_private` moved from `ask` to `pii`, and `ask` re-exports them.

## 0.1.10
release

## 0.1.9
pii updates

## Unreleased

**`vishalakshi.pii`**: digits are read in context. `EN 60601-1` was an address and a ten-digit
Confluence page id in a URL was an NHS number. Both are fixed, by five guards.

- `US_STATES` and a capitalised city gate the ZIP alternative.
- `DESIGNATOR` drops a match introduced by a reference word.
- `URLISH` drops digit runs inside a link.
- `nhs` needs its groups or its name, and `card` needs an issuer digit.

Precision 0.762 to 0.996 at unchanged recall 1.000 on the tuned corpus, and 1.000 at recall 1.000
on a held-out corpus run once. `evals/pii.py` reports both and labels which is in sample.

Nineteen regional identifiers, each with its own checksum, all at 20/20 recall.

| region | kinds |
|---|---|
| India | `aadhaar` (Verhoeff), `pan`, `gstin` (mod-36) |
| Australia | `tfn` (mod-11), `abn` (mod-89), `medicare` |
| Singapore, Thailand | `nric`, `thai_id` |
| France, Spain, Italy | `nir` (mod-97), `dni`, `nie` (mod-23), `cf` |
| Netherlands, Poland, Germany | `bsn`, `pesel`, `steuerid` (ISO 7064) |
| Sweden, Norway, UK | `personnummer`, `fnr`, `nino` |
| devices | `imei` |

`evals/ids.py` generates them and checks every generator against the library's own validator.

Holding a corpus back found three defects the tuned corpus could not. `MS 73681` and `AL 31000` were
addresses. An ORCID was a phone number. A Swedish organisationsnummer was a personnummer.

Two learned detectors were measured and neither is shipped. The wheel has no weights and no
`onnxruntime` import. An ONNX DeBERTa-v3 classifier scores 0.825 precision and 0.846 recall against
the patterns' 0.996 and 1.000, at 200 times the cost, and finds 0.00 of the planted IBANs. Liquid's
350M tflite encoder through `ai_edge_litert` finds no names at all and labels Aadhaar digits
`special.religion` in both its builds. The onnx int8 build silently finds 0.446 of what is there.
Both live in `evals/backends.py`, measured by `evals/pii_model.py`.

## 0.1.8
image support and job queues

## 0.1.7
ner should not be done for code and fixing addresses

## 0.1.6
release

## 0.1.5

**`vishalakshi.quality`**: feedback, a noise score, and a ranker fitted from both. `learn()`,
`rate`, `log_ask`, `doc_prior`, `noise_features`, `noise_scores`, `suggest_noisy`, `fit_noise`,
`Ranker`, `fit_ranker`, `use_ranker`, `retune`.

The labels are taken rather than asked for: `ask` already computes which sections an answer cited,
which is a relevance judgement by the model that read all of them, produced on every question. A
section retrieved and ignored is the weak negative that makes the positives mean something. An
answer that cites nothing is not logged at all: small models drop the convention on exactly the
hardest questions, and six negatives is the wrong thing to learn from that.

The noise score is unsupervised and reaches 0.988 AUC over generated corpora, 0.996 fitted from six
marks. What it measures is *"this gets retrieved for everything"*: hubness in the k-NN graph,
near-duplication across documents, not breadth. Document-level cluster spread, the intuitive
version, scores 0.453: below chance, because it flags surveys harder than boilerplate.

None of the rerankers beat RRF reproducibly on novel questions, and `use_ranker` is a separate call
from `fit_ranker` for that reason. `retune` fuses by reciprocal rank rather than substituting the
order: mediocre and fused costs −0.001 nDCG, mediocre and substituted costs −0.127. Full numbers
and method in `evals/RESULTS.md`.

**`doc_marks`**: `mark_noisy` and `mark_not_pii` now write to their own table instead of the
document's `meta`. `add_doc(force=True)` deletes the document row and writes a fresh one, so a mark
kept in `meta` was erased by the next re-ingest, and `run_watch` re-ingests on a schedule. A page
marked noisy on Monday was back in the results on Tuesday, silently. Existing marks migrate on
first open. The retrieval filter is an anti-join against the marked set rather than a
`json_extract` over every document, which is the same answer without parsing the metadata of the
whole vault on both legs of every query.

**`Vault.doc(ref)`** returns None for an empty ref instead of falling through to `title LIKE '%%'`
and matching the newest document in the vault. `ask`'s PII exemption check reached it with the
`doc_id=None` that federated code sections carry, and got back an unrelated document's exemption.

**`Vault.context`** no longer asks for `sections*3` on top of the `sections*3` litesearch already
applies internally, or rebuilds the filter in Python after pushing it into retrieval: 9x the chunk
fanout and 3x the `read()` calls to return the same six sections.

## 0.1.4
enable marking items as not pii and testing for pdf acquire

## 0.1.3

**`vishalakshi.pii`**: whether a document is somebody's business, decided by arithmetic. Patterns
with checksums where a checksum exists (Luhn for cards, mod-97 for IBANs, mod-11 for NHS numbers)
and tightly written where none does, de-overlapped longest-first so one card is not counted three
times, and sampled at both ends of a long document because a statement's account number is in its
header. `pii_spans`, `pii_report`, `redact`, `Vault.pii(ref)` and `pii_ctx(ctx)`.

The detector is not a model. A classifier that must read a document to say whether the
document may be read has already lost. And `has_pii` is narrower than "found something": an IP
address or an API key is reported but does not on its own make a document private, or every
question about a server log ends up on the slow path.

**`ask(pii=...)`**: when the sections retrieval chose hold personal information, `'local'` (the
default) answers on `pii_model` under `PII_SP`, a briefing that forbids reproducing any personal
detail and asks the questioner what instruction it needs instead. Before a character is sent, the
chat that was built is checked for a local runtime; a caller that lends a hosted one is refused,
because the check is on the object rather than on the caller having been honest about the name.
The reply is re-scanned on the way out and masked if the model slipped. `'redact'` masks the
sections and answers anywhere, `'refuse'` answers nothing, `'off'` does not look. `instruction=`
carries the questioner's reply back for the second turn.

`ask`, `ask_doc` and `explain` take `mk_chat=`: build this call's chat with that instead of
`new_chat`, same signature. `use_chat` already swapped the factory, but process-wide and only
for the duration of a block: right for a notebook replaying recorded replies, wrong for a
long-lived host, and wrong again for one that runs turns on threads.

A factory rather than a chat, deliberately. A chat is built per question and built again from
scratch when the first prompt overflows the window, and a passed-in conversation would carry
the last question's history into this one and leave the overflow retry with nothing to rebuild.
Both still happen; the caller just decides what they happen on. Since the factory takes what
`new_chat` takes, `rishi.Chat`'s `engine=` is the whole point of it: an agent that already has
a model loaded lends the vault a fresh conversation on those weights, instead of the vault
loading a second copy of an engine to answer on a different model from the one being talked to.

## 0.1.2
A shelf reuses the vault's encoder, and offline means offline


## 0.1.1
release

## 0.0.1
vault vishalakshi- she sees everything
