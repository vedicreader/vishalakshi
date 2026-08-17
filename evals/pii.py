"""What do the checksums buy, and what does the detector miss.

`pii.py` says a checksum is what separates a detector from a superstition. That is a claim about a
false-positive rate, so it needs a corpus of things that look like PII and are not: order numbers,
ISBNs, part numbers, timestamps, version strings, long digit runs. The negatives are the whole
experiment. Positives are easy to detect and easy to fake being good at.

Half the negatives are adversarial by construction: the digits carry a *valid* checksum and sit in
a context that says they are not identity. A checksum-passing number under `Order` or inside a URL
is the failure a random corpus finds one time in eleven and a spec document finds on every page.

Four of the negative groups were not thought of here. `money`, `citation`, `celex` and `about` are
the shapes that actually broke the detector on 2.3 M characters of real legislation, distilled back
into ground truth so they stay measured after the fix (`evals/pii_real.py`).

Measured per kind, per negative class, and again with every validator disabled.

    python -m evals.pii
"""
import sys, random, re, argparse
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def luhn_number(rng, n=16):
    "A card number that passes Luhn, built by choosing the check digit rather than by rejection."
    ds = [rng.randrange(10) for _ in range(n - 1)]
    ds[0] = rng.randrange(2, 7)
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


def _grouped(nhs): return f'{nhs[:3]} {nhs[3:6]} {nhs[6:]}'


_ALNUM = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

def _rand(rng, n, alphabet=_ALNUM): return ''.join(rng.choice(alphabet) for _ in range(n))


POSITIVE = {
    'email':  lambda r: f"Contact {r.choice(['jane','arun','mira'])}.{r.choice(['doe','patel','ross'])}@example.com for the file.",
    'card':   lambda r: f"Payment taken on card {luhn_number(r)}.",
    'nhs':    lambda r: r.choice([f"NHS number {nhs_number(r)} recorded at triage.",
                                  f"Recorded at triage as {_grouped(nhs_number(r))} on the day."]),
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
    # five kinds that shipped with a pattern and no positive to measure it. `passport`, `licence`
    # and `medical` are the three the real corpus caught firing on cue words alone.
    'passport':lambda r: r.choice([
        f"Passport number {r.randrange(10**8, 10**9)} was checked at the gate.",
        f"Passport No. {r.choice('XKJ')}{r.randrange(10**6, 10**7)} expires in June.",
    ]),
    'licence':lambda r: r.choice([
        f"Driver's licence {_rand(r, 5, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{r.randrange(10**5, 10**6)}"
        f"SM9IJ is on file.",
        f"Driver licence no D{r.randrange(10**6, 10**7)} recorded at the desk.",
    ]),
    'sortcode':lambda r: f"Sort code {r.randrange(10,99)}-{r.randrange(10,99)}-{r.randrange(10,99)} "
                         f"was given for the transfer.",
    'secret': lambda r: r.choice([
        f"Key sk-{_rand(r, 20)} was committed to the repo.",
        f"Token ghp_{_rand(r, 36)} leaked in the log.",
        f"AKIA{_rand(r, 16, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')} was rotated on Friday.",
    ]),
    'medical':lambda r: r.choice([
        f"Medical record number {r.randrange(10**6, 10**7)} was pulled.",
        f"Patient ID {r.randrange(10**4, 10**5)} is on the ward list.",
        f"MRN {r.randrange(1000,9999)}-{r.randrange(10,99)} in the chart.",
    ]),
}

#: `ip` is the one pattern that is reportable and does not gate, so it cannot sit in `POSITIVE`
#: without counting as a miss on `has_pii`. Measured on its own in `run`.
REPORTABLE = {
    'ip': lambda r: f"The request came from 203.0.113.{r.randrange(1,254)} at 09:12.",
}

#: Things that look like identity and are not, grouped so a residual false positive has a name.
#: The `standard`, `link` and `cued` groups carry *valid* checksums: they are the whole point.
NEGATIVE = {
    # a bare number in front of a common noun is not a street line, and this is where a loose
    # address pattern does its damage: every numbered heading in every report would fire
    'heading': [
        lambda r: f"Chapter {r.randrange(1,9)} Court decisions are summarised below.",
        lambda r: f"Table {r.randrange(1,9)} Road traffic figures for the quarter.",
        lambda r: f"Figure {r.randrange(1,9)} Way of working, as adopted.",
        lambda r: f"Section {r.randrange(1,99)} Place of performance is unchanged.",
        lambda r: f"Item {r.randrange(1,99)} Drive belt replaced under warranty.",
    ],
    'refnum': [
        lambda r: f"ISBN 978-{r.randrange(0,9)}-{r.randrange(10000,99999)}-{r.randrange(100,999)}-{r.randrange(0,9)} is out of print.",
        lambda r: f"Build 20240{r.randrange(1,9)}{r.randrange(10,28)}.{r.randrange(1000,9999)} passed all gates.",
        lambda r: f"The run took {r.randrange(1000,9999)} seconds over {r.randrange(100,999)} shards.",
        lambda r: f"Version 4.{r.randrange(0,20)}.{r.randrange(0,20)} deprecates the old endpoint.",
        lambda r: f"Between {r.randrange(1900,2000)} and {r.randrange(2001,2024)} the figure trebled.",
        lambda r: f"Grid reference {r.randrange(100000,999999)} {r.randrange(100000,999999)} on the survey.",
        lambda r: f"Invoice total 1{r.randrange(100000,999999)} rupees before tax.",
        lambda r: f"Unix timestamp {r.randrange(1600000000,1800000000)} marks the cutover.",
    ],
    # A two-letter word before five digits is a US zip only if the letters are a state, and only
    # if they are capitals. Case-folded, `as 12345` and `no 90210` are somebody's address, and a
    # street suffix after a lowercase common noun is a sentence rather than a delivery.
    'zipish': [
        lambda r: f"As {r.randrange(10000,99999)} units shipped, the line was retired.",
        lambda r: f"No {r.randrange(10000,99999)} records matched the query.",
        lambda r: f"Ref ab {r.randrange(10000,99999)} cleared without comment.",
        lambda r: f"Delivered to {r.randrange(1,99)} the big street party volunteers.",
    ],
    # A standards designation is two capitals and five digits, which is also a state and a ZIP.
    # One spec document is hundreds of these.
    'standard': [
        lambda r: f"EN 60601-{r.randrange(1,9)} applies to medical electrical equipment.",
        lambda r: f"Conformity is assessed against EN {r.randrange(10000,99999)} in full.",
        lambda r: f"BS EN ISO {r.randrange(10000,99999)} supersedes the {r.randrange(1990,2020)} edition.",
        lambda r: f"IEC 6{r.randrange(1000,9999)} and ISO 134{r.randrange(10,99)} both apply here.",
        lambda r: f"ASTM D{r.randrange(1000,9999)} is the reference test method.",
        lambda r: f"DIN {r.randrange(10000,99999)} is cited in annex B.",
    ],
    # Every digit run in a link is a path segment or a query value. These carry real checksums.
    'link': [
        lambda r: f"See https://example.atlassian.net/wiki/spaces/TA/pages/{nhs_number(r)} for the spec.",
        lambda r: f"Tracked at https://tracker.example.com/order/{luhn_number(r)}?tab=all today.",
        lambda r: f"Mirror is https://cdn.example.org/blob/{nhs_number(r)}/{luhn_number(r)}.bin now.",
        lambda r: f"Docs live at www.example.com/kb/{nhs_number(r)} and nowhere else.",
    ],
    # Long digit runs with no cue either way, drawn at random: about one in ten passes Luhn and
    # one in eleven passes mod-11. This is the class the checksums are for, and the only one left
    # where they are the last line.
    'bare': [
        lambda r: f"Readings of {r.randrange(10**15, 10**16)} and {r.randrange(10**14, 10**15)} were logged.",
        lambda r: f"The export shows {r.randrange(10**15, 10**16)} twice and nothing else.",
        lambda r: f"{r.randrange(10**12, 10**13)} appears in the header of every page.",
        lambda r: f"Totals reconciled at {r.randrange(10**9, 10**10)} against the ledger.",
        lambda r: f"The counter reached {r.randrange(10**9, 10**10)} before the reset.",
    ],
    # Valid checksums under a word that says the number is a reference. Nothing but the left
    # context separates these from the positives.
    'cued': [
        lambda r: f"Order {luhn_number(r)} shipped on Tuesday.",
        lambda r: f"Part {nhs_number(r)} supersedes the previous revision.",
        lambda r: f"Transaction ref {luhn_number(r)} cleared at 14:02.",
        lambda r: f"Serial {nhs_number(r)} was returned under warranty.",
        lambda r: f"Docket {nhs_number(r)} was filed with the registry.",
        lambda r: f"Page {nhs_number(r)} of the export was truncated.",
    ],
    # A space is the thousands separator in most of Europe, so every large budget line carries a
    # `0`-leading group of three, which is the UK trunk-number pattern. Every one of these has one
    # by construction. Nine of the fifteen real false positives were this.
    'money': [
        lambda r: f"an amount of up to EUR {r.randrange(1,999)} 000 000 000 as referred to in point (b).",
        lambda r: f"EUR {r.randrange(1,20)} 0{r.randrange(10,99)} {r.randrange(100,999)} 000 in current prices.",
        lambda r: f"a ceiling of EUR {r.randrange(1,9)} 000 000 000 shall not be exceeded.",
        lambda r: f"The budget is set at {r.randrange(1,9)} {r.randrange(100,999)} 000 000 EUR over seven years.",
        lambda r: f"Total assets of {r.randrange(10,99)} 0{r.randrange(10,99)} {r.randrange(100,999)} 000 were reported.",
    ],
    # US legal citation, from 45 CFR 164: a different set of digit shapes from EU numbering, and
    # the reason the corpus is not all one jurisdiction.
    'citation': [
        lambda r: f"42 U.S.C. {r.randrange(1000,9999)}(a) and 42 U.S.C. 1320d-1320d-9 apply.",
        lambda r: f"sec. {r.randrange(100,999)}, Pub. L. {r.randrange(100,119)}-{r.randrange(1,999)}, "
                  f"110 Stat. {r.randrange(1000,9999)}-{r.randrange(1000,9999)}.",
        lambda r: f"{r.randrange(60,90)} FR {r.randrange(10000,99999)}, Dec. {r.randrange(1,28)}, "
                  f"{r.randrange(1990,2024)}, unless otherwise noted.",
        lambda r: f"secs. {r.randrange(10000,19999)}-{r.randrange(10000,19999)}, Pub. L. 111-5, "
                  f"123 Stat. {r.randrange(100,999)}-{r.randrange(100,999)}.",
        lambda r: f"See {r.randrange(60,90)} FR {r.randrange(1000,9999)}, Jan. {r.randrange(1,28)}, "
                  f"{r.randrange(1990,2024)}, as amended.",
    ],
    # EU act numbering, which is what a regulation is mostly made of.
    'celex': [
        lambda r: f"Council Directive {r.randrange(70,99)}/{r.randrange(1,99)}/EEC of 5 April 1993 on unfair terms.",
        lambda r: f"Regulation (EU) 20{r.randrange(10,24)}/{r.randrange(100,999)} of the European Parliament.",
        lambda r: f"OJ L {r.randrange(100,999)}, {r.randrange(1,28)}.{r.randrange(1,12)}.20{r.randrange(10,24)}, "
                  f"p. {r.randrange(1,99)}.",
        lambda r: f"as amended by Directive 20{r.randrange(10,24)}/{r.randrange(10,99)}/EU of 25 October 2011.",
        lambda r: f"Article {r.randrange(1,99)}({r.randrange(1,9)}), point (b), of Regulation (EU) "
                  f"2018/{r.randrange(1000,9999)} applies.",
    ],
    # A document about identifiers is not a document containing one. This is what a privacy notice,
    # a data schema and a data protection act all look like, and the class that broke `medical`,
    # `passport` and `licence`, none of which required a value after the cue word.
    'about': [
        lambda r: "Medical record numbers; Health plan beneficiary numbers; Account numbers.",
        lambda r: "the place entered as such in a passport, identity card or other document",
        lambda r: "driver's licence details are verified at the counter before collection",
        lambda r: "Social security numbers and account numbers are personal data.",
        lambda r: "The patient name field is mandatory and the patient id field is optional.",
        lambda r: "A telephone number, an email address or a postal address may identify a person.",
        lambda r: f"An account number shall be recorded for each of the {r.randrange(2,40)} transfers.",
        lambda r: "the sort code and account number of the payee are held by the bank",
    ],
}

FILLER = ("The committee met on Tuesday and reviewed the outstanding items. "
          "Delivery is scheduled for the following quarter subject to approval. "
          "No further action was recorded against this matter. ")


def corpus(n=720, seed=0):
    "`[(text, kinds_present, negative_class)]`: half carrying real identity, half lookalikes."
    rng, out = random.Random(seed), []
    kinds = list(POSITIVE)
    for i in range(n // 2):
        k = kinds[i % len(kinds)]
        out.append((FILLER + POSITIVE[k](rng) + ' ' + FILLER, {k}, None))
    flat = [(g, f) for g, fs in NEGATIVE.items() for f in fs]
    for i in range(n - n // 2):
        g, f = flat[i % len(flat)]
        out.append((FILLER + f(rng) + ' ' + FILLER, set(), g))
    return out


def _sub(P, kind, old, new):
    "Swap one fragment of a live pattern, so an ablation tracks edits to `PATTERNS` instead of a copy."
    p = P.PATTERNS[kind][0]
    assert old in p, (kind, old)
    P._COMPILED[kind] = (re.compile(p.replace(old, new), 0 if kind in P.CASED else re.I),
                         P._COMPILED[kind][1])


#: Every guard in `pii.py`, and how to take it away. Each row of the ablation tables in RESULTS.md
#: is one of these; nothing in those tables was measured by hand.
GUARDS = {
    'every checksum':     lambda P: P._COMPILED.update({k: (rx, None) for k, (rx, _) in P._COMPILED.items()}),
    'US_STATES ZIP':      lambda P: _sub(P, 'address', P._ZIP, r'\b[A-Z]{2} \d{5}(?:-\d{4})?\b'),
    'street name':        lambda P: _sub(P, 'address', r"[ ,]+(?:[A-Z][A-Za-z.\'-]+[ ,]+){1,3}",
                                                       r"[ ,]+(?:[A-Z][A-Za-z.\'-]+[ ,]+){0,3}"),
    'DESIGNATOR':         lambda P: setattr(P, '_designated', lambda s, i: False),
    'URLISH':             lambda P: setattr(P, 'URLISH', re.compile(r'(?!x)x')),
    'nhs groups or name': lambda P: _sub(P, 'nhs', P.PATTERNS['nhs'][0], r'\b\d{3}[ -]?\d{3}[ -]?\d{4}\b'),
    'card issuer digit':  lambda P: _sub(P, 'card', r'\b[2-6](?:[ -]?\d){12,18}\b',
                                                    r'\b\d(?:[ -]?\d){12,18}\b'),
    # the three the real regulatory corpus asked for (evals/pii_real.py)
    'grouped-number':     lambda P: setattr(P, '_grouped', lambda s, i, j: False),
    'passport value':     lambda P: _sub(P, 'passport', r'(?=[A-Z0-9]{0,8}\d)', ''),
    'licence value':      lambda P: _sub(P, 'licence', r'(?=[A-Z0-9]{0,19}\d)', ''),
    'medical value':      lambda P: _sub(P, 'medical', r'\W{0,6}(?=[A-Za-z0-9-]{0,19}\d)[A-Za-z0-9-]{1,20}\b', ''),
}


@contextmanager
def without(*guards):
    "Run the block with those guards switched off. No arguments runs the detector as shipped."
    from vishalakshi import pii as P
    saved = dict(P._COMPILED), P._designated, P._grouped, P.URLISH
    try:
        for g in guards: GUARDS[g](P)
        yield
    finally:
        P._COMPILED.clear(); P._COMPILED.update(saved[0])
        P._designated, P._grouped, P.URLISH = saved[1:]


def score(n=720, seed=0):
    "`(tp, fp, fn, tn, recall by kind, false positives by lookalike class)` over one corpus."
    from vishalakshi import pii as P
    tp = fp = fn = tn = 0
    per, by_class = {}, {}
    for text, want, neg in corpus(n, seed):
        got = P.pii_report(text).has_pii
        if want:
            k = next(iter(want))
            d = per.setdefault(k, [0, 0]); d[0 if got else 1] += 1
            tp, fn = tp + int(got), fn + int(not got)
        else:
            d = by_class.setdefault(neg, [0, 0]); d[0 if got else 1] += 1
            fp, tn = fp + int(got), tn + int(not got)
    return tp, fp, fn, tn, per, by_class


def ablate(n=720, seeds=8):
    """Precision with each guard removed on its own, and which lookalike group comes back.

    Over `seeds` draws, because the residual false positive is a random checksum collision and one
    draw of it says nothing: `bare` is 0/30 on seed 0 and 3/30 on seed 5."""
    print(f'\neach guard removed on its own, everything else in place, {seeds} draws of {n}:')
    print(f'  {"guard removed":<22} {"precision":>9} {"recall":>7} {"false positives":>16}   comes back')
    for g in (None, *GUARDS):
        tot, back = [0, 0, 0, 0], {}
        for s in range(seeds):
            with without(*([] if g is None else [g])): tp, fp, fn, tn, _, by_class = score(n, s)
            tot = [a+b for a, b in zip(tot, (tp, fp, fn, tn))]
            for k, (h, m) in by_class.items():
                d = back.setdefault(k, [0, 0]); d[0] += h; d[1] += h+m
        tp, fp, fn, tn = tot
        comes = ' '.join(f'{k} {h}/{t}' for k, (h, t) in sorted(back.items()) if h)
        print(f'  {g or "- (as shipped)":<22} {tp/(tp+fp) if tp+fp else 0:>9.3f} '
              f'{tp/(tp+fn) if tp+fn else 0:>7.3f} {f"{fp}/{tn+fp}":>16}   {comes}')


def run(n=720, seed=0, do_ablate=False):
    from vishalakshi import pii as P

    print(f'{n} documents, half carrying identity and half carrying lookalikes\n')
    rows = []
    for label, v in (('with checksums', True), ('regex only', False)):
        with without(*([] if v else ['every checksum'])): tp, fp, fn, tn, per, by_class = score(n, seed)
        prec = tp/(tp+fp) if tp+fp else 0.0
        rec = tp/(tp+fn) if tp+fn else 0.0
        f1 = 2*prec*rec/(prec+rec) if prec+rec else 0.0
        rows.append((label, prec, rec, f1, fp, tn+fp, per, by_class))
        print(f'{label:<16} precision {prec:.3f}  recall {rec:.3f}  F1 {f1:.3f}  '
              f'false positives {fp}/{tn+fp}')

    print(f'\nchecksums change the false-positive rate from {rows[1][4]}/{rows[1][5]} to '
          f'{rows[0][4]}/{rows[0][5]} of the lookalike documents')
    print(f'\nrecall by kind (with checksums):')
    for k, (hit, miss) in sorted(rows[0][6].items()):
        print(f'  {k:<10} {hit}/{hit+miss}  {hit/(hit+miss):.2f}')
    print(f'\nfalse positives by lookalike class (with checksums):')
    for k, (hit, miss) in sorted(rows[0][7].items()):
        print(f'  {k:<10} {hit}/{hit+miss}  {hit/(hit+miss):.2f}')

    rng = random.Random(seed + 2)
    for k, f in REPORTABLE.items():
        r = [P.pii_report(FILLER + f(rng) + ' ' + FILLER) for _ in range(20)]
        print(f'\n{k} is reportable and does not gate: found in {sum(k in x.kinds for x in r)}/20, '
              f'has_pii in {sum(x.has_pii for x in r)}/20')

    # The name pass is opt-in, so the number that decides whether to switch it on is not its
    # recall on names: it is how often it invents one in ordinary prose.
    neg = [t for t, want, _ in corpus(n, seed) if not want]
    spurious = sum(bool(P.pii_report(t, ner=True).kinds.get('person')) for t in neg)
    print(f'\nner=True on the {len(neg)} lookalike documents: {spurious} gained a spurious person')
    for t in ('Dr Charles Babbage signed it.', 'Ada Lovelace signed it.'):
        print(f'  {t:32} -> {P.pii_report(t, ner=True).identifying or "nothing"}')
    if do_ablate: ablate(n)
    return rows


if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    p = argparse.ArgumentParser()
    p.add_argument('--ablate', action='store_true', help='remove each guard on its own')
    p.add_argument('--n', type=int, default=720, help='documents, half of them lookalikes')
    p.add_argument('--seed', type=int, default=0)
    a = p.parse_args()
    run(n=a.n, seed=a.seed, do_ablate=a.ablate)
