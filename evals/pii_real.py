"""The detector on 5 M characters of real legislation, where every match is a false positive.

`evals/pii.py` measures precision against lookalikes somebody thought of. This measures it against
lookalikes nobody thought of. Eighteen acts from five jurisdictions (`evals/regcorpus.py`), none
holding a real person's card, account or address. The whole corpus is a labelled negative, so any
match is wrong. Recall is measured here too, by splicing the `evals/pii.py` positives into real
passages instead of into three sentences of filler.

What it found, and what the guards in `pii.py` now answer:

- `EUR 360 000 000 000` matched the UK trunk-number pattern nine times. `000 000 000` is a phone
  number if you do not read the `360 ` in front of it.
- `passport, identity card` matched `passport`, and `driver's licence details` matched `licence`.
  `[A-Z0-9]{6,9}` under `re.I` is every ordinary word of six to nine letters.
- `Medical record numbers;` matched `medical` five times in 45 CFR 164, a regulation *about* medical
  record numbers.

    python -m evals.pii_real
    python -m evals.pii_real --ablate     # each guard switched off on its own
"""
import sys, re, random, argparse, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: What the corpus may contain, as `(document, kind, matched)`. Empty: these acts hold no identity.
EXPECTED = set()

#: The four guards this corpus asked for. Switched off through `evals.pii.GUARDS`, so both corpora
#: ablate one definition.
NEW = ('grouped-number', 'passport value', 'licence value', 'medical value')

#: The one real person in the corpus: legislation is signed. Both sit in the AI Act's signature
#: block, shaped `The President \n R. METSOLA`, with no honorific.
SIGNATORIES = {'ai_act_2024_1689': ['R. METSOLA', 'M. MICHEL']}


def false_positives(docs, ner=False):
    "`[(doc, kind, matched, context)]` per span found. On this corpus that is every error."
    from vishalakshi import pii as P
    out = []
    for name, text in docs:
        for s, e, k, v in P.pii_report(text, mx=len(text), ner=ner).spans:
            if (name, k, v) in EXPECTED: continue
            out.append((name, k, v, re.sub(r'\s+', ' ', text[max(0, s-70):e+40])))
    return out


SENT = re.compile(r'(?<=[.;:])\s')

def passages(docs, n=270, chars=1200, seed=0):
    "Windows of real regulatory prose, cut on sentence boundaries, spread over the documents."
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
    "Plant one `evals.pii` positive mid-passage and see whether it still reads."
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

    candidates(docs)

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


def candidates(docs, kinds=None):
    """How often each pattern matched, and how much of that its checksum let through.

    0 candidates means this corpus cannot speak to that kind. Many candidates and 0 survivors is a
    checksum earning its place on material nobody generated."""
    from vishalakshi import pii as P
    print(f'\n  {"kind":10} {"pattern matched":>15} {"checksum passed":>16}')
    for k in (kinds or P.REGIONAL):
        rx, ok = P._COMPILED[k]
        hit = [m.group(0) for _, t in docs for m in rx.finditer(t)]
        print(f'  {k:10} {len(hit):>15} {sum(ok is None or ok(v) for v in hit):>16}')


def names(docs):
    "What `ner=True` makes of the one real person here, and what it invents in the rest."
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
