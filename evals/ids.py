"""Generators for the regional identifiers, one per validator in `vishalakshi.pii`.

These make fake identities that pass a real checksum, which is what a recall measurement needs.
Every generator is paired with the library's validator in `check()` below, so a corpus can never
quietly drift away from what the detector accepts.

    python -m evals.ids
"""
import re, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vishalakshi.pii import (_VD, _VP, _VINV, _luhn_ds, _NRIC_T, _NRIC_OFF, _DNI_L, _CF_ODD,
                             _CF_EVEN, _B36, _NINO_BAD)


def verhoeff_digit(ds):
    "The check digit that makes `ds` pass Verhoeff. Generating, so it lives here and not in the library."
    c = 0
    for i, d in enumerate(reversed(ds)): c = _VD[c][_VP[(i + 1) % 8][d]]
    return _VINV[c]

def gen_aadhaar(r):
    ds = [r.randrange(2, 10)] + [r.randrange(10) for _ in range(10)]
    return ''.join(map(str, ds + [verhoeff_digit(ds)]))

def gen_tfn(r):
    while True:
        ds = [r.randrange(10) for _ in range(8)]
        tot = sum(d*w for d, w in zip(ds, (1,4,3,7,5,8,6,9)))
        for last in range(10):
            if (tot + last*10) % 11 == 0: return ''.join(map(str, ds + [last]))
        continue

def gen_abn(r):
    W = (10,1,3,5,7,9,11,13,15,17,19)
    while True:
        ds = [r.randrange(1, 10)] + [r.randrange(10) for _ in range(8)]
        base = sum(d*w for d, w in zip([ds[0]-1] + ds[1:], W))
        for a in range(10):
            for b in range(10):
                if (base + a*W[9] + b*W[10]) % 89 == 0:
                    return ''.join(map(str, ds + [a, b]))

def gen_medicare(r):
    ds = [r.randrange(2, 7)] + [r.randrange(10) for _ in range(7)]
    chk = sum(d*w for d, w in zip(ds, (1,3,7,9,1,3,7,9))) % 10
    return ''.join(map(str, ds + [chk, r.randrange(1, 10)]))

def gen_nric(r):
    p = r.choice('STFG')
    ds = ''.join(str(r.randrange(10)) for _ in range(7))
    tot = (sum(int(d)*w for d, w in zip(ds, (2,7,6,5,4,3,2))) + _NRIC_OFF[p]) % 11
    return f'{p}{ds}{_NRIC_T[p][tot]}'

def gen_thai_id(r):
    ds = [r.randrange(1, 9)] + [r.randrange(10) for _ in range(11)]
    return ''.join(map(str, ds + [(11 - sum(d*(13-i) for i, d in enumerate(ds)) % 11) % 10]))

def gen_bsn(r):
    while True:
        ds = [r.randrange(1, 10)] + [r.randrange(10) for _ in range(7)]
        tot = sum(d*w for d, w in zip(ds, (9,8,7,6,5,4,3,2)))
        for last in range(10):
            if (tot - last) % 11 == 0: return ''.join(map(str, ds + [last]))

def gen_nir(r):
    body = f'{r.choice("12")}{r.randrange(30,99):02d}{r.randrange(1,12):02d}{r.randrange(1,95):02d}{r.randrange(1,999):03d}{r.randrange(1,999):03d}'
    return body + f'{97 - int(body) % 97:02d}'

def gen_dni(r):
    n = r.randrange(10**7, 10**8)
    return f'{n:08d}{_DNI_L[n % 23]}'

def gen_nie(r):
    p, n = r.choice('XYZ'), r.randrange(10**6, 10**7)
    return f'{p}{n:07d}' + _DNI_L[int(f'{"XYZ".index(p)}{n:07d}') % 23]

def gen_cf(r):
    L = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    body = (''.join(r.choice(L) for _ in range(6)) + f'{r.randrange(0,99):02d}' + r.choice('ABCDEHLMPRST')
            + f'{r.randrange(1,28):02d}' + r.choice(L) + f'{r.randrange(100,999)}')
    tot = sum((_CF_ODD if i % 2 == 0 else _CF_EVEN)[c] for i, c in enumerate(body))
    return body + chr(65 + tot % 26)

def gen_pesel(r):
    ds = [r.randrange(10) for _ in range(10)]
    return ''.join(map(str, ds + [(10 - sum(d*w for d, w in zip(ds, (1,3,7,9,1,3,7,9,1,3))) % 10) % 10]))

def gen_personnummer(r):
    # a real birth date, since that is what separates a person from a Swedish company
    ds = ([r.randrange(10), r.randrange(10), 0, 0, 0, 0] + [r.randrange(10) for _ in range(3)])
    ds[2], ds[3] = divmod(r.randrange(1, 13), 10)[::-1] if False else divmod(r.randrange(1, 13), 10)
    ds[4], ds[5] = divmod(r.randrange(1, 29), 10)
    for last in range(10):
        if _luhn_ds(ds + [last]):
            b = ''.join(map(str, ds + [last]))
            return f'{b[:6]}-{b[6:]}'

def gen_fnr(r):
    while True:
        ds = [r.randrange(10) for _ in range(9)]
        k1 = (11 - sum(d*w for d, w in zip(ds, (3,7,6,1,8,9,4,5,2))) % 11)
        if k1 >= 10: continue
        k2 = (11 - sum(d*w for d, w in zip(ds + [k1], (5,4,3,2,7,6,5,4,3,2))) % 11)
        if k2 >= 10: continue
        return ''.join(map(str, ds + [k1, k2]))

def gen_steuerid(r):
    ds = [r.randrange(1, 10)] + [r.randrange(10) for _ in range(9)]
    p = 10
    for d in ds:
        m = (d + p) % 10 or 10
        p = (2*m) % 11
    return ''.join(map(str, ds + [(11 - p) % 10]))

def gen_pan(r):
    L = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    return (''.join(r.choice(L) for _ in range(3)) + r.choice('ABCFGHLJPTKE')
            + r.choice(L) + f'{r.randrange(1000,9999)}' + r.choice(L))

def gen_gstin(r):
    body = f'{r.randrange(1,38):02d}' + gen_pan(r) + str(r.randrange(1, 10)) + 'Z'
    tot = 0
    for i, c in enumerate(body):
        v = _B36.index(c) * (2 if i % 2 else 1)
        tot += v // 36 + v % 36
    return body + _B36[(36 - tot % 36) % 36]

def gen_nino(r):
    while True:
        p = r.choice('ABCEGHJKLMNOPRSTWXYZ') + r.choice('ABCEGHJKLMNPRSTWXYZ')
        if p not in _NINO_BAD: return f'{p}{r.randrange(10**5,10**6):06d}{r.choice("ABCD")}'

def gen_imei(r):
    ds = [r.randrange(10) for _ in range(14)]
    for last in range(10):
        if _luhn_ds(ds + [last]): return ''.join(map(str, ds + [last]))


#: name -> (generator, the library validator it has to satisfy)
def _checks():
    from vishalakshi import pii as P
    return {'aadhaar': (gen_aadhaar, P.aadhaar_ok), 'tfn': (gen_tfn, P.tfn_ok), 'abn': (gen_abn, P.abn_ok),
            'medicare': (gen_medicare, P.medicare_ok), 'nric': (gen_nric, P.nric_ok),
            'thai_id': (gen_thai_id, P.thai_id_ok), 'bsn': (gen_bsn, P.bsn_ok), 'nir': (gen_nir, P.nir_ok),
            'dni': (gen_dni, P.dni_ok), 'nie': (gen_nie, P.dni_ok), 'cf': (gen_cf, P.cf_ok),
            'pesel': (gen_pesel, P.pesel_ok), 'personnummer': (gen_personnummer, P.personnummer_ok),
            'fnr': (gen_fnr, P.fnr_ok), 'steuerid': (gen_steuerid, P.steuerid_ok), 'pan': (gen_pan, P.pan_ok),
            'gstin': (gen_gstin, P.gstin_ok), 'nino': (gen_nino, P.nino_ok), 'imei': (gen_imei, P.imei_ok)}

#: Checked by hand or against the algorithm's own published vector, not against these generators.
#: `2363` is Verhoeff's worked example; `S1234567D` I did the mod-11 by hand; `12345678Z` and
#: `490154203237518` are the canonical DNI and IMEI examples.
KNOWN = [('verhoeff', 'aadhaar_ok', '234567890124', True), ('nric', 'nric_ok', 'S1234567D', True),
         ('nric', 'nric_ok', 'S1234567A', False), ('dni', 'dni_ok', '12345678Z', True),
         ('dni', 'dni_ok', '12345678A', False), ('imei', 'imei_ok', '490154203237518', True),
         ('imei', 'imei_ok', '490154203237519', False)]


def check(n=500, seed=0):
    "Every generator against the library validator, and every validator against a perturbation."
    from vishalakshi import pii as P
    r = random.Random(seed)
    print(f'{"kind":<15}{"generated accepted":>20}{"one digit changed, rejected":>30}')
    for name, (gen, ok) in _checks().items():
        good = sum(ok(gen(r)) for _ in range(n))
        bad = 0
        for _ in range(n):
            s = list(gen(r))
            i = r.choice([j for j, c in enumerate(s) if c.isdigit()])
            s[i] = str((int(s[i]) + r.randrange(1, 10)) % 10)
            bad += not ok(''.join(s))
        note = '   (shape only, no check digit)' if name in ('pan', 'nino') else ''
        print(f'{name:<15}{f"{good}/{n}":>20}{f"{bad}/{n}":>30}{note}')
    print()
    for _, fn, s, want in KNOWN:
        got = getattr(P, fn)(s)
        print(f'  {fn:<14}{s:<18}{"accepted" if got else "rejected":<10}'
              f'{"ok" if got == want else "MISMATCH"}')


if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    check()
