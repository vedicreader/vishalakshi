"""What the hashing fallback costs.

`Vault(offline=True)` swaps the static encoder for character n-gram hashing so a machine with no
network still has a working vault. `concepts` says that changes what the results mean. This puts a
number on it, because "lexical only" is not a number and the fallback is silent enough that
somebody will end up running on it without noticing.

Known-item queries where the query shares words with the target favour hashing; the topic queries
are the ones that need the embedding to generalise.

    python -m evals.encoder
"""
import sys, tempfile, warnings
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals import corpus
from evals.metrics import score_run, compare, show

K = 10


def _run_one(encoder, offline, seed=0, n_queries=90):
    from vishalakshi import Vault
    v = Vault(Path(tempfile.mkdtemp())/'enc.db', encoder=encoder, offline=offline, dims=256)
    truth = corpus.build(v, seed=seed)
    by_title = {r['title']: r['id'] for r in v.sources()}
    out = {}
    ki = [(q, by_title[t], tp) for q, t, tp in corpus.known_item(n=n_queries, seed=seed+1)]
    out['known'] = [([1 if s['node_id'].split('#')[0] == g else 0
                      for s in v.sections(q, limit=K)], 1, [False]*K) for q, g, _ in ki]
    n_by = {}
    for _, t in truth.values(): n_by[t] = n_by.get(t, 0) + 1
    tq = corpus.queries(n=n_queries, seed=seed+1)
    out['topic'] = [([1 if truth.get(s['node_id'].split('#')[0], (0, None))[1] == tp else 0
                      for s in v.sections(q, limit=K)], n_by.get(tp, 1), [False]*K) for q, tp in tq]
    return {k: score_run(rs, k=K) for k, rs in out.items()}


def run(seed=0, n_queries=90):
    real = _run_one('retrieval', False, seed, n_queries)
    hashed = _run_one(None, True, seed, n_queries)
    for mode in ('known', 'topic'):
        print(f'\n=== {mode}-item queries, {n_queries} of them ===')
        show(compare('static', real[mode], 'hash', hashed[mode],
                     keys=('ndcg', 'mrr', 'recall')), 'static', 'hash')
    return real, hashed


if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    run()
