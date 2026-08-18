"""Do the learned PII detectors beat the patterns, and are they worth the weights.

The patterns are cheap, auditable and at 1.000 out-of-sample precision on `evals/pii.py`. A model
earns its place only by finding what no pattern can (a name, a street line with no number) without
inventing identity in ordinary prose. So this measures every backend on the same corpus, and
separately on a set of positives the patterns are known to be blind to.

Two models, four builds:

  onnx    `onnx-community/piiranha-v1-detect-personal-information-ONNX`, DeBERTa-v3, fp32 and int8
  litert  `litert-community/LFM2.5-Encoder-350M-PII-Detector`, 350M tflite, fp16 and wi8fc

Every build in both repos is measured, because the quantised one is the one you would reach for.

    pip install onnxruntime ai-edge-litert tokenizers huggingface-hub
    python -m evals.pii_model
"""
import sys, time, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals.pii import corpus
from evals import backends as B

NAMES = B.MODEL_ADDS

#: What the patterns cannot reach by construction: no digits, no keyword, no checksum.
BLIND = [
    "The account was opened by Priya Ramaswamy in March and closed in June.",
    "Correspondence should go to Wolfgang Amadeus Schmidt at the address below.",
    "Ms Eleanor Vance chaired the meeting and Thomas Okonkwo took the minutes.",
    "He lives on Rosebery Avenue, in the flat above the bakery.",
    "Her address is Flat C, Windermere House, Clapham.",
    "The claimant, Sarah Nakamura, disputes the figure entirely.",
    "Signed by Ahmed El-Sayed on behalf of the trustees.",
    "The referral came from Dr Ingrid Halvorsen at the Bergen clinic.",
]

#: Prose with no identity in it at all, to see what the model invents where the corpus is clean.
CLEAN = [
    "The committee reviewed the outstanding items and deferred the decision to the next quarter.",
    "Conformity with EN 60601-1 was assessed against the harmonised standard in full.",
    "Gradient boosting beat the baseline on one corpus and lost on another, so it was not shipped.",
    "The Bergen clinic reported a fall in referrals over the same period.",
    "Delivery is scheduled for the following quarter subject to approval by the board.",
    "See the wiki page for the specification and the change log that accompanies it.",
    "Reciprocal rank fusion does not make a weak model good; it makes it harmless.",
    "The build takes twenty minutes and costs nothing to run again.",
]


def _score(fn, docs):
    "precision/recall/F1 over `[(text, kinds, neg_class)]`, plus false positives by class."
    tp = fp = fn_ = tn = 0
    per, by_class = {}, {}
    for text, want, neg in docs:
        got = fn(text)
        if want:
            k = next(iter(want))
            d = per.setdefault(k, [0, 0]); d[0 if got else 1] += 1
            tp, fn_ = tp + int(got), fn_ + int(not got)
        else:
            d = by_class.setdefault(neg, [0, 0]); d[0 if got else 1] += 1
            fp, tn = fp + int(got), tn + int(not got)
    prec = tp/(tp+fp) if tp+fp else 0.0
    rec = tp/(tp+fn_) if tp+fn_ else 0.0
    f1 = 2*prec*rec/(prec+rec) if prec+rec else 0.0
    return dict(prec=prec, rec=rec, f1=f1, fp=fp, n_neg=tn+fp, per=per, by_class=by_class)


#: (label, backend, file) for every build in both repos.
BUILDS = [('onnx fp32', 'onnx', 'onnx/model.onnx'),
          ('onnx int8', 'onnx', 'onnx/model_int8.onnx'),
          ('litert fp16', 'litert', 'LFM2.5-Encoder-350M-PII-Detector_fp16.tflite'),
          ('litert wi8fc', 'litert', 'LFM2.5-Encoder-350M-PII-Detector_wi8fc.tflite')]


def _spans(backend, fn):
    "One backend's spans, for the named build."
    if backend == 'litert': return lambda t: B.litert_spans(t, fn=fn)
    return lambda t: B.model_spans(t, fn=fn)


def run(n=480, seed=0, builds=None):
    from vishalakshi import pii as P

    docs = corpus(n, seed)
    chars = sum(len(t) for t, _, _ in docs)
    systems, timing = {}, {}

    print(f'{n} documents from evals.pii, {chars:,} characters\n')

    # patterns, as shipped
    t0 = time.time()
    systems['patterns'] = _score(lambda t: P.pii_report(t).has_pii, docs)
    timing['patterns'] = 1000 * (time.time() - t0) / len(docs)

    got = {}
    for tag, backend, f in (builds or BUILDS):
        spans = _spans(backend, f)
        try: spans('warm up the session')
        except Exception as e:
            print(f'skipping {tag}: {type(e).__name__}: {e}'); continue
        got[tag] = spans
        ident = P.IDENTIFYING | B.MODEL_ONLY

        def only(t, sp=spans, keep=None):
            return any(k in ident and (keep is None or k in keep) for _, _, k, _ in sp(t))

        for name, fn in (
                (tag, only),
                (f'patterns+{tag} all', lambda t, sp=spans: P.pii_report(t).has_pii or only(t, sp)),
                (f'patterns+{tag} MODEL_ADDS',
                 lambda t, sp=spans: P.pii_report(t).has_pii or only(t, sp, NAMES))):
            t0 = time.time()
            systems[name] = _score(fn, docs)
            timing[name] = 1000 * (time.time() - t0) / len(docs)

    print(f'{"system":<28}{"precision":>10}{"recall":>9}{"F1":>8}{"false pos":>12}{"ms/doc":>9}')
    for k, s in systems.items():
        fps = '%d/%d' % (s['fp'], s['n_neg'])
        print(f'{k:<28}{s["prec"]:>10.3f}{s["rec"]:>9.3f}{s["f1"]:>8.3f}{fps:>12}'
              f'{timing.get(k, float("nan")):>9.1f}')

    print('\nrecall by planted kind')
    kinds = sorted(systems['patterns']['per'])
    print(f'{"":<28}' + ''.join(f'{k:>10}' for k in kinds))
    for k, s in systems.items():
        cells = []
        for kd in kinds:
            hit, miss = s['per'].get(kd, (0, 0))
            cells.append(f'{hit/(hit+miss):>10.2f}' if hit+miss else f'{"-":>10}')
        print(f'{k:<28}' + ''.join(cells))

    print('\nfalse positives by lookalike class')
    classes = sorted(systems['patterns']['by_class'])
    print(f'{"":<28}' + ''.join(f'{c:>10}' for c in classes))
    for k, s in systems.items():
        cells = []
        for c in classes:
            hit, miss = s['by_class'].get(c, (0, 0))
            cells.append(f'{f"{hit}/{hit+miss}":>10}' if hit+miss else f'{"-":>10}')
        print(f'{k:<28}' + ''.join(cells))

    # the only reason to pay for a model: what the patterns cannot see
    print(f'\nrecall on {len(BLIND)} sentences no pattern can reach (names, unnumbered streets)')
    print(f'  patterns                 {sum(P.pii_report(t).has_pii for t in BLIND)}/{len(BLIND)}')
    print(f'  patterns ner=True        {sum(P.pii_report(t, ner=True).has_pii for t in BLIND)}/{len(BLIND)}')
    for tag, spans in got.items():
        for lbl, keep in (('', None), (' MODEL_ADDS', NAMES)):
            hit = sum(any(k in P.IDENTIFYING and (keep is None or k in keep)
                          for _, _, k, _ in spans(t)) for t in BLIND)
            print(f'  {tag + lbl:<24} {hit}/{len(BLIND)}')

    print(f'\nidentity invented in {len(CLEAN)} clean sentences')
    print(f'  patterns ner=True        {sum(P.pii_report(t, ner=True).has_pii for t in CLEAN)}/{len(CLEAN)}')
    for tag, spans in got.items():
        bad = [(t, [(v, k) for _, _, k, v in spans(t) if k in P.IDENTIFYING]) for t in CLEAN]
        bad = [b for b in bad if b[1]]
        print(f'  {tag:<24} {len(bad)}/{len(CLEAN)}')
        for t, sp in bad: print(f'      {t[:52]:<54}{sp}')
    return systems


if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    run()
