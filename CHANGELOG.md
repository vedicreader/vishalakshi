# Release notes

<!-- do not remove -->

## Unreleased

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
