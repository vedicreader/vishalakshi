"""Does the noise score find the noise, and does it spare the surveys?

Two questions, and the second is the one worth running.

1. **Per-feature AUC.** Every feature scored on its own against ground truth. AUC because it needs
   no threshold: 0.5 is a coin, 1.0 separates perfectly, and below 0.5 means the feature points the
   wrong way, which is a result rather than a bug.
2. **The survey test.** `corpus.py` plants documents that range over every topic and are *not*
   noise. The claim in `quality.py` is that document-level cluster spread cannot tell them from
   boilerplate and chunk-level spread can. This prints the two numbers side by side and lets the
   corpus settle it.

    python -m evals.noise
"""
import sys, warnings, tempfile
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals import corpus
from evals.metrics import auc


def build(seed=0, encoder='retrieval', offline=False, **kw):
    """A vault filled from `corpus.make`, on a real encoder by default.

    The hash fallback is available and is the wrong thing to measure on: hashing makes near-identical
    text into identical vectors and unrelated text into near-orthogonal ones, which flatters the
    duplicate features and leaves the geometric ones (`hub`, `centroid`, the spread pair) with no
    structure to read. Every number here was produced with `encoder='retrieval'`.
    """
    from vishalakshi import Vault
    v = Vault(Path(tempfile.mkdtemp())/'noise.db', encoder=encoder, offline=offline)
    return v, corpus.build(v, seed=seed, **kw)


def run(seed=0, **kw):
    from vishalakshi.quality import NOISE_FEATURES, NOISE_W, _robust_z
    v, truth = build(seed=seed, **kw)
    f = v.noise_features()
    y = np.array([truth[d][0] for d in f.doc_ids])
    topic = np.array([truth[d][1] for d in f.doc_ids])
    Z = _robust_z(f.X)

    print(f'\n{len(f.doc_ids)} documents, {int(y.sum())} of them noise by construction\n')
    print(f'{"feature":<14}{"AUC":>7}   {"boiler":>8}{"survey":>8}{"content":>8}   weight')
    print('-'*62)
    order = sorted(range(len(f.names)), key=lambda i: -auc(f.X[:, i], y))
    for i in order:
        n = f.names[i]
        m = lambda t: float(np.mean(Z[topic == t, i])) if (topic == t).any() else float('nan')
        mm = lambda t: float(np.mean(Z[(topic != 'boiler') & (topic != 'survey'), i]))
        print(f'{n:<14}{auc(f.X[:, i], y):>7.3f}   {m("boiler"):>+8.2f}{m("survey"):>+8.2f}{mm(""):>+8.2f}   {NOISE_W.get(n,0):.1f}')

    s = np.array([r.score for r in sorted(v.noise_scores(), key=lambda r: f.doc_ids.index(r.doc_id))])
    print(f'\nblended score AUC: {auc(s, y):.3f}')

    print('\n--- the survey test -------------------------------------------------')
    print('A feature that cannot tell a survey from a footer is not a noise feature.')
    print(f'{"feature":<14}{"boiler z":>10}{"survey z":>10}{"gap":>10}  reads')
    for n in ('spread_doc', 'spread_chunk', 'hub', 'dup_out'):
        i = f.names.index(n)
        b, sv = float(np.mean(Z[topic == 'boiler', i])), float(np.mean(Z[topic == 'survey', i]))
        verdict = ('separates' if b - sv > 1.0 else 'confuses them' if abs(b - sv) < 0.5 else 'weak')
        print(f'{n:<14}{b:>+10.2f}{sv:>+10.2f}{b-sv:>+10.2f}  {verdict}')

    print('\n--- top of the ranking ----------------------------------------------')
    for r in v.noise_scores()[:12]:
        print(f'  {r.score:+.2f}  {"NOISE" if truth[r.doc_id][0] else "     "}  {r.title}')
    return v, truth, f, y


def sweep(seeds=(0, 1, 2)):
    "The blended AUC over several corpora, since one draw of a synthetic corpus proves nothing."
    from vishalakshi.quality import _robust_z
    out = []
    for s in seeds:
        v, truth = build(seed=s)
        f = v.noise_features()
        y = np.array([truth[d][0] for d in f.doc_ids])
        sc = {r.doc_id: r.score for r in v.noise_scores()}
        out.append(auc(np.array([sc[d] for d in f.doc_ids]), y))
    print(f'\nblended AUC over {len(seeds)} corpora: '
          f'{np.mean(out):.3f} (min {min(out):.3f}, max {max(out):.3f})')
    return out


if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    run()
    sweep()


def fitted(seeds=(0, 1, 2, 3), n_mark=6, folds=3, seed=7):
    """Fixed weights against a blend fitted from a handful of marks, held out.

    The fit never sees the documents it is scored on: the marked documents are split into folds,
    weights are fitted on the rest, and AUC is computed over the held-out fold plus every unmarked
    document. `n_mark` is deliberately small: six confirmations is a realistic afternoon, and the
    question is whether six is enough to beat a table of constants.
    """
    import numpy as np, random
    from vishalakshi.quality import _robust_z, Ranker, NOISE_W
    rows = []
    for s in seeds:
        v, truth = build(seed=s)
        f = v.noise_features()
        y = np.array([float(truth[d][0]) for d in f.doc_ids])
        Z = _robust_z(f.X)
        w = np.array([NOISE_W.get(n, 0.0) for n in f.names])
        fixed = auc(Z @ w, y)
        best = max(auc(f.X[:, i], y) for i in range(len(f.names)))

        rng = random.Random(seed + s)
        pos = [i for i in range(len(y)) if y[i]]
        neg = [i for i in range(len(y)) if not y[i]]
        rng.shuffle(pos); rng.shuffle(neg)
        marked = pos[:n_mark] + neg[:n_mark*3]        # you mark noise, and confirm some keepers
        got = []
        for k in range(folds):
            test = set(marked[k::folds])
            tr = [i for i in marked if i not in test]
            if len({y[i] for i in tr}) < 2: continue
            r = Ranker(f.names).fit(Z[tr], ['all']*len(tr), y[tr], l2=1.0)
            held = [i for i in range(len(y)) if i not in set(marked) or i in test]
            got.append(auc(r.score(Z[held]), y[held]))
        rows.append((s, fixed, best, float(np.mean(got)) if got else float('nan')))

    print(f'\n{"corpus":>7}{"fixed weights":>15}{"best single":>13}{"fitted (held-out)":>19}')
    for s, fx, bs, ft in rows: print(f'{s:>7}{fx:>15.3f}{bs:>13.3f}{ft:>19.3f}')
    m = lambda i: float(np.nanmean([r[i] for r in rows]))
    print(f'{"mean":>7}{m(1):>15.3f}{m(2):>13.3f}{m(3):>19.3f}')
    return rows
