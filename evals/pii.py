"""What do the checksums buy, and what does the detector miss.

`pii.py` says a checksum is what separates a detector from a superstition. That is a claim about a
false-positive rate, so it needs a corpus of things that look like PII and are not: order numbers,
ISBNs, part numbers, timestamps, version strings, long digit runs. The negatives are the whole
experiment. Positives are easy to detect and easy to fake being good at.

Half the negatives are adversarial by construction: the digits carry a *valid* checksum and sit in
a context that says they are not identity. A checksum-passing number under `Order` or inside a URL
is the failure a random corpus finds one time in eleven and a spec document finds on every page.

Measured per kind, per negative class, and again with every validator disabled.

    python -m evals.pii
"""
import sys, random, re
from pathlib import Path

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
}

#: The nineteen regional identifiers, each planted with a real checksum. `evals/ids.py` generates
#: them and checks every generator against the library's own validator.
def _intl_positive():
    from evals import ids
    g = {k: v[0] for k, v in ids._checks().items()}
    return {
        'aadhaar': lambda r: f"Aadhaar {(a := g['aadhaar'](r))[:4]} {a[4:8]} {a[8:]} was linked to the account.",
        'pan':     lambda r: f"PAN {g['pan'](r)} quoted on the return.",
        'gstin':   lambda r: f"GSTIN {g['gstin'](r)} appears on the invoice.",
        'tfn':     lambda r: f"TFN {g['tfn'](r)} was lodged with the ATO.",
        'abn':     lambda r: f"The supplier's ABN is {(a := g['abn'](r))[:2]} {a[2:5]} {a[5:8]} {a[8:]}.",
        'medicare':lambda r: f"Medicare card {(a := g['medicare'](r))[:4]} {a[4:9]} {a[9]} presented at reception.",
        'nric':    lambda r: f"NRIC {g['nric'](r)} on the tenancy agreement.",
        'thai_id': lambda r: f"Thai national ID {(a := g['thai_id'](r))[0]}-{a[1:5]}-{a[5:10]}-{a[10:12]}-{a[12]} recorded.",
        'bsn':     lambda r: f"BSN {g['bsn'](r)} verified against the register.",
        'nir':     lambda r: f"Numero de securite sociale {g['nir'](r)} confirmed by the caisse.",
        'dni':     lambda r: f"DNI {g['dni'](r)} presented at the notary.",
        'nie':     lambda r: f"NIE {g['nie'](r)} shown for the residency application.",
        'cf':      lambda r: f"Codice fiscale {g['cf'](r)} on the contract.",
        'pesel':   lambda r: f"PESEL {g['pesel'](r)} entered into the system.",
        'personnummer': lambda r: f"Personnummer {g['personnummer'](r)} in the patient record.",
        'fnr':     lambda r: f"Fodselsnummer {g['fnr'](r)} registered with Folkeregisteret.",
        'steuerid':lambda r: f"Steuer-IdNr {g['steuerid'](r)} supplied by the employee.",
        'nino':    lambda r: f"National Insurance number {g['nino'](r)} given on the P45.",
        'imei':    lambda r: f"IMEI {g['imei'](r)} was blocked by the carrier.",
    }


#: Lookalikes written *after* the guards were fixed but never used to change them. The provenance is
#: deliberate: `ticket` is the precision-trap list documented in `context_cued.py` in
#: LiquidAI/LFM2.5-Encoder-350M-PII-Detector, `stdnum` and `orgnum` are real numbering standards
#: with their own check digits, `geo` is postal and vehicle coding from the four regions above, and
#: `stdbody` is standards bodies absent from `DESIGNATOR` plus three two-letter codes that are also
#: US states. Reported separately from `NEGATIVE`, because only `NEGATIVE` is in-sample.
HELDOUT = {
    'ticket': [
        lambda r: f"PO#{r.randrange(10**5,10**6)} was raised against the framework agreement.",
        lambda r: f"WO-{r.randrange(1000,9999)} and RMA {r.randrange(10**7,10**8)} are both closed.",
        lambda r: f"JIRA-{r.randrange(1000,9999)} blocks EPIC-{r.randrange(100,999)} this sprint.",
        lambda r: f"INC{r.randrange(10**7,10**8):08d} escalated to CHG{r.randrange(10**7,10**8):08d}.",
        lambda r: f"TICKET-{r.randrange(10**5,10**6)} duplicates GH-{r.randrange(1000,9999)}.",
        lambda r: f"ORD-{r.randrange(10**8,10**9)} shipped against INV-{r.randrange(10**8,10**9)}.",
    ],
    'stdnum': [
        lambda r: f"ISIN US{r.randrange(10**9,10**10)} was delisted last quarter.",
        lambda r: f"LEI 5299{r.randrange(10,99)}T8BM49AURSDO{r.randrange(10,99)} is on the GLEIF register.",
        lambda r: f"CAS {r.randrange(50,9999)}-{r.randrange(10,99)}-{r.randrange(0,9)} is the reference substance.",
        lambda r: f"ORCID 0000-000{r.randrange(1,3)}-{r.randrange(1000,9999)}-{r.randrange(1000,9999)} on the preprint.",
        lambda r: f"GTIN {r.randrange(10**12,10**13)} scanned at the till.",
        lambda r: f"ISSN {r.randrange(1000,9999)}-{r.randrange(1000,9999)} ceased publication.",
        lambda r: f"BIC DEUTDEFF{r.randrange(100,999)} routes the payment.",
        lambda r: f"MAC 00:1B:44:{r.randrange(10,99)}:3A:B{r.randrange(0,9)} was seen on the segment.",
        lambda r: f"UUID {r.randrange(10**7,10**8):08x}-1234-5678-9abc-{r.randrange(10**11,10**12):012x} in the log.",
        lambda r: f"Coordinates 51.{r.randrange(1000,9999)}, -0.{r.randrange(1000,9999)} put it in London.",
        lambda r: f"ICD-10 C{r.randrange(10,99)}.{r.randrange(0,9)} and ATC A10BA0{r.randrange(1,9)} were coded.",
        lambda r: f"Epoch {r.randrange(10**12,10**13)} ms is when the run started.",
    ],
    'orgnum': [
        lambda r: f"Organisationsnummer {r.randrange(100000,999999)}-{r.randrange(1000,9999)} for the Swedish entity.",
        lambda r: f"SIRET {r.randrange(10**13,10**14)} and SIREN {r.randrange(10**8,10**9)} for the French branch.",
        lambda r: f"Partita IVA {r.randrange(10**10,10**11)} for the Italian subsidiary.",
        lambda r: f"ACN {r.randrange(100,999)} {r.randrange(100,999)} {r.randrange(100,999)} for the Australian company.",
        lambda r: f"Organisasjonsnummer {r.randrange(10**8,10**9)} for the Norwegian branch.",
        lambda r: f"NIP {r.randrange(10**9,10**10)} for the Polish supplier.",
        lambda r: f"CIF A{r.randrange(10**7,10**8)} for the Spanish company.",
        lambda r: f"NPWP {r.randrange(10**14,10**15)} for the Indonesian entity.",
        lambda r: f"KvK {r.randrange(10**7,10**8)} for the Dutch B.V.",
    ],
    'geo': [
        lambda r: f"The Bengaluru office PIN is {r.randrange(560001,560100)}, near the ring road.",
        lambda r: f"The Sydney site is NSW {r.randrange(2000,2100)} and the Melbourne one VIC {r.randrange(3000,3100)}.",
        lambda r: f"Singapore {r.randrange(100000,999999)} is the postal code for the tower.",
        lambda r: f"Bangkok {r.randrange(10110,10999)} covers the district.",
        lambda r: f"Berlin {r.randrange(10115,10999)} and Paris {r.randrange(75001,75020)} were both surveyed.",
        lambda r: f"Amsterdam {r.randrange(1012,1099)} AB is the delivery postcode.",
        lambda r: f"Warszawa {r.randrange(0,99):02d}-{r.randrange(100,999)} is the registered postcode.",
        lambda r: f"Vehicle KA {r.randrange(1,60):02d} AB {r.randrange(1000,9999)} was recorded at the gate.",
    ],
    'stdbody': [
        lambda r: f"AS/NZS {r.randrange(1000,9999)} governs the installation.",
        lambda r: f"JIS B {r.randrange(1000,9999)} and GB/T {r.randrange(10000,99999)} were both cited.",
        lambda r: f"IS {r.randrange(100,999)} is the Indian standard for the mix.",
        lambda r: f"NEN {r.randrange(1000,9999)} and SS {r.randrange(100,999)} apply in those markets.",
        lambda r: f"TIS {r.randrange(10,99)} and SNI 06-{r.randrange(1000,9999)} cover the region.",
        lambda r: f"NF C {r.randrange(10,99)}-{r.randrange(100,999)} and UNE {r.randrange(10000,99999)} are equivalent.",
        # two-letter codes that are also US states, which is the trap the ZIP list cannot see
        lambda r: f"MS {r.randrange(10000,99999)} is the military standard referenced.",
        lambda r: f"AL {r.randrange(10000,99999)} and IN {r.randrange(10000,99999)} are internal designations.",
    ],
}

#: A second held-out set, written after `HELDOUT` had already been used to fix three defects and
#: was therefore spent. Nothing here was looked at before the run reported in `evals/RESULTS.md`,
#: and the defects it found are recorded there as limits rather than quietly fixed, because fixing
#: against it would spend it too. Families chosen for collision with the shipped checksums: SNOMED
#: CT is Verhoeff like Aadhaar, ICCID is Luhn like a card, IMO and VIN are mod-11, UK UTR is ten
#: digits like an NHS number.
HELDOUT2 = {
    'logistics': [
        lambda r: f"Container MSCU{r.randrange(10**6,10**7)} cleared customs on the 4th.",
        lambda r: f"Air waybill {r.randrange(100,999)}-{r.randrange(10**7,10**8)} covers the shipment.",
        lambda r: f"IMO {r.randrange(9000000,9999999)} is the vessel on the bill of lading.",
        lambda r: f"MMSI {r.randrange(200000000,799999999)} was broadcasting all night.",
        lambda r: f"NATO stock number {r.randrange(1000,9999)}-{r.randrange(10,99)}-{r.randrange(100,999)}-{r.randrange(1000,9999)} ordered.",
    ],
    'telecom': [
        lambda r: f"ICCID 8944{r.randrange(10**15,10**16)} was provisioned on the new SIM.",
        lambda r: f"IMSI {r.randrange(10**14,10**15)} appeared on the roaming report.",
        lambda r: f"ASN {r.randrange(1000,65000)} announced the prefix at {r.randrange(10,23)}:00.",
        lambda r: f"OUI 3C:5A:B4 and channel {r.randrange(1,140)} were both wrong.",
    ],
    'finance': [
        lambda r: f"CUSIP 03783{r.randrange(1000,9999)} and SEDOL 2046{r.randrange(100,999)} both resolve.",
        lambda r: f"ABA routing {r.randrange(10**8,10**9)} for the correspondent bank.",
        lambda r: f"IFSC SBIN000{r.randrange(1000,9999)} for the Indian branch transfer.",
        lambda r: f"BSB {r.randrange(10,99)}-{r.randrange(100,999)} for the Australian account.",
        lambda r: f"DUNS {r.randrange(10**8,10**9)} is on the vendor record.",
    ],
    'health': [
        lambda r: f"SNOMED CT {r.randrange(10**11,10**12)} codes the finding.",
        lambda r: f"NDC {r.randrange(10000,99999)}-{r.randrange(100,999)}-{r.randrange(10,99)} was dispensed.",
        lambda r: f"ICD-11 {r.choice('ABCDE')}{r.randrange(10,99)}.{r.randrange(0,9)} replaced the old code.",
        lambda r: f"ATC A0{r.randrange(1,9)}BA0{r.randrange(1,9)} is the classification.",
    ],
    'vehicle': [
        lambda r: f"VIN 1HGCM82633A{r.randrange(100000,999999)} matches the registration.",
        lambda r: f"Tail number VH-{r.choice('ABCDEFG')}{r.choice('ABCDEFG')}{r.choice('ABCDEFG')} was on the tarmac.",
        lambda r: f"Engine {r.randrange(10**9,10**10)} and chassis {r.randrange(10**9,10**10)} were both stamped.",
    ],
    'govnum': [
        lambda r: f"UTR {r.randrange(10**9,10**10)} was quoted on the self assessment.",
        lambda r: f"Companies House {r.randrange(10**7,10**8)} lists the same director.",
        lambda r: f"EORI GB{r.randrange(10**10,10**11)} for the import declaration.",
        lambda r: f"URN {r.randrange(100000,999999)} identifies the school in the return.",
    ],
    'academic': [
        lambda r: f"ISBN-13 978{r.randrange(10**9,10**10)} is the second edition.",
        lambda r: f"arXiv 24{r.randrange(1,12):02d}.{r.randrange(10000,99999)} was withdrawn.",
        lambda r: f"LCCN {r.randrange(1900,2020)}{r.randrange(100000,999999)} in the catalogue.",
    ],
    'timeish': [
        lambda r: f"Modified Julian Date {r.randrange(50000,60999)} is the epoch used.",
        lambda r: f"Week {r.randrange(2020,2025)}-W{r.randrange(1,52):02d} closed the period.",
        lambda r: f"The window was {r.randrange(10**9,10**10)} to {r.randrange(10**9,10**10)} in nanoseconds.",
    ],
}

FILLER = ("The committee met on Tuesday and reviewed the outstanding items. "
          "Delivery is scheduled for the following quarter subject to approval. "
          "No further action was recorded against this matter. ")


def corpus(n=480, seed=0, pos=None, neg=None):
    "`[(text, kinds_present, negative_class)]`: half carrying real identity, half lookalikes."
    rng, out = random.Random(seed), []
    pos, neg = pos if pos is not None else POSITIVE, neg if neg is not None else NEGATIVE
    kinds = list(pos)
    for i in range(n // 2):
        k = kinds[i % len(kinds)]
        out.append((FILLER + pos[k](rng) + ' ' + FILLER, {k}, None))
    flat = [(g, f) for g, fs in neg.items() for f in fs]
    for i in range(n - n // 2):
        g, f = flat[i % len(flat)]
        out.append((FILLER + f(rng) + ' ' + FILLER, set(), g))
    return out


def intl_corpus(n=480, seed=1):
    "The regional identifiers against the held-out lookalikes, which is where they can go wrong."
    return corpus(n, seed, pos=_intl_positive(), neg=HELDOUT)


def heldout_corpus(n=480, seed=2):
    "The shipped kinds against `HELDOUT`, which has since been spent on three fixes."
    return corpus(n, seed, neg=HELDOUT)


def heldout2_corpus(n=480, seed=3, intl=False):
    "`HELDOUT2`, run once. The only out-of-sample precision number in `evals/RESULTS.md`."
    return corpus(n, seed, pos=_intl_positive() if intl else None, neg=HELDOUT2)


def _score(report, docs):
    "precision/recall/F1 over `[(text, kinds, class)]`, plus recall per kind and fp per class."
    tp = fp = fn = tn = 0
    per, by_class = {}, {}
    for text, want, neg in docs:
        got = report(text)
        if want:
            k = next(iter(want))
            d = per.setdefault(k, [0, 0]); d[0 if got else 1] += 1
            tp, fn = tp + int(got), fn + int(not got)
        else:
            d = by_class.setdefault(neg, [0, 0]); d[0 if got else 1] += 1
            fp, tn = fp + int(got), tn + int(not got)
    prec = tp/(tp+fp) if tp+fp else 0.0
    rec = tp/(tp+fn) if tp+fn else 0.0
    return dict(prec=prec, rec=rec, f1=2*prec*rec/(prec+rec) if prec+rec else 0.0,
                fp=fp, n_neg=tn+fp, per=per, by_class=by_class)


def _row(label, s):
    print(f'{label:<34} precision {s["prec"]:.3f}  recall {s["rec"]:.3f}  F1 {s["f1"]:.3f}  '
          f'false positives {s["fp"]}/{s["n_neg"]}')


def _by_class(s, indent='  '):
    fired = {k: v for k, v in sorted(s['by_class'].items()) if v[0]}
    print(f'{indent}false positives by class: '
          + (', '.join(f'{k} {v[0]}/{v[0]+v[1]}' for k, v in fired.items()) if fired else 'none'))
    gaps = {k: v for k, v in sorted(s['per'].items()) if v[1]}
    if gaps: print(f'{indent}recall gaps: ' + ', '.join(f'{k} {v[0]}/{v[0]+v[1]}' for k, v in gaps.items()))


def run(n=480, seed=0):
    import rahasya as P
    rep = lambda t: P.pii_report(t).has_pii

    print(f'=== 1. the tuned corpus, {n} documents. IN-SAMPLE: these lookalikes were written while')
    print('       the guards were being fixed, so this precision is the optimistic one.\n')
    rows = []
    for label, v in (('with checksums', True), ('regex only', False)):
        saved = dict(P._COMPILED)
        if not v: P._COMPILED.update({k: (rx, None) for k, (rx, _) in saved.items()})
        try: sc = _score(rep, corpus(n, seed))
        finally: P._COMPILED.clear(); P._COMPILED.update(saved)
        rows.append(sc); _row(label, sc)
    _by_class(rows[0])
    print(f'\n  checksums move the false-positive rate from {rows[1]["fp"]}/{rows[1]["n_neg"]} '
          f'to {rows[0]["fp"]}/{rows[0]["n_neg"]}')

    print('\n=== 2. HELDOUT, spent. Written after the guards, then used to fix three defects, so')
    print('       this is in-sample now too. Kept because the three defects are the point.\n')
    sc = _score(rep, heldout_corpus(n, seed + 2)); _row('shipped kinds', sc); _by_class(sc)
    sc = _score(rep, intl_corpus(int(n * 1.6), seed + 1)); _row('regional kinds', sc); _by_class(sc)

    print('\n=== 3. HELDOUT2, run once and never fixed against. The only OUT-OF-SAMPLE number here.\n')
    sc = _score(rep, heldout2_corpus(n, seed + 3)); _row('shipped kinds', sc); _by_class(sc)
    sc = _score(rep, heldout2_corpus(int(n * 1.6), seed + 3, intl=True)); _row('regional kinds', sc); _by_class(sc)

    print('\n=== 4. what each guard is worth, removed one at a time on the tuned corpus\n')
    for label, patch in _ablations(P):
        saved_d, saved_u, saved_c = P.DESIGNATOR, P.URLISH, dict(P._COMPILED)
        try:
            patch()
            _row(label, _score(rep, corpus(n, seed)))
        finally:
            P.DESIGNATOR, P.URLISH = saved_d, saved_u
            P._COMPILED.clear(); P._COMPILED.update(saved_c)

    print('\n=== 5. names, which no pattern finds\n')
    neg = [t for t, w, _ in corpus(n, seed) if not w]
    print(f'  ner=True invented a person in {sum(bool(P.pii_report(t, ner=True).kinds.get("person")) for t in neg)}'
          f' of {len(neg)} lookalike documents')
    for t in ('Dr Charles Babbage signed it.', 'Ada Lovelace signed it.'):
        print(f'    {t:32} -> {P.pii_report(t, ner=True).identifying or "nothing"}')
    return rows


def _ablations(P):
    "Each guard switched off on its own, so the table in RESULTS.md is reproducible."
    import re as _re
    never = _re.compile(r'(?!x)x')
    addr = P.PATTERNS['address'][0]
    loose_zip = addr.split(r'|\b[A-Z][a-z]+')[0] + r'|\b[A-Z]{2} \d{5}(?:-\d{4})?\b'
    no_city = addr.replace(r"\b[A-Z][a-z]+(?:[ ][A-Z][a-z]+){0,2},?[ ](?:", r"\b(?:")
    def _set(kind, pat, ok): P._COMPILED[kind] = (_re.compile(pat, 0 if kind in P.CASED else _re.I), ok)
    return [
        ('  as shipped', lambda: None),
        ('  without the US_STATES list', lambda: _set('address', loose_zip, None)),
        ('  without the city before a ZIP', lambda: _set('address', no_city, None)),
        ('  without the DESIGNATOR guard', lambda: setattr(P, 'DESIGNATOR', never)),
        ('  without the URL guard', lambda: setattr(P, 'URLISH', never)),
        ('  nhs on any 10-digit run', lambda: _set('nhs', r'\b\d{3}[ -]?\d{3}[ -]?\d{4}\b', P._nhs_ok)),
        ('  card on any 13-19 digit run', lambda: _set('card', r'\b(?:\d[ -]?){13,19}\b', P.luhn)),
    ]


if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    run()
