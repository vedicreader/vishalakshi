"""What do the checksums buy, and what does the detector miss.

`pii.py` says a checksum is what separates a detector from a superstition. That is a claim about a
false-positive rate, so it needs a corpus of things that look like PII and are not: order numbers,
ISBNs, part numbers, timestamps, version strings, long digit runs. The negatives are the whole
experiment. Positives are easy to detect and easy to fake being good at.

Measured per kind, and again with every validator disabled, so the difference is the answer.

    python -m evals.pii
"""
import sys, random, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def luhn_number(rng, n=16):
    "A card number that passes Luhn, built by choosing the check digit rather than by rejection."
    ds = [rng.randrange(10) for _ in range(n - 1)]
    tot, parity = 0, n % 2
    for i, d in enumerate(ds):
        if i % 2 == parity: d = d*2 - 9 if d*2 > 9 else d*2
        tot += d
    return ''.join(map(str, ds)) + str((10 - tot % 10) % 10)


def nhs_number(rng):
    while True:
        ds = [rng.randrange(10) for _ in range(9)]
        chk = 11 - sum(d*(10-i) for i, d in enumerate(ds)) % 11
        if chk == 10: continue
        return ''.join(map(str, ds)) + str(0 if chk == 11 else chk)


def iban(rng):
    body = ''.join(rng.choice('0123456789') for _ in range(14))
    for c in range(1, 100):
        cand = f'GB{c:02d}ABCD{body}'
        t = cand[4:] + cand[:4]
        if int(''.join(str(int(ch, 36)) for ch in t)) % 97 == 1: return cand
    return None


POSITIVE = {
    'email':  lambda r: f"Contact {r.choice(['jane','arun','mira'])}.{r.choice(['doe','patel','ross'])}@example.com for the file.",
    'card':   lambda r: f"Payment taken on card {luhn_number(r)}.",
    'nhs':    lambda r: f"NHS number {nhs_number(r)} recorded at triage.",
    'iban':   lambda r: f"Settlement to {iban(r)} on the 3rd.",
    'ssn':    lambda r: f"SSN {r.randrange(1,665):03d}-{r.randrange(1,99):02d}-{r.randrange(1,9999):04d} on file.",
    'phone':  lambda r: f"Call +44 20 7946 {r.randrange(1000,9999)} before noon.",
    'dob':    lambda r: f"Date of birth 14/03/{r.randrange(1940,2005)}, confirmed.",
    'account':lambda r: f"Account number {r.randrange(10**7, 10**8)} was debited.",
    'address':lambda r: r.choice([
        f"Deliver to {r.randrange(1,300)} Elm Street, London.",
        f"The registered office is 221B Baker Street, London NW1 {r.randrange(1,9)}XE.",
        f"Ship to {r.randrange(100,999)} Market St, San Francisco CA 941{r.randrange(10,99)}.",
        f"Collected from {r.randrange(1,99)} Victoria Road on the 3rd.",
        f"Returned to {r.randrange(1,99)} Kings Court, Leeds.",
    ]),
}

#: Things that look like identity and are not. This is the list the claim lives or dies on.
NEGATIVE = [
    # a bare number in front of a common noun is not a street line, and this is where a loose
    # address pattern does its damage: every numbered heading in every report would fire
    lambda r: f"Chapter {r.randrange(1,9)} Court decisions are summarised below.",
    lambda r: f"Table {r.randrange(1,9)} Road traffic figures for the quarter.",
    lambda r: f"Figure {r.randrange(1,9)} Way of working, as adopted.",
    lambda r: f"Section {r.randrange(1,99)} Place of performance is unchanged.",
    lambda r: f"Item {r.randrange(1,99)} Drive belt replaced under warranty.",
    lambda r: f"Order number {r.randrange(10**15, 10**16)} shipped on Tuesday.",
    lambda r: f"ISBN 978-{r.randrange(0,9)}-{r.randrange(10000,99999)}-{r.randrange(100,999)}-{r.randrange(0,9)} is out of print.",
    lambda r: f"Part {r.randrange(10**12, 10**13)} supersedes the previous revision.",
    lambda r: f"Build 20240{r.randrange(1,9)}{r.randrange(10,28)}.{r.randrange(1000,9999)} passed all gates.",
    lambda r: f"Transaction ref {r.randrange(10**13, 10**14)} cleared at 14:02.",
    lambda r: f"The run took {r.randrange(1000,9999)} seconds over {r.randrange(100,999)} shards.",
    lambda r: f"Version 4.{r.randrange(0,20)}.{r.randrange(0,20)} deprecates the old endpoint.",
    lambda r: f"Serial {r.randrange(10**14, 10**15)} was returned under warranty.",
    lambda r: f"Between {r.randrange(1900,2000)} and {r.randrange(2001,2024)} the figure trebled.",
    lambda r: f"Grid reference {r.randrange(100000,999999)} {r.randrange(100000,999999)} on the survey.",
    lambda r: f"Invoice total 1{r.randrange(100000,999999)} rupees before tax.",
    lambda r: f"Docket {r.randrange(10**9, 10**10)}-{r.randrange(10,99)} filed with the registry.",
    # A two-letter word before five digits is a US zip only if the letters are a state, and only
    # if they are capitals. Case-folded, `as 12345` and `no 90210` are somebody's address, and a
    # street suffix after a lowercase common noun is a sentence rather than a delivery.
    lambda r: f"As {r.randrange(10000,99999)} units shipped, the line was retired.",
    lambda r: f"No {r.randrange(10000,99999)} records matched the query.",
    lambda r: f"Ref ab {r.randrange(10000,99999)} cleared without comment.",
    lambda r: f"Delivered to {r.randrange(1,99)} the big street party volunteers.",
]

FILLER = ("The committee met on Tuesday and reviewed the outstanding items. "
          "Delivery is scheduled for the following quarter subject to approval. "
          "No further action was recorded against this matter. ")


def corpus(n=400, seed=0):
    "`[(text, kinds_present)]`: half carrying real identity, half carrying lookalikes."
    rng, out = random.Random(seed), []
    kinds = list(POSITIVE)
    for i in range(n // 2):
        k = kinds[i % len(kinds)]
        out.append((FILLER + POSITIVE[k](rng) + ' ' + FILLER, {k}))
    for i in range(n - n // 2):
        out.append((FILLER + NEGATIVE[i % len(NEGATIVE)](rng) + ' ' + FILLER, set()))
    return out


def run(n=400, seed=0):
    from vishalakshi import pii as P

    def score(validators=True):
        saved = dict(P._COMPILED)
        if not validators:
            P._COMPILED.update({k: (rx, None) for k, (rx, _) in saved.items()})
        try:
            tp = fp = fn = tn = 0
            per = {}
            for text, want in corpus(n, seed):
                r = P.pii_report(text)
                got = r.has_pii
                if want:
                    k = next(iter(want))
                    d = per.setdefault(k, [0, 0])
                    d[0 if got else 1] += 1
                    tp, fn = tp + int(got), fn + int(not got)
                else:
                    fp, tn = fp + int(got), tn + int(not got)
            return tp, fp, fn, tn, per
        finally:
            P._COMPILED.clear(); P._COMPILED.update(saved)

    print(f'{n} documents, half carrying identity and half carrying lookalikes\n')
    rows = []
    for label, v in (('with checksums', True), ('regex only', False)):
        tp, fp, fn, tn, per = score(v)
        prec = tp/(tp+fp) if tp+fp else 0.0
        rec = tp/(tp+fn) if tp+fn else 0.0
        f1 = 2*prec*rec/(prec+rec) if prec+rec else 0.0
        rows.append((label, prec, rec, f1, fp, tn+fp, per))
        print(f'{label:<16} precision {prec:.3f}  recall {rec:.3f}  F1 {f1:.3f}  '
              f'false positives {fp}/{tn+fp}')

    print(f'\nchecksums change the false-positive rate from {rows[1][4]}/{rows[1][5]} to '
          f'{rows[0][4]}/{rows[0][5]} of the lookalike documents')
    print(f'\nrecall by kind (with checksums):')
    for k, (hit, miss) in sorted(rows[0][6].items()):
        print(f'  {k:<10} {hit}/{hit+miss}  {hit/(hit+miss):.2f}')

    # The name pass is opt-in, so the number that decides whether to switch it on is not its
    # recall on names: it is how often it invents one in ordinary prose.
    spurious = sum(bool(P.pii_report(t, ner=True).kinds.get('person')) for t, want in corpus(n, seed) if not want)
    n_neg = sum(1 for _, want in corpus(n, seed) if not want)
    print(f'\nner=True on the {n_neg} lookalike documents: {spurious} gained a spurious person')
    for t in ('Dr Charles Babbage signed it.', 'Ada Lovelace signed it.'):
        print(f'  {t:32} -> {P.pii_report(t, ner=True).identifying or "nothing"}')
    return rows


if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    run()
