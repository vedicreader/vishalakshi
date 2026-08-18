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

`python -m evals.pii`. Read the split first, because it is the only honest way to read the rest.

| corpus | precision | recall | false positives | in sample? |
|---|---|---|---|---|
| tuned | 0.996 | 1.000 | 1/240 | yes, written while fixing |
| HELDOUT, first run | 0.927 | 1.000 | 19/240 | no, then spent on three fixes |
| HELDOUT, after those fixes | 0.996 | 1.000 | 1/240 | yes, now |
| **HELDOUT2, run once** | **1.000** | **1.000** | **0/240** | **no** |
| HELDOUT2, regional kinds | 0.990 | 1.000 | 4/384 | no |

The tuned corpus was written after the two reported failures, in the same sitting as the guards that
fix them. That makes its 0.996 the optimistic number, so it is not the headline. **1.000 on
HELDOUT2 is.**

### The two reported failures

- `EN 60601-1`, `EN 60601-1-2` and `EN 60601` were read as **addresses**. `[A-Z]{2} \d{5}` is a US
  state and ZIP, and it is also every standards designation ever written.
- A Confluence page id, `.../pages/2377744435`, was read as an **NHS number**. It is one: ten digits
  pass the NHS mod-11 check about one time in eleven, and that one does.

Before and after on the tuned corpus: precision 0.762 to 0.996, recall unchanged at 1.000. By group,
false positives before and after: `cued` 36/36 to 0/36, `link` 24/24 to 0/24, `standard` 12/36 to
0/36, `bare` 3/30 to 1/30.

### What each guard is worth

Each removed on its own, everything else left in place. Recall stays 1.000 in every row.

| guard removed | precision | false positives | group that comes back |
|---|---|---|---|
| nothing | 0.996 | 1/240 | |
| `US_STATES` before a ZIP | 0.949 | 13/240 | `standard` 12/36 |
| a city before the state | 0.956 | 11/240 | `stdbody` 10/40 |
| `DESIGNATOR` to the left | 0.949 | 13/240 | `cued` 12/36 |
| `URLISH` span suppression | 0.972 | 7/240 | `link` 6/24 |
| NHS needs groups or its name | 0.992 | 2/240 | `bare` |
| card needs an issuer digit | 0.992 | 2/240 | `bare` |
| all of them | 0.762 | 75/240 | all four |

The guards overlap. `DESIGNATOR` alone costs 12 of the 36 `cued` documents rather than all 36,
because the NHS and card tightenings independently kill the other 24. The city and `US_STATES` rows
are measured on the corpus where each one bites, `stdbody` being a held-out group.

`DESIGNATOR` keeps its acronyms case-sensitive, because lowercase `en` is an ordinary English word.
`No` was in the list and is not any more. It suppressed `No. 5 Elm Street` and `Flat 2, No. 12
Victoria Road` and changed precision by nothing. A guard that costs recall and buys no precision is
not a guard.

### What holding a corpus back actually bought

`HELDOUT` was written from conventions enumerated independently of the detector: the precision-trap
list documented in `context_cued.py` in LiquidAI/LFM2.5-Encoder-350M-PII-Detector, real numbering
standards with their own check digits, organisation numbers, postal coding from four regions, and
standards bodies absent from `DESIGNATOR`. Run cold it found three defects the tuned corpus could
not have found, since the tuned corpus was written to match the fix:

- **`stdbody`, 10 of 40.** `MS 73681`, `AL 31000`, `IN 61010`. Two-letter codes that are also US
  states. The `US_STATES` list moved the reported hole rather than closing it. A ZIP now needs a
  capitalised city in front of it, for the same reason the street line needs a street name.
- **`stdnum`, 15 hits.** ORCID `0000-0002-1825-0097` read as a UK trunk-prefixed phone number. The
  phone alternative now refuses to be one link in a longer chain of digit groups.
- **`orgnum`, 4 hits.** A Swedish organisationsnummer read as a personnummer. Same 6-4 shape, same
  Luhn, and a company is not a person. `personnummer_ok` now also requires a real birth date, which
  is the only thing that separates them.

Fixing against `HELDOUT` spent it, so `HELDOUT2` was written afterwards from families chosen to
collide with the shipped checksums: SNOMED CT is Verhoeff like Aadhaar, ICCID is Luhn like a card,
IMO and VIN are mod-11, a UK UTR is ten digits like an NHS number. It ran once. Its 4 residual false
positives are Luhn collisions on 13 to 15 digit runs, NATO stock numbers and IMSIs, and they are
recorded here as a limit rather than fixed, because fixing against `HELDOUT2` would spend that too.
A Luhn-valid run at card length is a card as far as arithmetic can tell.

### Europe, South and South East Asia, Australia

Nineteen regional identifiers, each with its own checksum, all at **20/20 recall**:

| region | identifiers | check |
|---|---|---|
| India | `aadhaar`, `pan`, `gstin` | Verhoeff, shape, mod-36 |
| Australia | `tfn`, `abn`, `medicare` | mod-11, mod-89, mod-10 |
| Singapore, Thailand | `nric`, `thai_id` | check letter, mod-11 |
| France, Spain, Italy | `nir`, `dni`, `nie`, `cf` | mod-97, mod-23, mod-26 |
| Netherlands, Poland, Germany | `bsn`, `pesel`, `steuerid` | elfproef, mod-10, ISO 7064 |
| Sweden, Norway, UK | `personnummer`, `fnr`, `nino` | Luhn plus date, double mod-11, shape |
| devices | `imei` | Luhn |

They are grouped by how much evidence the number carries alone. A mod-97 or mod-89 check, or a shape
with four fixed letter positions, is not met by accident, so `nric`, `nir`, `fnr`, `cf`, `dni`,
`nie`, `abn`, `gstin` and `pan` fire unanchored. Verhoeff, mod-11 and mod-10 each let one bare digit
run in ten through, which is the `bare` lookalike group, so `aadhaar`, `thai_id` and `personnummer`
need their conventional grouping or their name. `tfn`, `medicare`, `bsn`, `pesel`, `steuerid`,
`nino` and `imei` need the field label, and for `nino` that is the whole evidence, since a NINO
carries no check digit at all.

`evals/ids.py` generates them and checks every generator against the library's own validator, so the
corpus cannot drift from what the detector accepts: 500 generated and accepted, 500 with one digit
changed and rejected, for each of the seventeen that have a check digit. `pan` and `nino` report
0/500 on the perturbation, which is the shape gate admitting it is a shape gate. Four values are
checked against something other than my own generator: Verhoeff's published `2363`, `S1234567D` done
by hand, and the canonical `12345678Z` and `490154203237518`.

Adding nineteen patterns took the scan from 15 to 34 patterns and 0.2 to 0.3 ms per document.

### Names

Names are the one kind no pattern finds, so they are the one kind behind `ner=True`. The extractor
is the honorific-anchored regex in `extract._noun_ents`, not a model: no weights, and 21 ms over
180,000 characters. `Dr Charles Babbage` is found and a bare `Ada Lovelace` is not, which is a
recall limit and the reason `mark_pii` stays. The number that decides whether to switch it on is
what it invents in ordinary prose. It invented a person in **0 of the 240** lookalike documents.

`scanned_ner` is in every report, because a zero `person` count means nothing without knowing
whether anything looked. `n` and `density` stay arithmetic-only so `DENSE` keeps its meaning.

## 3a. The learned detectors, and why they are not in the wheel

`evals/backends.py` holds both, out of the library. `pip install onnxruntime ai-edge-litert
tokenizers huggingface-hub && python -m evals.pii_model`.

| backend | model | builds |
|---|---|---|
| `onnx` | `onnx-community/piiranha-v1-detect-personal-information-ONNX`, DeBERTa-v3 | fp32, int8 |
| `litert` | `litert-community/LFM2.5-Encoder-350M-PII-Detector`, 350M tflite | fp16, wi8fc |

On the tuned 480 documents:

| system | precision | recall | F1 | false positives | ms/doc |
|---|---|---|---|---|---|
| patterns | **0.996** | **1.000** | **0.998** | 1/240 | **0.3** |
| onnx fp32 | 0.825 | 0.846 | 0.835 | 43/240 | 71 |
| patterns and fp32, every kind | 0.845 | 1.000 | 0.916 | 44/240 | 37 |
| patterns and fp32, `MODEL_ADDS` | 0.996 | 1.000 | 0.998 | 1/240 | 73 |
| onnx int8 | 0.955 | 0.446 | 0.608 | 5/240 | 38 |
| patterns and int8, every kind | 0.976 | 1.000 | 0.988 | 6/240 | 19 |

**Neither model wins the gate.** The onnx build is worse on precision and worse on recall than a page
of regexes, 200 times slower, and it finds **0.00** of the planted IBANs. Unioning everything it
emits costs precision 0.996 to 0.845 and buys no recall, because the patterns were already at 1.000.
That is why nothing here is exported: `vishalakshi/pii.py` carries the arithmetic, and a wheel that
imported `onnxruntime` to lose on both axes would be a worse library.

**Do not use the onnx int8 build.** It is in the repo, it is 317 MB against 1.15 GB, it loads and it
runs. It also finds 0 of 27 planted emails, 0 of 27 IBANs, 3 of 27 NHS numbers and 4 of 27 SSNs, for
recall 0.446. DeBERTa-v3's disentangled attention does not survive dynamic quantisation, and the
failure is silent. Nothing in the model card says so.

### The tflite encoder

`ai_edge_litert`, the two signatures `pii_128` and `pii_512`, fixed-length int32 inputs. A raw argmax
fragments every entity across byte-BPE tokens, so `litert_spans` collapses the BIOES tags per entity
and windows anything longer than the sequence. Its taxonomy is the richest of the three, 28 types
across 28 languages. It is also the worst detector measured here:

| sentence | fp16 | wi8fc |
|---|---|---|
| `Contact jane.doe@example.com` | `email` | `email` |
| `Deliver to 42 Elm Street, London.` | `address`, `address` | `address`, `address` |
| `card 4111 1111 1111 1111` | `national_id` | `national_id` |
| `NHS number 4505577104` | `online.url` | `online.url` |
| `The claimant, Sarah Nakamura, disputes...` | nothing | nothing |
| `Ada Lovelace signed it.` | nothing | nothing |
| `GB82WEST12345698765432` | nothing | nothing |
| `Aadhaar 2234 5678 9012` | `special.religion` | `special.religion` |
| `TFN 123 456 782`, `NRIC S1234567D` | `special.religion` | `special.religion` |
| `EN 60601-1`, the Confluence URL | nothing | nothing |
| ms/doc at `pii_128` | 2295 | 217 |

fp16 and wi8fc agree on every line, which rules out quantisation and leaves the model. It finds no
names at all, where onnx fp32 finds 5 of 8. It labels a card a national id and an NHS number a URL,
and it labels Aadhaar, TFN and NRIC digits `special.religion`.

**The useful thing in that repo is not the weights.** `context_cued.py` states the finding this
module is built on: an arbitrary alphanumeric ID has no learnable shape, a passport number and a
purchase-order number are byte-for-byte indistinguishable, so the model gets about zero recall on one
and the field label has to gate it. `pii_hybrid_decode.py` then hands email, IBAN, SSN, card with
Luhn, IP, MAC, IMEI, URL and GPS back to regex with validators, and trusts the model only for names,
addresses and conditions. That is the same split this module reached by measurement, written by the
authors of one of the models. Their documented precision traps became the external provenance for
the `ticket` group in `HELDOUT`, and their multilingual field labels are why the cue-anchored kinds
here carry `आधार`, `บัตรประชาชน`, `burgerservicenummer` and `steuerliche identifikationsnummer`
alongside the English ones.

### The one thing a model is for

Eight sentences no pattern can reach by construction, a name with no honorific and a street with no
number:

| | found |
|---|---|
| patterns | 0/8 |
| patterns, `ner=True` | 2/8 |
| onnx fp32, `person` only | **5/8** |
| onnx fp32, every kind | 7/8 |
| litert fp16 | 0/8 |

and onnx fp32 invented identity in 0 of 8 clean sentences. So a union is worth making for exactly one
kind, `MODEL_ADDS`, which is `{'person'}`: precision stays 0.996 and recall 1.000 while the
blind-spot recall goes from 2/8 to 5/8. Union every kind and precision drops to 0.845 for nothing.

A gigabyte of weights and 73 ms per document to find a name the arithmetic cannot, on a gate already
at 1.000 out of sample, is a trade to make per vault and outside the wheel. `mark_pii` is still the
answer for a document that names somebody and matches nothing.

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
| a learned PII backend | **not shipped** | worse on precision and on recall than the patterns, and 200 times slower |

The honest summary is that the infrastructure is worth having and the models are not yet. Three
generated corpora is not a real vault, and every number here should be re-measured against yours:
`evals/gold.py` builds a gold set from a real one for exactly that.
