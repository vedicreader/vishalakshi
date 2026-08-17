# What the evals actually said

Everything below is from `evals/`, on generated corpora (`evals/corpus.py`) with the
`retrieval` static encoder. Reproduce with `python -m evals.noise`, `python -m evals.run`, `python -m evals.jobs`,
`python -m evals.pii` and `python -m evals.pii_model`.
Every comparison is paired over queries with a 5,000-sample bootstrap; a CI spanning zero is
reported as no difference rather than as a small win.

Read the headline first: **the noise score works, and no learned reranker beat plain RRF
reproducibly.** The parts that are switched on by default are exactly the parts that earned it.

## 1. The noise score

Per-feature AUC against ground truth, 72 documents of which 8 are boilerplate by construction:

| feature | AUC | boiler z | survey z | what it is |
|---|---|---|---|---|
| `hub` | 0.984 | +1.51 | −1.66 | how often a chunk is in others' k-NN lists |
| `spread_chunk` | 0.982 | +1.50 | +0.67 | entropy of one chunk's similarity over topic centroids |
| `off_centre` | 0.881 | +1.19 | −1.56 | cosine distance from the corpus centroid |
| `dup_out` | 0.800 | +0.94 | −1.12 | chunks near-duplicated in *another* document |
| `low_idf` | 0.602 | +0.32 | −0.07 | mean term specificity, negated |
| `promiscuity` | 0.500 | n/a | n/a | distinct past queries retrieving it (needs a feedback log) |
| `redundancy` | 0.498 | −0.01 | −0.24 | chunks near-duplicated inside the same document |
| `spread_doc` | 0.453 | −0.15 | **+0.83** | entropy of the document's chunks over clusters |
| `short` | 0.422 | −0.24 | +0.55 | fraction of very short chunks |

Blended: **0.988 mean AUC** over three corpora (0.967–1.000). Fitted from marks instead of the
fixed weights, held out: **0.996** (0.990–1.000), better on all four corpora tried, from six
marked documents and eighteen confirmed keepers.

### "Spread across clusters means generic", measured

`spread_doc` is that hypothesis, and it scores **0.453 AUC. Below chance.** Worse, look at which
documents it indicts: the corpus plants `Survey` documents that range over every topic and are
*not* noise, and `spread_doc` scores them +0.83 against boilerplate's −0.15. It ranks the surveys
as noisier than the footers.

Measuring the same idea one level down, the entropy of a *single chunk* over topic centroids
rather than of a document over cluster assignments, gets **0.982**, the second-best feature in the
table. That is the difference between broad and generic: a survey is broad at the document level
and specific in each paragraph, and boilerplate is generic in every chunk it has. But even that
correction only partly separates surveys (gap +0.83); what cleanly does is `hub` (+3.17) and
`dup_out` (+2.06). Genericness is better measured as *"this gets retrieved for everything"* than as
anything about topics.

### An incidental finding

`usearch.index.kmeans` does not honour its `seed`. Called twice on identical input it returns
different assignments, and `spread_doc`, an entropy over those assignments, drifted across its
whole range between two calls on the same vault, taking `spread_chunk` from 0.807 to 0.982 once
fixed. `quality._centroids` is now a seeded k-means++ plus Lloyd in numpy, at comparable cost since
both are dominated by one `V @ C.T` per iteration.

## 2. The rerankers

Known-item queries (one document answers each, different every time), **document-disjoint** split
(no test query's gold document was seen in training), three corpora, mean Δ vs base:

| system | nDCG@10 | MRR@10 | recall@10 | significant wins / losses |
|---|---|---|---|---|
| `+noise` (unsupervised filter) | **+0.001** | **+0.005** | −0.015 | 1 / 0 |
| `+linear` fused at α=0.25 | −0.001 | −0.004 | +0.007 | 0 / 0 |
| `+gbdt` (replaces order) | −0.005 | +0.019 | −0.093 | 1 / 1 |
| `+forest` (replaces order) | −0.085 | −0.051 | n/a | 0 / 2 |
| `+prior` (Beta posterior) | −0.043 | −0.065 | n/a | 0 / **3** |
| `+linear` (replaces order) | −0.127 | −0.082 | −0.274 | 0 / 2 |

Three things to take from this.

**Gradient boosting did not win.** It beat the baseline on MRR on one corpus (+0.083, p=0.05) and
lost on another (−0.109, p=0.01). One seed would have shipped it. That is the entire reason the
harness resamples and reports across corpora.

**Substituting the ranking is the dangerous operation, not learning.** The same linear model costs
−0.127 nDCG when it sorts by its own score and −0.001 when it is fused with the incoming order by
reciprocal rank. Fusion does not make a weak model good; it makes it harmless. `retune` defaults to
`alpha=0.25` for that reason.

**The Beta prior is regime-dependent, and the two regimes disagree sharply.** On `mode='topic'`
queries, the same material relevant again and again, it was worth +0.020 nDCG and +0.116 recall.
On known-item queries it was significantly worse on MRR on all three corpora. It remembers which
documents were useful, which is precisely wrong for a question whose answer you have never been
shown.

### The leak that had to be closed first

The first run had the linear model at recall 0.47 against a baseline of 0.80, with `prior` as its
largest weight by a factor of two. The `prior` feature was computed from the same feedback log the
labels came from: the feature was a summary of the label. `training_data` now computes it
out-of-fold, excluding each question's own rows. That alone moved forest and gbdt from
significantly worse to indistinguishable, and it is invisible on a query-disjoint split: only the
document-disjoint split showed it.

## 3. PII detection

`python -m evals.pii`: 480 documents, half with planted identity and half with lookalikes. The
lookalikes are grouped so a residual false positive has a name, and three of the seven groups carry
*valid* checksums, because that is the case a random corpus meets one time in eleven and a spec
document meets on every page.

| detector | precision | recall | F1 | false positives |
|---|---|---|---|---|
| regex only | 0.956 | 1.000 | 0.978 | 11/240 |
| with checksums | **0.996** | **1.000** | **0.998** | **1/240** |

Recall is 1.000 on every planted kind (email, card, iban, ssn, nhs, phone, dob, account, address).
The one residual false positive is a Luhn collision on a random 16-digit run.

### Reading the digits is not enough; you have to read what is around them

The corpus grew two groups after two reported failures, and both were real:

- `EN 60601-1`, `EN 60601-1-2`, `EN 60601` were reported as **addresses**. `[A-Z]{2} \d{5}` is a US
  state and ZIP, and it is also every standards designation ever written.
- A Confluence page id, `.../pages/2377744435`, was reported as an **NHS number**. It is: ten digits
  pass the NHS mod-11 check about one time in eleven, and that one was one of them.

The same detector on the same 480 documents, before and after:

| | precision | recall | false positives |
|---|---|---|---|
| before | 0.762 | 1.000 | 75/240 |
| after | **0.996** | 1.000 | **1/240** |

By lookalike group, false positives before → after: `cued` 36/36 → 0/36, `link` 24/24 → 0/24,
`standard` 12/36 → 0/36, `bare` 3/30 → 1/30. Nothing else moved and recall did not change.

Five guards did that. Each removed on its own, everything else left in place:

| guard removed | precision | false positives | which group comes back |
|---|---|---|---|
| — (as shipped) | 0.996 | 1/240 | |
| `US_STATES` before a ZIP | 0.949 | 13/240 | `standard` 12/36 |
| `DESIGNATOR` to the left | 0.949 | 13/240 | `cued` 12/36 |
| `URLISH` span suppression | 0.972 | 7/240 | `link` 6/24 |
| NHS needs groups or its name | 0.992 | 2/240 | `bare` |
| card needs an issuer digit | 0.992 | 2/240 | `bare` |
| all five | 0.762 | 75/240 | all four |

The guards overlap: `DESIGNATOR` alone costs 12/36 on `cued` rather than 36/36 because the NHS and
card tightenings independently kill the other 24. The street-name requirement inside `address` is
now fully covered by `DESIGNATOR` on this corpus (0.996 either way); with `DESIGNATOR` switched off
it is still worth 0.949 against 0.833, so it stays.

`DESIGNATOR` keeps its acronyms case-sensitive, because lowercase `en` is an ordinary English word.
`No` was in the list and is not any more: it suppressed `No. 5 Elm Street`, `No 5 Elm Street` and
`Flat 2, No. 12 Victoria Road` and changed precision by nothing (0.996 either way). A guard that
costs recall and buys no precision is not a guard.

### Names

Names are the one kind no pattern finds, so they are the one kind behind `ner=True`. The extractor
is the honorific-anchored regex in `extract._noun_ents`, not a model: no weights, and 21 ms over
180,000 characters. `Dr Charles Babbage` is found and a bare `Ada Lovelace` is not, which is a
recall limit and the reason `mark_pii` stays. The number that decides whether to switch it on is
what it invents in ordinary prose: **0 of the 240 lookalike documents** gained a spurious person.

`scanned_ner` is in every report, because a zero `person` count means nothing without knowing
whether anything looked. `n` and `density` stay arithmetic-only so `DENSE` keeps its meaning.

## 3a. The learned detector

`pip install 'vishalakshi[model]' && python -m evals.pii_model`. The model is
`onnx-community/piiranha-v1-detect-personal-information-ONNX`, a DeBERTa-v3 token classifier,
on the same 480 documents. Both builds in that repo are measured, because the quantised one is the
one you would reach for.

| system | precision | recall | F1 | false positives | ms/doc |
|---|---|---|---|---|---|
| patterns | **0.996** | **1.000** | **0.998** | 1/240 | **0.2** |
| model fp32 | 0.825 | 0.846 | 0.835 | 43/240 | 71 |
| patterns ∪ fp32, every kind | 0.845 | 1.000 | 0.916 | 44/240 | 37 |
| patterns ∪ fp32, `MODEL_ADDS` | **0.996** | **1.000** | **0.998** | 1/240 | 73 |
| model int8 | 0.955 | 0.446 | 0.608 | 5/240 | 38 |
| patterns ∪ int8, every kind | 0.976 | 1.000 | 0.988 | 6/240 | 19 |

**The model loses the gate outright.** It is worse on precision and worse on recall than a page of
regexes, 370 times slower, and it finds **0.00** of the planted IBANs. Unioning everything it emits
costs precision 0.996 → 0.845 and buys no recall at all, because the patterns were already at
1.000. `standard` is the one lookalike group it gets perfectly right, which is exactly the group
that prompted this work and exactly the group the `US_STATES` list also fixes, for free.

**Do not use the int8 build.** It is in the repo, it is 317 MB against 1.15 GB, it loads and it runs.
It also finds **0 of 27** planted emails, 0 of 27 IBANs, 3 of 27 NHS numbers and 4 of 27 SSNs: recall
0.446 overall. DeBERTa-v3's disentangled attention does not survive dynamic quantisation, and the
failure is silent. Nothing in the model card says so.

**The one thing it is for.** On eight sentences no pattern can reach by construction (a name with no
honorific, a street with no number):

| | found |
|---|---|
| patterns | 0/8 |
| patterns, `ner=True` | 2/8 |
| model fp32, `person` only | **5/8** |
| model fp32, every kind | 7/8 |

and it invented identity in **0 of 8** clean sentences. So `model=True` unions `MODEL_ADDS`
(`{'person'}`) and nothing else: it holds precision at 0.996 and recall at 1.000 on the gate corpus
while raising the blind-spot recall from 2/8 to 5/8. Pass `kinds` explicitly to get the rest, and
pay the 0.996 → 0.845 for it knowingly.

Off by default. 1.1 GB of weights, an `onnxruntime` dependency and 73 ms per document to find a name
the arithmetic cannot, on a gate that is already at 0.996, is a trade to make deliberately and per
vault.

## 4. The job queue

`python -m evals.jobs`, three runs, identical on every correctness number; only throughput moves.
One SQLite file, separate OS processes, `job_runs` as the audit trail and a `side` table written by
the handler before the ack so redelivery is visible as a duplicate side effect rather than inferred.

| measurement | result |
|---|---|
| 8 workers, 400 jobs, no failures | 400 done, **0 lost, 0 double-claimed, 0 side effects applied twice** |
| 4 workers SIGKILLed mid-handler, 200 jobs | 200 done, **0 lost**, 4 jobs stranded by the kills, all 4 recovered |
| price of at-least-once, same run | 204 side effects for 200 jobs: **4 applied twice, one per kill** |
| 6 of 24 handlers outliving their lease | **0 jobs acked by two workers**, 18 acks refused, 6 dead-lettered |
| throughput | 9,900 enqueue/s, 53,000–66,000 claim/s |
| empty poll | **0.030 ms** |

Four of these decided a design question.

**The claim is sound; the busy timeout was not.** `UPDATE ... RETURNING` through a partial index
never handed one job to two workers, in any run. The first run still lost 2 of 400, to
`apsw.BusyError` on the *history* write: apsw's stock busy timeout is 100 ms and 8 processes on one
file exceed it, so the write failed instead of waiting and took the worker with it. `Queue` now
sets `BUSY_TIMEOUT_MS` (30 s) on its connection, which is what litesearch already does on its own
write paths. Nothing was wrong with the claim; the queue was simply not waiting its turn.

**One instance of that is not the queue's to fix, and the harness was hiding it.** apsw's
bestpractice runs `pragma optimize` while *opening* a connection, before any queue code exists to
raise the timeout, so 1 to 3 of 8 workers died in `database()` in 4 of 5 runs. The measurement
reported `workers=8` regardless, because it printed the number of processes it asked for rather than
the number that ran, and fewer workers is less contention: the harness was quietly making the
result better. `workers` is now the count that did work, `_open` retries the connect, and every
measurement asserts on worker exit codes.

**A lease is not enough on its own; `ack` has to be fenced.** A handler slower than its lease is
reclaimed underneath it and handed to a second worker, and the first worker then finishes and acks a
job it no longer holds. 6 slow handlers of 24 produced **2 jobs acked by two workers each**, and a
late `fail` from the real holder took a `done` job back to `ready` for a third run. `ack` and `fail`
now check state and worker inside the same transaction as the update. The same 6 handlers now give 0
double acks, 18 refused acks recorded as `lost`, and 6 dead letters, which is the honest outcome: a
lease shorter than the work cannot be completed, and it should fail loudly rather than book two
successes.

**0.030 ms per empty poll is why there is no watcher here.** honker earns its `PRAGMA data_version`
thread by making cross-process wake sub-millisecond, which matters when a job is a function call.
Here a job is a page fetch on a schedule measured in hours, so a one-second poll costs 0.003% of a
core and the watcher buys nothing. That is the whole argument for a table over the extension, and
it is a number rather than a preference.

The 4-in-200 redelivery rate is not a defect to fix. It is what at-least-once means, and it is
safe here only because ingest is idempotent: litesearch skips a source it already holds, so a
redelivered batch re-does the work it missed and nothing else. A handler that is not idempotent
has to carry its own key.

## 5. What this means for switching things on

| piece | default | why |
|---|---|---|
| `mark_noisy` / `mark_not_pii` / `mark_pii` | active | a person's decision, not a model's |
| `suggest_noisy` / `accept_noisy` | suggests only | 0.988 AUC is good; it is not good enough to delete things unasked |
| `fit_noise` / `use_noise` | off until saved and switched | fitted blend 0.996 AUC; same save/use seam as the ranker |
| queue retries / dead letter | active | 0 lost of 200 across 4 kills; the 4 redeliveries are the price |
| queue lease fence on `ack` | active | without it, 2 of 6 slow handlers had two workers ack one job |
| feedback logging (`learn()`) | **off** | nothing is recorded until you say so |
| `fit_ranker` | manual | fitting is free and cheap to inspect |
| `use_ranker` | **off** | nothing here beat RRF reproducibly; measure on your own corpus first |
| `ask` / `extract` / `explain` `pii=` | `local` | arithmetic gate; structured fields scrubbed on the way out |
| `pii(model=True)` | **off** | 0.996 precision without it; the model is worse on the gate and 370× slower |

The honest summary is that the infrastructure is worth having and the models are not yet. Three
generated corpora is not a real vault, and every number here should be re-measured against yours:
`evals/gold.py` builds a gold set from a real one for exactly that.
