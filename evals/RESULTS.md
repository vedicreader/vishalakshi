# What the evals actually said

Everything below is from `evals/`, on generated corpora (`evals/corpus.py`) with the
`retrieval` static encoder, except section 3b, which is on real legislation (`evals/regcorpus.py`).
Reproduce with `python -m evals.noise`, `python -m evals.run`, `python -m evals.jobs`,
`python -m evals.pii`, `python -m evals.pii_real` and `python -m evals.pii_model`.
Every comparison is paired over queries with a 5,000-sample bootstrap; a CI spanning zero is
reported as no difference rather than as a small win.

Read the headline first: **the noise score works, and no learned reranker beat plain RRF
reproducibly.** The parts that are switched on by default are exactly the parts that earned it.

## 1. The noise score

Per-feature AUC against ground truth, 72 documents of which 8 are boilerplate by construction:

| feature | AUC | boiler z | survey z | what it is |
|---|---|---|---|---|
| `hub` | 0.984 | +1.51 | -1.66 | how often a chunk is in others' k-NN lists |
| `spread_chunk` | 0.982 | +1.50 | +0.67 | entropy of one chunk's similarity over topic centroids |
| `off_centre` | 0.881 | +1.19 | -1.56 | cosine distance from the corpus centroid |
| `dup_out` | 0.800 | +0.94 | -1.12 | chunks near-duplicated in *another* document |
| `low_idf` | 0.602 | +0.32 | -0.07 | mean term specificity, negated |
| `promiscuity` | 0.500 | n/a | n/a | distinct past queries retrieving it (needs a feedback log) |
| `redundancy` | 0.498 | -0.01 | -0.24 | chunks near-duplicated inside the same document |
| `spread_doc` | 0.453 | -0.15 | **+0.83** | entropy of the document's chunks over clusters |
| `short` | 0.422 | -0.24 | +0.55 | fraction of very short chunks |

Blended: **0.988 mean AUC** over three corpora (0.967–1.000). Fitted from marks instead of the
fixed weights, held out: **0.996** (0.990–1.000), better on all four corpora tried, from six
marked documents and eighteen confirmed keepers.

### "Spread across clusters means generic", measured

`spread_doc` is that hypothesis, and it scores **0.453 AUC. Below chance.** Worse, look at which
documents it indicts: the corpus plants `Survey` documents that range over every topic and are
*not* noise, and `spread_doc` scores them +0.83 against boilerplate's -0.15. It ranks the surveys
as noisier than the footers.

Measure the same idea one level down and it gets **0.982**, the second-best feature in the table:
the entropy of a *single chunk* over topic centroids, rather than of a document over cluster
assignments. That is the difference between broad and generic: a survey is broad at the document level
and specific in each paragraph, and boilerplate is generic in every chunk it has. But even that
correction only partly separates surveys (gap +0.83); what cleanly does is `hub` (+3.17) and
`dup_out` (+2.06). Genericness is better measured as *"this gets retrieved for everything"* than as
anything about topics.

### An incidental finding

`usearch.index.kmeans` does not honour its `seed`. Called twice on identical input it returns
different assignments. `spread_doc` is an entropy over those assignments, and it drifted across its
whole range between two calls on the same vault. Fixing it took `spread_chunk` from 0.807 to
0.982. `quality._centroids` is now a seeded k-means++ plus Lloyd in numpy, at comparable cost since
both are dominated by one `V @ C.T` per iteration.

## 2. The rerankers

Known-item queries (one document answers each, different every time), **document-disjoint** split
(no test query's gold document was seen in training), three corpora, mean Δ vs base:

| system | nDCG@10 | MRR@10 | recall@10 | significant wins / losses |
|---|---|---|---|---|
| `+noise` (unsupervised filter) | **+0.001** | **+0.005** | -0.015 | 1 / 0 |
| `+linear` fused at α=0.25 | -0.001 | -0.004 | +0.007 | 0 / 0 |
| `+gbdt` (replaces order) | -0.005 | +0.019 | -0.093 | 1 / 1 |
| `+forest` (replaces order) | -0.085 | -0.051 | n/a | 0 / 2 |
| `+prior` (Beta posterior) | -0.043 | -0.065 | n/a | 0 / **3** |
| `+linear` (replaces order) | -0.127 | -0.082 | -0.274 | 0 / 2 |

Three things to take from this.

**Gradient boosting did not win.** It beat the baseline on MRR on one corpus (+0.083, p=0.05) and
lost on another (-0.109, p=0.01). One seed would have shipped it. That is the entire reason the
harness resamples and reports across corpora.

**Substituting the ranking is the dangerous operation, not learning.** The same linear model costs
-0.127 nDCG when it sorts by its own score and -0.001 when it is fused with the incoming order by
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

`python -m evals.pii`: 960 documents, half with planted identity and half with lookalikes, over 8
draws. The lookalikes are grouped, so a residual false positive has a name. Nine of the fifteen
groups carry *valid* checksums or real regulatory digit shapes. A random corpus meets that case one
time in eleven. A spec document meets it on every page.

| detector | precision | recall | F1 | false positives |
|---|---|---|---|---|
| regex only | 0.913 | 1.000 | 0.955 | 364/3840 |
| with checksums | **0.996** | **1.000** | **0.998** | **15/3840** |

Recall is 1.000 on all 25 gating kinds. Each is reported as itself, not as something else. `ip` is
found 20/20 and gates 0/20, which is what "reportable but not identifying" means. Every residual
false positive is a checksum collision on a random digit run: 12/240 in `bare`, 3/200 in
`apac_invalid`.

Those three are a shadowing rather than a collision. A Thai national ID is thirteen digits and
`card` matches twelve to nineteen, so about one malformed national ID in ten passes Luhn and reports
as a card. A *valid* one is untouched. Spans de-overlap longest-first, the cue-anchored `thai_id`
span is longer than the bare digit run, and 40 of 40 valid ones report as `thai_id`. The failure
needs a document holding a broken national ID and no real identity.

### Reading the digits is not enough; you have to read what is around them

The corpus grew two groups after two reported failures, and both were real:

- `EN 60601-1`, `EN 60601-1-2`, `EN 60601` were reported as **addresses**. `[A-Z]{2} \d{5}` is a US
  state and ZIP, and it is also every standards designation ever written.
- A Confluence page id, `.../pages/2377744435`, was reported as an **NHS number**. It is: ten digits
  pass the NHS mod-11 check about one time in eleven, and that one was one of them.

Every guard, removed on its own with everything else left in place. `python -m evals.pii --ablate`
prints this table; nothing in it was measured by hand.

| guard removed | precision | false positives | which group comes back |
|---|---|---|---|
| — (as shipped) | **0.996** | **15/3840** | `bare` 12/240, `apac_invalid` 3/200 |
| every checksum | 0.913 | 364/3840 | `apac_invalid` 200/200, `bare` 93/240, `money` 71/240 |
| `US_STATES` before a ZIP | 0.960 | 159/3840 | `standard` 96/288, `citation` 48/240 |
| street name inside `address` | 0.996 | 15/3840 | nothing |
| `DESIGNATOR` to the left | 0.943 | 233/3840 | `cued` 96/288, `apac_cued` 122/200 |
| `URLISH` span suppression | 0.984 | 63/3840 | `link` 48/192 |
| NHS needs groups or its name | 0.994 | 22/3840 | `bare` 17/240, `refnum` 2/384 |
| card needs an issuer digit | 0.993 | 28/3840 | `bare` 24/240 |
| grouped-number suppression | 0.947 | 213/3840 | `money` 192/240 |
| `passport` needs a value | 0.984 | 63/3840 | `about` 48/384 |
| `licence` needs a value | 0.984 | 63/3840 | `about` 48/384 |
| `medical` needs a value | 0.972 | 111/3840 | `about` 96/384 |
| regional checksums | 0.931 | 283/3840 | `apac_invalid` 200/200, `money` 71/240 |
| regional cue words | 0.992 | 32/3840 | `bare` 29/240 |

Recall stays 1.000 in every row: none of these guards is trading recall for precision.

The guards overlap, and two do a second job. `US_STATES` went in to stop `EN 60601` being a state
and a ZIP. It also stops `65 FR 82802`, the US Federal Register citation, which has the same shape.
Nobody was thinking about that one. The ABN's mod-89 went in to read Australian business numbers.
The 71 `money` documents it holds back are EU budget lines: `EUR 360 000 000 000` contains
`60 000 000 000`, which is an ABN's shape exactly. The street-name requirement inside `address` is
covered by `DESIGNATOR` here, 0.996 either way. With `DESIGNATOR` off it is worth 0.965 against
0.894, so it stays.

The regional cue words look cheap at 32/3840 against 15/3840. They are, because the grouped-number
guard already suppresses most of what they would admit. Removing both is the case they exist for.

`DESIGNATOR` keeps its acronyms case-sensitive, because lowercase `en` is an ordinary English word.
`No` was in the list and is not any more: it suppressed `No. 5 Elm Street`, `No 5 Elm Street` and
`Flat 2, No. 12 Victoria Road` and changed precision by nothing. A guard that costs recall and buys
no precision is not a guard.

### 3b. What real documents said, which was not what the generated ones said

`python -m evals.pii_real`: eighteen acts, 5,062,290 characters, none of which contain a real
person's card, account or address. The whole corpus is a labelled negative that nobody had to
annotate, so every match is an error and the target is zero. Eight EU acts come from
`litesearch/examples/pdfs` and go through `pdf_parse`, so the text carries the line breaks and
header noise a real ingest carries; the other ten are fetched by `evals/regcorpus.py`.

| jurisdiction | documents | characters | why it is in the corpus |
|---|---|---|---|
| EU | 10 | 2.08 M | article references, and money space-grouped in threes |
| US | 1 | 0.24 M | `42 U.S.C. 1302(a)`, `Pub. L. 104-191`, `65 FR 82802` |
| Australia | 2 | 1.60 M | the Telecommunications Act 1997 is a statute about phone numbering |
| India | 4 | 0.93 M | digit grouping is 2-2-3 (`12,34,567`), and amounts run in lakhs |
| Thailand | 1 | 0.20 M | Thai script and Thai numerals, which no pattern here can read |

Southeast Asia is one statute rather than four. Singapore Statutes Online, AGC Malaysia and the
Philippine Official Gazette all sit outside this sandbox's egress policy, and no GitHub mirror of
their English text turned up. The Malaysian and Indonesian identifiers below are measured on
generated documents only. That is a real gap, and not a small one. It is the gap the EU-only corpus
had before Australia and India went in.

The generated corpus at 0.996 precision had **15 false positives** on this material, in three
classes, none of which anybody had thought to generate:

- **Money.** `EUR 360 000 000 000` matched the UK trunk-number pattern, nine times across four
  regulations. A space is the thousands separator across Europe, so every large budget line carries
  a `0`-leading group of three, which is exactly `\b0\d{1,4}[ .-]\d{3,4}[ .-]?\d{3,4}\b`.
- **A cue with no value after it.** `passport, identity card` matched `passport` and
  `driver's licence details` matched `licence`, because `[A-Z0-9]{6,9}` under `re.I` is also every
  ordinary word of six to nine letters.
- **A document about identifiers.** `Medical record numbers;` matched `medical` five times in
  45 CFR 164, which is a regulation about medical record numbers rather than a document containing
  one. The pattern never required a number at all.

| | false positives | per 100,000 characters |
|---|---|---|
| before | 15 | 0.64 |
| after | **0** | **0.00** |

Four guards, each removed on its own (`python -m evals.pii_real --ablate`):

| guard removed | false positives | where |
|---|---|---|
| — (as shipped) | **0** | |
| grouped-number suppression | 9 | `phone` 9 |
| `passport` needs a value | 1 | `passport` 1 |
| `licence` needs a value | 0 | |
| `medical` needs a value | 5 | `medical` 5 |
| all four | 15 | |

`licence` cost nothing on the EU-only corpus. It costs 1 once Australia is in it. That is the whole
argument for two corpora, and for more than one jurisdiction in the second. Each is blind where the
other is not.

Recall was measured in the same place. One planted identity spliced into a real regulatory passage
instead of into three sentences of filler: **267/267, 1.000**, over all 25 gating kinds. Dense legal
boilerplate around a card number does not hide it.

The four classes are distilled back into `evals/pii.py` as the `money`, `citation`, `celex` and
`about` groups. The digits are randomised, and every `money` document carries a `0`-leading group by
construction, so they stay measured on a corpus that resamples.

### 3c. Somebody else's digits

Before this section the detector was European and North American. Against twenty identifiers from
the three regions the corpus had just gained, it found **two**, and one of those was the wrong kind:

| | found before | found now |
|---|---|---|
| India: Aadhaar, PAN, GSTIN, IFSC, `+91` mobile | 0/5 | **5/5** |
| Australia: TFN, ABN, Medicare, `04xx` mobile | 1/4 | **4/4** |
| SE Asia: NRIC, MyKad, NIK, Thai national ID | 0/4 | **4/4** |

Ten kinds went in. Each decides on a checksum or an embedded date, because shape on its own is not
usable. `\d{3} \d{3} \d{3}` is an Australian tax file number. It is also a budget line, 34 times in
Regulation 2021/695. `tfn`, `medicare`, `nik` and `thai_id` need a cue word on top. Their bare digit
runs are nine, ten, sixteen and thirteen digits: a phone number, a phone number, a card, a
timestamp.

| kind | what decides it | anchored on |
|---|---|---|
| `aadhaar` | Verhoeff, and UIDAI issues nothing starting 0 or 1 | Verhoeff of `236` is `3` |
| `pan` | shape only, `[A-Z]{5}\d{4}[A-Z]`, cased | — |
| `gstin` | base-36 check character over 14 | `27AAPFU0939F1ZV` |
| `ifsc` | shape only, `[A-Z]{4}0[A-Z0-9]{6}`, cased | — |
| `tfn` | weighted mod-11, cue required | `123 456 782` |
| `abn` | mod-89, first digit less one | `51 824 753 556` (ATO) |
| `medicare` | weighted mod-10, cue required | `2123 45670 1` |
| `nric` | check letter, three tables by prefix | `S1234567D` |
| `mykad` | a real YYMMDD and a real state code | — |
| `nik` | a real DDMMYY, day plus 40 for women | — |
| `thai_id` | mod-11, cue required | — |

ACN was left out on purpose: an Australian company number identifies a company, not a person.

What the checksums are worth, on the 5 M characters of legislation rather than on anything
generated (`python -m evals.pii_real` prints this):

| kind | pattern matched | checksum passed |
|---|---|---|
| `abn` | **12** | **0** |
| the other ten | 0 | 0 |

Twelve EU budget lines have an ABN's exact shape, and mod-89 rejects all twelve. The other ten kinds
have nothing to say on this corpus. That is the honest reading of a zero. No EU, US, Australian,
Indian or Thai act holds a string shaped like an Aadhaar number, or writes "tax file number"
followed by nine digits. `evals/pii.py` measures those instead. `apac_money`, `apac_ref`,
`apac_cued` and `apac_invalid` went in for it: Indian 2-2-3 money grouping, Australian and Indian
statute references, valid regional checksums under `Order` and `Invoice`, and the cue present with
the checksum broken. Turning the regional checksums off costs 0.996 to 0.931 and hands back 71 EU
budget lines. Turning the cue words off costs 0.996 to 0.992.

### What is in the corpus that the detector is right to want

One thing in those 5 M characters is a real person. Legislation is signed. `R. METSOLA` and
`M. MICHEL` sit in the AI Act's signature block, shaped `The President \n R. METSOLA`. `ner=True`
finds **0 of 2**. The anchor is an honorific and a signature block has none. It also invents **0**
names in the other 5 M characters. The generated corpus reports the same trade, and this measures it
on prose nobody wrote as a test. It does not hallucinate. It does not find the names that are there.
That is why `mark_pii` exists.

### Names

Names are the one kind no pattern finds, so they are the one kind behind `ner=True`. The extractor
is the honorific-anchored regex in `extract._noun_ents`, not a model: no weights, and 21 ms over
180,000 characters. `Dr Charles Babbage` is found and a bare `Ada Lovelace` is not, which is a
recall limit and the reason `mark_pii` stays. The number that decides whether to switch it on is
what it invents in ordinary prose: **0 of the 480 lookalike documents** gained a spurious person,
and 0 in 5 M characters of legislation.

`scanned_ner` is in every report, because a zero `person` count means nothing without knowing
whether anything looked. `n` and `density` stay arithmetic-only so `DENSE` keeps its meaning.

## 3a. The learned detector

`pip install 'vishalakshi[model]' && python -m evals.pii_model`. The model is
`onnx-community/piiranha-v1-detect-personal-information-ONNX`, a DeBERTa-v3 token classifier.
Both builds in that repo are measured, because the quantised one is the one you would reach for.

Every number here was measured on the 480-document corpus that preceded section 3b. None has been
re-run since the corpus grew to 960 and the regulatory guards went in. Re-running needs the weights,
a 1.1 GB download.

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

**The claim is sound. The busy timeout was not.** `UPDATE ... RETURNING` through a partial index
never handed one job to two workers, in any run. The first run still lost 2 of 400, to
`apsw.BusyError` on the *history* write. apsw's stock busy timeout is 100 ms, and 8 processes on one
file exceed it, so the write failed instead of waiting and took the worker with it. `Queue` now
sets `BUSY_TIMEOUT_MS` (30 s) on its connection, which is what litesearch already does on its own
write paths. Nothing was wrong with the claim; the queue was simply not waiting its turn.

**One instance of that is not the queue's to fix, and the harness was hiding it.** apsw's
bestpractice runs `pragma optimize` while *opening* a connection, before any queue code exists to
raise the timeout, so 1 to 3 of 8 workers died in `database()` in 4 of 5 runs. The measurement
reported `workers=8` regardless. It printed the number of processes it asked for, not
the number that ran, and fewer workers is less contention: the harness was quietly making the
result better. `workers` is now the count that did work, `_open` retries the connect, and every
measurement asserts on worker exit codes.

**A lease is not enough on its own. `ack` has to be fenced.** A handler slower than its lease is
reclaimed underneath it and handed to a second worker, and the first worker then finishes and acks a
job it no longer holds. 6 slow handlers of 24 produced **2 jobs acked by two workers each**, and a
late `fail` from the real holder took a `done` job back to `ready` for a third run. `ack` and `fail`
now check state and worker inside the same transaction as the update. The same 6 handlers now give 0
double acks, 18 refused acks recorded as `lost`, and 6 dead letters. That is the honest outcome. A
lease shorter than the work cannot be completed. It should fail loudly rather than book two
successes.

**0.030 ms per empty poll is why there is no watcher here.** honker earns its `PRAGMA data_version`
thread by making cross-process wake sub-millisecond, which matters when a job is a function call.
Here a job is a page fetch on a schedule measured in hours, so a one-second poll costs 0.003% of a
core and the watcher buys nothing. That is the whole argument for a table over the extension, and
it is a number rather than a preference.

The 4-in-200 redelivery rate is not a defect to fix. It is what at-least-once means. It is
safe here only because ingest is idempotent. litesearch skips a source it already holds, so a
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
