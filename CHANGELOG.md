# Release notes

<!-- do not remove -->

## Unreleased

**`vishalakshi.pii`**: digits are read in context. `EN 60601-1` was an address. A ten-digit
Confluence page id in a URL was an NHS number. Both were reported and both are fixed. `US_STATES`
gates the ZIP alternative. `DESIGNATOR` suppresses a match introduced by a reference word. `URLISH`
suppresses digit runs inside a link. `nhs` needs its groups or its name, and `card` needs an issuer
digit. Precision 0.762 -> **0.996** at unchanged recall 1.000 on 480 documents. `evals/pii.py` grew
the `standard`, `link`, `cued` and `bare` lookalike groups to measure it.

The same detector then read 5 M characters of real legislation. It made **15 false positives** in
three classes. None had been generated.

- `EUR 360 000 000 000` matched the UK trunk-number pattern, nine times. A space is the thousands
  separator across Europe. `000 000 000` is a phone number if you skip the `360 ` in front of it.
- `passport, identity card` matched `passport`. `driver's licence details` matched `licence`. Under
  `re.I`, `[A-Z0-9]{6,9}` is every ordinary word of six to nine letters.
- `Medical record numbers;` matched `medical`, five times in 45 CFR 164. That is a regulation
  *about* medical record numbers. The pattern never asked for a number.

Four guards answer them. A digit group butting against a match makes it a slice of a longer number.
`passport`, `licence` and `medical` each need a value with a digit after the cue word. **0 false
positives** after. Recall stayed 1.000, with a planted identity spliced into 267 real passages.

The corpus then grew to five jurisdictions. The detector turned out to be European and North
American. It found **two** of twenty identifiers from Australia, India and South-East Asia, and
called one of those a phone number.

Ten kinds answer that. `aadhaar` (Verhoeff), `pan`, `gstin` (base-36), `ifsc`, `tfn` (weighted
mod-11), `abn` (mod-89), `medicare` (weighted mod-10), `nric` (Singapore's check letter), `mykad`
and `nik` (an embedded birth date, all either carries), `thai_id` (mod-11). `phone` gained the
`+91 98765 43210` split. Each decides on a checksum or a date. Shape alone is not usable:
`\d{3} \d{3} \d{3}` is an Australian tax file number, and also a budget line, 34 times in
Regulation 2021/695. `tfn`, `medicare`, `nik` and `thai_id` need a cue word too. Twelve EU budget
lines carry an ABN's exact shape, and mod-89 rejects all twelve. ACN was left out. An Australian
company number identifies a company.

`evals/regcorpus.py` is the corpus. Eight EU acts from `litesearch/examples/pdfs` through
`pdf_parse`, plus the EU AI Act, the GDPR, 45 CFR Part 164, the Australian Privacy Act 1988 and
Telecommunications Act 1997, the Indian Penal Code, Criminal Procedure Code, Evidence Act and DPDP
Act 2023, and the Thai PDPA. 18 documents, 5,062,290 characters, fetched on first run.
`evals/pii_real.py` runs it.

`evals/pii.py` went from 480 documents to 960. It gained positives for the five gating kinds that
shipped with a pattern and no test (`passport`, `licence`, `sortcode`, `secret`, `medical`) and for
all ten regional kinds. It gained eight lookalike groups distilled from the real documents:
`money`, `citation`, `celex`, `about`, `apac_money`, `apac_ref`, `apac_cued`, `apac_invalid`. It
gained `--ablate`, which prints every guard's contribution. That table in RESULTS.md is no longer
assembled by hand. Precision **0.996** at recall 1.000 over 8 draws of 960. All 25 kinds found, each
reported as itself.

`pii_spans`, `pii_report`, `redact`, `redact_obj`, `pii_ctx` and `Vault.pii` take `model=True`,
which adds an ONNX DeBERTa-v3 token classifier (`pip install 'vishalakshi[model]'`). Off by
default: it loses the gate to the patterns on precision *and* recall and is 370× slower, so
`model=True` unions only `MODEL_ADDS` (`{'person'}`), where it lifts 2/8 to 5/8 on names no
honorific introduces. Do not use the int8 build; it silently finds 0.446 of what is there.
`evals/pii_model.py`.

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
order: mediocre and fused costs -0.001 nDCG, mediocre and substituted costs -0.127. Full numbers
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

Not a model, deliberately: a classifier that has to read the document in order to say whether the
document may be read has already lost. And `has_pii` is narrower than "found something". An IP
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

A factory rather than a chat, deliberately. A chat is built per question, and built again from
scratch when the first prompt overflows the window. A passed-in conversation would carry
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
