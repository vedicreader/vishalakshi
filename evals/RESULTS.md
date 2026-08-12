# What the evals actually said

Everything below is from `evals/`, on generated corpora (`evals/corpus.py`) with the
`retrieval` static encoder. Reproduce with `python -m evals.noise` and `python -m evals.run`.
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
(order numbers, ISBNs, part numbers, build strings). Checksums are the claim:

| detector | precision | recall | F1 | false positives |
|---|---|---|---|---|
| regex only | 0.664 | 1.000 | 0.798 | 101/200 |
| with checksums | 0.948 | 1.000 | 0.973 | 11/200 |

Recall is 1.000 on every planted kind in the harness (email, card, iban, ssn, nhs, phone, dob,
account). The residual false positives are Luhn collisions on long digit runs. API keys (`secret`)
gate with the identifying set; names and addresses are out of scope and need `mark_pii`.

## 4. What this means for switching things on

| piece | default | why |
|---|---|---|
| `mark_noisy` / `mark_not_pii` / `mark_pii` | active | a person's decision, not a model's |
| `suggest_noisy` / `accept_noisy` | suggests only | 0.988 AUC is good; it is not good enough to delete things unasked |
| `fit_noise` / `use_noise` | off until saved and switched | fitted blend 0.996 AUC; same save/use seam as the ranker |
| feedback logging (`learn()`) | **off** | nothing is recorded until you say so |
| `fit_ranker` | manual | fitting is free and cheap to inspect |
| `use_ranker` | **off** | nothing here beat RRF reproducibly; measure on your own corpus first |
| `ask` / `extract` / `explain` `pii=` | `local` | arithmetic gate; structured fields scrubbed on the way out |

The honest summary is that the infrastructure is worth having and the models are not yet. Three
generated corpora is not a real vault, and every number here should be re-measured against yours:
`evals/gold.py` builds a gold set from a real one for exactly that.
