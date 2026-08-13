# What the evals actually said

Everything below is from `evals/`, on generated corpora (`evals/corpus.py`) with the
`retrieval` static encoder. Reproduce with `python -m evals.noise`, `python -m evals.run` and `python -m evals.jobs`.
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

`python -m evals.pii`: 400 documents, half with planted identity and half with lookalikes
(order numbers, ISBNs, part numbers, build strings, numbered headings). Checksums are the claim:

| detector | precision | recall | F1 | false positives |
|---|---|---|---|---|
| regex only | 0.738 | 1.000 | 0.849 | 71/200 |
| with checksums | 0.962 | 1.000 | 0.980 | 8/200 |

Recall is 1.000 on every planted kind in the harness (email, card, iban, ssn, nhs, phone, dob,
account, address). The residual false positives are Luhn collisions on long digit runs.

### The street line, and why it needs a street name

`address` is what makes "John Smith, 12 Elm Street" private: no pattern finds the name, and one
identifying hit is all a section needs. Written as a number followed by an optional street name and
a suffix, it reads `Chapter 4 Court`, `Table 3 Road` and `Figure 2 Way` as addresses and takes
precision to **0.746** (68/200 false positives). Requiring at least one capitalised word between the
number and the suffix is the whole difference: **0.962** at the same recall. A US ZIP needs its
state for the same reason, since five digits alone are a quantity.

### Names

Names are the one kind no pattern finds, so they are the one kind behind `ner=True`. The extractor
is the honorific-anchored regex in `extract._noun_ents`, not a model: no weights, and 21 ms over
180,000 characters. `Dr Charles Babbage` is found and a bare `Ada Lovelace` is not, which is a
recall limit and the reason `mark_pii` stays. The number that decides whether to switch it on is
what it invents in ordinary prose: **0 of the 200 lookalike documents** gained a spurious person.

`scanned_ner` is in every report, because a zero `person` count means nothing without knowing
whether anything looked. `n` and `density` stay arithmetic-only so `DENSE` keeps its meaning.

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

The honest summary is that the infrastructure is worth having and the models are not yet. Three
generated corpora is not a real vault, and every number here should be re-measured against yours:
`evals/gold.py` builds a gold set from a real one for exactly that.
