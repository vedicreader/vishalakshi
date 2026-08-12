# Release notes

<!-- do not remove -->

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

Not a model, deliberately: a classifier that has to read the document in order to say whether the
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
