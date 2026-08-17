"""The detector on 2.3 M characters of real legislation, where every match is a false positive.

`evals/pii.py` measures precision against lookalikes somebody thought of. This measures it against
lookalikes nobody thought of: eleven EU and US acts (`evals/regcorpus.py`), none of which contain a
real person's card, account or address, so the whole corpus is a labelled negative and any match at
all is wrong. Recall gets measured too, by splicing the `evals/pii.py` positives into real passages
rather than into three sentences of filler.

What it found, and what the guards in `pii.py` now answer:

- `EUR 360 000 000 000` matched the UK trunk-number pattern nine times across four regulations,
  because `000 000 000` is a phone number if you do not look at the `360 ` in front of it.
- `passport, identity card` matched `passport` and `driver's licence details` matched `licence`,
  because `[A-Z0-9]{6,9}` under `re.I` is also every ordinary word of six to nine letters.
- `Medical record numbers;` matched `medical` five times in 45 CFR 164, which is a regulation about
  medical record numbers rather than a document containing one.

    python -m evals.pii_real
    python -m evals.pii_real --ablate     # each guard switched off on its own
"""
import sys, re, random, argparse, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: What the corpus is allowed to contain, as `(document, kind, matched)`. Empty: eleven public acts,
#: no real identity in any of them, so a residual match is a residual false positive.
EXPECTED = set()

#: The four guards this corpus asked for, switched off through `evals.pii.GUARDS` so there is one
#: definition of what a guard is and both corpora ablate the same code.
NEW = ('grouped-number', 'passport value', 'licence value', 'medical value')

#: The one thing in the corpus that *is* a real person: legislation is signed. Both names sit in the
#: AI Act's signature block, in the shape `The President \n R. METSOLA`, with no honorific anywhere.
SIGNATORIES = {'ai_act_2024_1689': ['R. METSOLA', 'M. MICHEL']}


def false_positives(docs, ner=False):
    "`[(doc, kind, matched, context)]` for every span found, which on this corpus is every error."
    from vishalakshi import pii as P
    out = []
    for name, text in docs:
        for s, e, k, v in P.pii_report(text, mx=len(text), ner=ner).spans:
            if (name, k, v) in EXPECTED: continue
            out.append((name, k, v, re.sub(r'\s+', ' ', text[max(0, s-70):e+40])))
    return out


SENT = re.compile(r'(?<=[.;:])\s')

def passages(docs, n=270, chars=1200, seed=0):
    "Windows of real regulatory prose, cut on sentence boundaries, spread across the documents."
    rng, out = random.Random(seed), []
    for name, text in docs:
        want = max(1, round(n * len(text) / sum(len(t) for _, t in docs)))
        for _ in range(want):
            i = rng.randrange(0, max(1, len(text) - chars))
            w = text[i:i+chars]
            cuts = [m.end() for m in SENT.finditer(w)]
            if len(cuts) >= 2: w = w[cuts[0]:cuts[-1]]
            if len(w) > 200: out.append((name, w))
    rng.shuffle(out)
    return out[:n]


def recall_in_context(docs, n=270, seed=0):
    "Plant one `evals.pii` positive in the middle of a real passage, and see if it still reads it."
    from vishalakshi import pii as P
    from evals.pii import POSITIVE
    rng, kinds = random.Random(seed + 1), list(POSITIVE)
    per, misses = {}, []
    for i, (name, w) in enumerate(passages(docs, n, seed=seed)):
        k = kinds[i % len(kinds)]
        planted = POSITIVE[k](rng)
        cut = w.find(' ', len(w)//2) + 1 or len(w)//2
        text = w[:cut] + planted + ' ' + w[cut:]
        got = k in P.pii_report(text, mx=len(text)).kinds
        d = per.setdefault(k, [0, 0]); d[0 if got else 1] += 1
        if not got: misses.append((name, k, planted))
    return per, misses


def run(ablate=False, ner=False, n=270):
    from evals.regcorpus import documents
    docs = documents()
    if not docs: print('no corpus; run `python -m evals.regcorpus` first'); return
    chars = sum(len(t) for _, t in docs)
    print(f'{len(docs)} real regulatory documents, {chars:,} characters, no identity in any of them\n')

    fps = false_positives(docs)
    print(f'false positives, everything on: {len(fps)} '
          f'({1e5*len(fps)/chars:.2f} per 100,000 characters)')
    for name, k, v, ctx in fps: print(f'  [{name} / {k}] {v!r}\n      ...{ctx}...')

    per, misses = recall_in_context(docs, n)
    hit, tot = sum(h for h, _ in per.values()), sum(h+m for h, m in per.values())
    print(f'\nrecall with a planted identity in {tot} real passages: {hit}/{tot} = {hit/tot:.3f}')
    for k, (h, m) in sorted(per.items()): print(f'  {k:<10} {h}/{h+m}  {h/(h+m):.2f}')
    for name, k, planted in misses: print(f'  missed in {name}: {k} {planted!r}')

    if ablate:
        from evals.pii import without
        print('\neach guard switched off on its own:')
        print(f'  {"guard removed":<20} {"false positives":>15}   where')
        for g in ((), *((x,) for x in NEW), NEW):
            with without(*g): f = false_positives(docs)
            where = {}
            for name, k, *_ in f: where[k] = where.get(k, 0) + 1
            print(f'  {(" + ".join(g) if len(g) < 2 else "all four") or "- (as shipped)":<20} '
                  f'{len(f):>15}   {" ".join(f"{k} {v}" for k, v in sorted(where.items()))}')

    if ner: names(docs)
    return fps


def names(docs):
    "What `ner=True` does with the one real person in the corpus, and what it invents in the rest."
    from vishalakshi import pii as P
    got = [(n, k, v) for n, k, v, _ in false_positives(docs, ner=True) if k == 'person']
    want = [(n, s) for n, ss in SIGNATORIES.items() for s in ss]
    hit = sum(any(n == d and s in v for d, _, v in got) for n, s in want)
    print(f'\nner=True: {hit}/{len(want)} of the signatories, {len(got) - hit} other names in '
          f'{sum(len(t) for _, t in docs):,} characters of prose that has none')
    for n, s in want:
        print(f'  {n} {s!r}: {"found" if any(d == n and s in v for d, _, v in got) else "missed"}')


if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    p = argparse.ArgumentParser()
    p.add_argument('--ablate', action='store_true', help='switch each guard off on its own')
    p.add_argument('--ner', action='store_true', help='also report the names, which are real')
    p.add_argument('--n', type=int, default=270, help='planted passages for the recall leg')
    a = p.parse_args()
    run(ablate=a.ablate, ner=a.ner, n=a.n)
