"""The ladder: does any of this beat plain RRF, and by how much, with what confidence.

Five systems on the same queries, scored against ground truth from `corpus.py`:

- **base** — `v.sections`, which is litesearch's hybrid retrieval and the thing to beat.
- **+noise** — the same, with the documents the *unsupervised* score flags excluded. No labels used.
- **+prior** — the same, rescored by the per-document Beta posterior from the training feedback.
- **+linear** — the pairwise `Ranker`, fitted on the training half of the feedback log.
- **+forest / +gbdt** — the same features under scikit-learn, if it is installed. Present so that
  "a forest would do better" is a measurement rather than an argument.

Two splits, and the second is the one that catches self-deception:

- **query-disjoint** — train and test on different queries. The usual split.
- **document-disjoint** — test only on queries whose relevant documents were never in training. A
  model that has quietly memorised *which documents are good*, rather than what makes a section
  relevant, scores well on the first and collapses on the second. Since a third of the features
  are document-level, that is a live risk here rather than a hypothetical one.

Feedback is simulated the way `ask` produces it: for each training query the relevant sections are
logged `cited` and the rest `shown`. That models the citation channel and inherits its position
bias, which is the point — it is what the real log will look like.

    python -m evals.run
"""
import sys, warnings, tempfile, random
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals import corpus
from evals.metrics import score_run, compare, show, paired

K = 10
#: fusion weights swept for the learned leg; 0 is the baseline untouched
ALPHAS = (0.25, 0.5, 1.0)


def _hits(v, q, limit=K):
    "Sections shaped the way `retune` and `pair_X` expect them."
    from fastcore.all import AttrDict, L
    return L(AttrDict(node_id=s['node_id'], doc_id=s['node_id'].split('#')[0], score=float(s['score']),
                      text=' '.join(s['snippets']), breadcrumb=s['breadcrumb'])
             for s in v.sections(q, limit=limit))


def _judge(hits, topic, truth, n_rel):
    rels = [1 if truth.get(h.doc_id, (False, None))[1] == topic else 0 for h in hits]
    noise = [truth.get(h.doc_id, (False, None))[0] for h in hits]
    return rels, n_rel, noise


def simulate(v, qs, truth):
    "Log the training queries the way `ask` would: relevant sections cited, the rest shown."
    import uuid
    n = 0
    for q, topic in qs:
        hs = _hits(v, q)
        if not hs: continue
        aid = uuid.uuid4().hex[:12]
        for i, h in enumerate(hs, 1):
            rel = truth.get(h.doc_id, (False, None))[1] == topic
            v.rate(q, node_id=h.node_id, doc_id=h.doc_id, signal='cited' if rel else 'shown',
                   rank=i, score=h.score, ask_id=aid)
            n += 1
    return n


def _sk(name, X, g, y, w):
    "A scikit-learn model on the same pairwise differences, or None when sklearn is absent."
    try:
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    except ImportError: return None
    from collections import defaultdict
    by = defaultdict(list)
    for i, k in enumerate(g): by[k].append(i)
    D, Y = [], []
    for ix in by.values():
        for a in ix:
            for b in ix:
                if y[a] > y[b]: D.append(X[a]-X[b]); Y.append(1); D.append(X[b]-X[a]); Y.append(0)
    if len(set(Y)) < 2: return None
    m = (RandomForestClassifier(n_estimators=300, min_samples_leaf=5, random_state=0, n_jobs=-1)
         if name == 'forest' else
         GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0))
    m.fit(np.array(D), np.array(Y))

    def borda(Z):
        """Score by round robin: item i scores the mean P(i beats j) over the others.

        A pairwise model consumes a *difference*, so it cannot score one item in isolation. For a
        linear model that does not matter -- w.(x - 0) = w.x, so feeding it the item works -- and
        doing the same to a forest asks it about a point it was never trained near. That is a bug
        in the harness, not a fact about forests, and it is the sort of bug that produces a
        confident negative result about whichever model you were least inclined to adopt."""
        Z = np.asarray(Z); n = len(Z)
        if n < 2: return np.zeros(n)
        i, j = np.triu_indices(n, 1)
        p = m.predict_proba(Z[i] - Z[j])[:, 1]
        s = np.zeros(n); c = np.zeros(n)
        np.add.at(s, i, p);       np.add.at(c, i, 1)
        np.add.at(s, j, 1.0 - p); np.add.at(c, j, 1)
        return s / np.maximum(c, 1)
    return borda


def _split(items, key, train_frac, seed):
    """Split by `key` rather than by row, so no key appears on both sides.

    With `key` the gold document, this is the document-disjoint split: every document a test query
    is about was invisible during training. A model that has learned *which documents are good* --
    and a third of these features are document-level, so that is the standing temptation -- scores
    well on a query split and loses its advantage entirely on this one. The gap between the two
    numbers is the measurement of how much was memorisation."""
    ks = sorted({key(x) for x in items})
    rng = random.Random(seed); rng.shuffle(ks)
    tr = set(ks[:int(len(ks)*train_frac)])
    return [x for x in items if key(x) in tr], [x for x in items if key(x) not in tr]


def run(seed=0, n_queries=90, train_frac=0.5, encoder='retrieval', boot=5000,
        mode='known', split='document'):
    """One rung-by-rung comparison. `mode` picks the query regime, `split` picks the honesty level.

    `mode='topic'`   — a whole topic is relevant. The regime where you return to the same material,
                       and the one the Beta prior exists for.
    `mode='known'`   — exactly one document answers each query, and it differs every time. Nothing
                       document-level transfers, so a ranker has to have learned about matching.
    `split='query'`  — train and test queries differ. `split='document'` additionally guarantees the
                       gold documents differ, which is the split that catches memorisation.
    """
    from vishalakshi import Vault
    from vishalakshi.quality import Ranker

    v = Vault(Path(tempfile.mkdtemp())/'run.db', encoder=encoder)
    truth = corpus.build(v, seed=seed)
    by_title = {r['title']: r['id'] for r in v.sources()}
    n_by_topic = {}
    for _, t in truth.values(): n_by_topic[t] = n_by_topic.get(t, 0) + 1

    if mode == 'known':
        qs = [(q, by_title[title], topic) for q, title, topic in corpus.known_item(n=n_queries, seed=seed+1)]
        gold = lambda item: item[1]                      # relevant iff it is *this* document
        rel_of = lambda item, h: 1 if h.doc_id == item[1] else 0
        n_rel_of = lambda item: 1
    else:
        qs = [(q, topic, topic) for q, topic in corpus.queries(n=n_queries, seed=seed+1)]
        gold = lambda item: item[2]
        rel_of = lambda item, h: 1 if truth.get(h.doc_id, (False, None))[1] == item[2] else 0
        n_rel_of = lambda item: n_by_topic.get(item[2], 1)

    if split == 'document': train, test = _split(qs, gold, train_frac, seed)
    else:
        rng = random.Random(seed); ix = list(range(len(qs))); rng.shuffle(ix)
        cut = int(len(ix)*train_frac)
        train, test = [qs[i] for i in ix[:cut]], [qs[i] for i in ix[cut:]]

    print(f'\n{"="*74}\nmode={mode}  split={split}  encoder={encoder}  seed={seed}')
    print(f'{len(truth)} documents ({sum(1 for x in truth.values() if x[0])} noisy), '
          f'{len(train)} train / {len(test)} test queries')

    import uuid
    for item in train:
        hs = _hits(v, item[0], limit=K)
        if not hs: continue
        aid = uuid.uuid4().hex[:12]
        for i, h in enumerate(hs, 1):
            v.rate(item[0], node_id=h.node_id, doc_id=h.doc_id,
                   signal='cited' if rel_of(item, h) else 'shown', rank=i, score=h.score, ask_id=aid)

    d = v.training_data()
    print(f'feedback: {len(v.ratings())} rows -> {d.X.shape[0]} labelled hits in {len(set(d.groups))} usable groups')
    if not d.X.shape[0]:
        print('nothing to fit'); return v, truth, {}
    lin = Ranker(d.names).fit(d.X, d.groups, d.y, weights=d.weights, l2=1.0)
    print('top weights: ' + ', '.join(f'{w.feature}={w.weight:+.3f}' for w in lin.weights()[:6]))

    models = dict(linear=lin.score)
    Zt = (d.X - lin.mu)/lin.sd
    for nm in ('forest', 'gbdt'):
        f = _sk(nm, Zt, d.groups, d.y, d.weights)
        if f is not None: models[nm] = f

    flagged = {r.doc_id for r in v.suggest_noisy(k=10, min_score=0.5)}
    prior = v.doc_prior(explore=0.0)
    print(f'unsupervised noise filter flagged {len(flagged)} documents; '
          f'{sum(1 for dd in flagged if truth.get(dd,(False,))[0])} of them are noise by construction')

    runs = {n: [] for n in ['base', '+noise', '+prior'] + [f'+{m}' for m in models]
                       + [f'+linear@{a}' for a in ALPHAS]}
    for item in test:
        q = item[0]
        hs = _hits(v, q, limit=K*2)
        if not hs: continue
        nr = n_rel_of(item)
        J = lambda hh: ([rel_of(item, h) for h in hh], nr, [truth.get(h.doc_id, (False,))[0] for h in hh])
        runs['base'].append(J(hs[:K]))
        runs['+noise'].append(J([h for h in hs if h.doc_id not in flagged][:K]))
        runs['+prior'].append(J(sorted(hs, key=lambda h: -h.score*prior.get(h.doc_id, 1.0))[:K]))
        X = v.pair_X(q, hs)
        for nm, f in models.items():
            sc = f(X) if nm == 'linear' else f((X - lin.mu)/lin.sd)
            runs[f'+{nm}'].append(J([hs[i] for i in sorted(range(len(hs)), key=lambda i: -sc[i])][:K]))
        # the same linear model, fused with the incoming order instead of replacing it
        for a in ALPHAS:
            runs[f'+linear@{a}'].append(J(list(v.retune(q, hs, ranker=lin, alpha=a))[:K]))

    scored = {k: score_run(rs, k=K) for k, rs in runs.items()}
    print(f'\n--- paired bootstrap over {len(test)} test queries, {boot} resamples ---')
    for nm in runs:
        if nm == 'base': continue
        print(f'\n{nm} vs base')
        show(compare(nm, scored[nm], 'base', scored['base'], n_boot=boot), nm, 'base')
    return v, truth, scored


def ladder(seed=0, **kw):
    "Both regimes and both splits — the whole table, which is the only honest way to read any of it."
    out = {}
    for mode in ('topic', 'known'):
        for split in ('query', 'document'):
            out[(mode, split)] = run(seed=seed, mode=mode, split=split, **kw)[2]
    return out


if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    ladder()
