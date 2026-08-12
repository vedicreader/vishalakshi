# Working in this repo

nbdev. The notebooks under `nbs/` are the source; `vishalakshi/*.py` is generated. Edit the
notebook, run `nbdev_export`, never edit the `.py`. CI runs `nbdev_export` and fails on a diff.

## Prose in notebooks

Keep it short. The prose is there so a reader can see what the code does and what was chosen,
not to argue for it.

- Lead with the action or the decision. First sentence does real work. No throat clearing.
- Say what is chosen and move on. One line of reason where the choice is surprising, none where
  it is not.
- Numbers instead of adjectives. "0.453 AUC, below chance" beats "performs poorly".
- No em dashes, no bold inside a paragraph, no "not just X but Y", no rhetorical questions.
- A design rationale that runs past three sentences belongs in a docstring or in `evals/`,
  not in a markdown cell.
The failure mode to avoid is a notebook where the prose is longer than the code and the reader
has to hunt for what actually happens.

## Docstrings and comments

The code is the document. Prose explains what the code cannot say about itself, and nothing else.

- Docstrings: one line. Add a second sentence only to state a measured number or a footgun.
- Inline comments in a `def` signature are nbdev docments and become the API parameter table.
  Keep them, keep them short.
- Body comments: one line, and only where the code genuinely does not say it. A comment that
  restates the line under it goes.
- No changelog in a comment. "This used to do X and it broke" is a commit message.
- Never reflow a triple-quoted string that is not a docstring. `PII_SP`, `VAULT_SP` and `TYPE_SP`
  are prompts with line continuations; rewrapping one edits what a model is told.

## Evals

`evals/` is not shipped in the wheel. Results go in `evals/RESULTS.md` with the method, and
anything claimed in a docstring should have a number there behind it. Paired bootstrap over
queries, CI spanning zero reported as no difference.
