# Release notes

<!-- do not remove -->

## Unreleased

**`vishalakshi.pii`** — whether a document is somebody's business, decided by arithmetic. Patterns
with checksums where a checksum exists (Luhn for cards, mod-97 for IBANs, mod-11 for NHS numbers)
and tightly written where none does, de-overlapped longest-first so one card is not counted three
times, and sampled at both ends of a long document because a statement's account number is in its
header. `pii_spans`, `pii_report`, `redact`, `Vault.pii(ref)` and `pii_ctx(ctx)`.

Not a model, deliberately: a classifier that has to read the document in order to say whether the
document may be read has already lost. And `has_pii` is narrower than "found something" — an IP
address or an API key is reported but does not on its own make a document private, or every
question about a server log ends up on the slow path.

**`ask(pii=...)`** — when the sections retrieval chose hold personal information, `'local'` (the
default) answers on `pii_model` under `PII_SP`, a briefing that forbids reproducing any personal
detail and asks the questioner what instruction it needs instead. Before a character is sent, the
chat that was built is checked for a local runtime; a caller that lends a hosted one is refused,
because the check is on the object rather than on the caller having been honest about the name.
The reply is re-scanned on the way out and masked if the model slipped. `'redact'` masks the
sections and answers anywhere, `'refuse'` answers nothing, `'off'` does not look. `instruction=`
carries the questioner's reply back for the second turn.

`ask`, `ask_doc` and `explain` take `mk_chat=`: build this call's chat with that instead of
`new_chat`, same signature. `use_chat` already swapped the factory, but process-wide and only
for the duration of a block -- right for a notebook replaying recorded replies, wrong for a
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
