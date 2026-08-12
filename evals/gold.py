"""A gold set from a real vault, so the numbers in RESULTS.md can be re-measured against yours.

The generated corpora settle questions about the *features* — they have ground truth and can be
resampled — but they cannot tell you whether any of this helps on your own material. That needs
queries with known answers over your own documents, and nobody is going to write three hundred of
those by hand.

So they are generated the other way round: sample a section, have a local model write a question
that *only that section* answers, and keep the section as the gold answer. Known-item retrieval,
a few hundred queries, no annotation.

Two things this gets wrong, both of which matter and neither of which is fatal:

- **It measures findability, not usefulness.** A question written from a passage is answerable from
  that passage by construction. Real questions are not, and a system tuned only on these will be
  tuned for lookup rather than for synthesis. Read it as a floor.
- **It inherits the writing model's habits.** If the model writes questions using the passage's own
  rare words, the keyword leg finds them trivially and every ranker looks equally good. `screen`
  drops the queries that the baseline already answers at rank 1 *and* the ones nothing answers at
  all, which is where the discrimination is.

    python -m evals.gold --vault ~/.vishalakshi/vault.db --n 200
"""
import sys, json, argparse, random, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROMPT = """Below is one section from a document.

Write ONE question that this section answers and that a reader would plausibly ask. Rules:
- Do not use the words "this section", "the passage", "the text", or "the document".
- Do not quote a whole sentence from it. Paraphrase.
- The question must be specific enough that only this section answers it.
- Reply with the question and nothing else.

SECTION
-------
{text}"""


def sample_nodes(v, n=200, min_chars=400, seed=0):
    "Sections long enough to carry a question, sampled across documents rather than within one."
    rows = [r for r in v.t.nodes(select='id, doc_id, title, nchunks') if (r['nchunks'] or 0) >= 2]
    rng = random.Random(seed); rng.shuffle(rows)
    by_doc, out = {}, []
    for r in rows:                       # at most two per document, or a long one dominates
        if by_doc.get(r['doc_id'], 0) >= 2: continue
        s = v.read(r['id'], max_chars=3000)
        if len((s or {}).get('text') or '') < min_chars: continue
        by_doc[r['doc_id']] = by_doc.get(r['doc_id'], 0) + 1
        out.append(dict(node_id=r['id'], doc_id=r['doc_id'], title=r['title'], text=s['text']))
        if len(out) >= n: break
    return out


def generate(v, nodes, model=None, mk_chat=None, **chat_kw):
    "Ask a model for one question per section. Failures are dropped, not retried."
    from vishalakshi.ask import new_chat, resp_text, split_reasoning
    out = []
    for i, nd in enumerate(nodes):
        try:
            ch = (mk_chat or new_chat)(model, sp='You write precise retrieval questions.', **chat_kw)
            q, _ = split_reasoning(resp_text(ch(PROMPT.format(text=nd['text'][:3000]))))
            q = q.strip().strip('"').splitlines()[0].strip()
            if len(q) > 15: out.append(dict(q=q, gold=nd['node_id'], doc_id=nd['doc_id'], title=nd['title']))
        except Exception as e:
            warnings.warn(f'question {i} failed ({type(e).__name__}: {e})')
    return out


def screen(v, gold, limit=20):
    """Drop the queries that decide nothing.

    A query the baseline already answers at rank 1 cannot show an improvement, and one where the
    gold section is not in the top `limit` at all cannot show one either. What is left is the band
    where reranking is even in principle able to matter, and a comparison run over the unscreened
    set is mostly a measurement of how much of it was already easy."""
    keep = []
    for g in gold:
        hits = v.sections(g['q'], limit=limit)
        ids = [h['node_id'] for h in hits]
        if g['gold'] in ids and ids.index(g['gold']) > 0: keep.append(dict(g, base_rank=ids.index(g['gold'])+1))
    return keep


def save(gold, path): Path(path).write_text(json.dumps(gold, indent=1)); return path
def load(path): return json.loads(Path(path).read_text())


def evaluate(v, gold, systems=None, k=10, boot=5000):
    """Score `{name: fn(q, hits) -> reordered hits}` against a gold set, paired against the baseline.

    `systems` defaults to the fused ranker if one is stored, which is the comparison worth running
    before `use_ranker(True)`.
    """
    from evals.metrics import score_run, compare, show
    from fastcore.all import AttrDict, L
    systems = systems or {}
    if not systems:
        rk = v._rk() or (v.fit_ranker() if len(v.ratings()) else None)
        if rk is not None and rk.w is not None:
            systems = {f'+ranker@{a}': (lambda a: lambda q, h: v.retune(q, h, ranker=rk, alpha=a))(a)
                       for a in (0.25, 0.5, 1.0)}
    runs = {'base': [], **{n: [] for n in systems}}
    for g in gold:
        hits = L(AttrDict(node_id=s['node_id'], doc_id=s['node_id'].split('#')[0], score=float(s['score']),
                          text=' '.join(s['snippets']), breadcrumb=s['breadcrumb'])
                 for s in v.sections(g['q'], limit=k*2))
        if not hits: continue
        J = lambda hh: ([1 if h.node_id == g['gold'] else 0 for h in hh][:k], 1, [False]*min(len(hh), k))
        runs['base'].append(J(hits))
        for n, f in systems.items(): runs[n].append(J(L(f(g['q'], hits))))
    scored = {n: score_run(rs, k=k) for n, rs in runs.items() if rs}
    for n in scored:
        if n == 'base': continue
        print(f'\n{n} vs base  ({len(runs["base"])} queries)')
        show(compare(n, scored[n], 'base', scored['base'], n_boot=boot), n, 'base')
    return scored


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vault', default=None)
    ap.add_argument('--n', type=int, default=200)
    ap.add_argument('--model', default=None)
    ap.add_argument('--out', default='evals/gold.json')
    ap.add_argument('--evaluate', action='store_true', help='score a stored ranker on an existing gold set')
    a = ap.parse_args()
    from vishalakshi import Vault
    v = Vault(a.vault)
    if a.evaluate: return evaluate(v, load(a.out))
    nodes = sample_nodes(v, n=a.n)
    print(f'{len(nodes)} sections sampled; writing questions with {a.model or "$VISHALAKSHI_MODEL"}')
    gold = generate(v, nodes, model=a.model)
    kept = screen(v, gold)
    print(f'{len(gold)} questions generated, {len(kept)} kept after screening -> {save(kept, a.out)}')


if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    main()
