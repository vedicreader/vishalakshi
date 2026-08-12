"""Ranking metrics and the paired bootstrap, which is the part that decides anything.

A bare delta between two rankers on ninety queries means nothing on its own: the variance across
queries is larger than almost any effect a reranker produces, and the same experiment run on a
different sample of queries routinely reverses sign. So every comparison here is paired — both
systems are scored on *the same* queries — and reported as a mean difference with a bootstrap
confidence interval over queries. If the interval spans zero, the honest report is "no difference
measured", and this module makes that the easy thing to write down.
"""
import numpy as np

def dcg(rels):
    r = np.asarray(rels, float)
    return float((r / np.log2(np.arange(2, len(r) + 2))).sum())

def ndcg(rels, ideal=None, k=10):
    "Normalised DCG@k. `ideal` is the best ordering available, defaulting to sorting what was found."
    rels = list(rels)[:k]
    best = sorted(ideal if ideal is not None else rels, reverse=True)[:k]
    d = dcg(best)
    return dcg(rels) / d if d > 0 else 0.0

def mrr(rels, k=10):
    "Reciprocal rank of the first relevant hit."
    for i, r in enumerate(list(rels)[:k], 1):
        if r > 0: return 1.0 / i
    return 0.0

def recall(rels, n_rel, k=10):
    return (sum(1 for r in list(rels)[:k] if r > 0) / n_rel) if n_rel else 0.0

def precision(rels, k=10):
    rels = list(rels)[:k]
    return (sum(1 for r in rels if r > 0) / len(rels)) if rels else 0.0

def noise_at_k(is_noise, k=10):
    "The fraction of what came back that ground truth calls noise — the metric this work is for."
    v = list(is_noise)[:k]
    return (sum(1 for x in v if x) / len(v)) if v else 0.0

def score_run(runs, k=10):
    """`runs` is `[(rels, n_rel, is_noise)]`, one per query -> per-query metric arrays.

    Kept per query rather than averaged, because the paired bootstrap needs the individual values.
    """
    return dict(ndcg=np.array([ndcg(r, k=k) for r, _, _ in runs]),
                mrr=np.array([mrr(r, k=k) for r, _, _ in runs]),
                recall=np.array([recall(r, n, k=k) for r, n, _ in runs]),
                precision=np.array([precision(r, k=k) for r, _, _ in runs]),
                noise=np.array([noise_at_k(z, k=k) for _, _, z in runs]))

def paired(a, b, n_boot=5000, alpha=0.05, seed=0):
    """Mean of `a - b` with a bootstrap CI over queries, resampling the *pairs*.

    Returns `(delta, lo, hi, p)`, where `p` is the two-sided fraction of resamples on the far side
    of zero. A CI containing zero is the result, not a failure to find one.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    if not len(d): return 0.0, 0.0, 0.0, 1.0
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    boots = d[idx].mean(1)
    lo, hi = np.quantile(boots, [alpha/2, 1 - alpha/2])
    p = 2 * min((boots <= 0).mean(), (boots >= 0).mean())
    return float(d.mean()), float(lo), float(hi), float(min(p, 1.0))

def compare(name_a, sa, name_b, sb, keys=('ndcg', 'mrr', 'recall', 'noise'), **kw):
    "One printable table of paired differences between two scored runs."
    rows = []
    for k in keys:
        d, lo, hi, p = paired(sa[k], sb[k], **kw)
        rows.append(dict(metric=k, a=float(np.mean(sa[k])), b=float(np.mean(sb[k])),
                         delta=d, lo=lo, hi=hi, p=p,
                         verdict='—' if lo <= 0 <= hi else ('better' if d > 0 else 'worse')))
    return rows

def show(rows, name_a='A', name_b='B'):
    print(f'{"metric":<10}{name_a:>9}{name_b:>9}{"Δ":>9}{"95% CI":>20}{"p":>8}  verdict')
    for r in rows:
        ci = f'[{r["lo"]:+.4f},{r["hi"]:+.4f}]'
        print(f'{r["metric"]:<10}{r["a"]:>9.4f}{r["b"]:>9.4f}{r["delta"]:>+9.4f}{ci:>20}{r["p"]:>8.3f}  {r["verdict"]}')

def auc(scores, labels):
    "Rank AUC — how well a score separates two classes, with no threshold to argue about."
    s, y = np.asarray(scores, float), np.asarray(labels, bool)
    n_p, n_n = int(y.sum()), int((~y).sum())
    if not n_p or not n_n: return float('nan')
    # average ranks for ties, or a feature that is constant (an unexercised one, like
    # `promiscuity` on a vault with no feedback log) scores whatever argsort happened to do.
    order = np.argsort(s, kind='mergesort')
    ranks = np.empty(len(s), float); ranks[order] = np.arange(1, len(s) + 1)
    su = np.sort(s)
    i = 0
    while i < len(su):
        j = i
        while j + 1 < len(su) and su[j+1] == su[i]: j += 1
        if j > i: ranks[order[i:j+1]] = (i + j + 2) / 2.0
        i = j + 1
    return float((ranks[y].sum() - n_p*(n_p+1)/2) / (n_p*n_n))
