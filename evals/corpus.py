"""Synthetic corpora with ground truth, for the experiments in `noise.py` and `run.py`.

Synthetic rather than borrowed, because the labels these questions need are ones no public corpus
carries: *which documents are noise*, and *which section answers this query*. A generated corpus
states both by construction, so the generator is the specification of what the noise score is
meant to find — and getting the generator wrong is the easiest way to prove something false.

Three populations, and the third exists to catch a specific mistake:

- **content** — prose on one topic, in that topic's vocabulary, each document carrying a handful of
  rare terms of its own. The rare terms matter: a corpus in which every document draws from the
  same fifteen words has no IDF structure, and any feature that reads term specificity will come
  out of such a corpus looking dead when it is only unexercised.
- **boiler** — cookie banners, licence blocks, mail footers. Near-identical to one another, present
  both as whole documents and as a tail glued onto content documents, which is how boilerplate
  actually arrives in a vault. Ground truth: noise.
- **survey** — documents that range across every topic. **Each paragraph is about one topic**, and
  that is the whole point of them: a real survey is broad at the document level and specific at
  the paragraph level. Generating them as an even blend of all vocabularies would make them
  generic rather than broad, which is a different object and would rig the experiment they exist
  to decide. Ground truth: not noise.
"""
import random

TOPICS = dict(
    retrieval=dict(
        terms='retrieval ranking recall precision inverted index embedding vector hybrid fusion relevance'.split(),
        frames=['The {a} stage dominates cost when the {b} is large.',
                'Measured on three corpora, {a} improved {b} without changing latency.',
                'Chunk size interacts with {a}: shorter passages raise {b} and lower precision.',
                'Fusing the keyword and vector legs by reciprocal rank leaves {a} unchanged.',
                'A cross-encoder reorders candidates after {a}, at roughly ten times the cost.'],
        rare='RankFuse Colberta Spanmerge BM25X Provenire Hexastore'.split()),
    optics=dict(
        terms='lens refraction diffraction wavelength interference aperture focal polarisation coherence beam'.split(),
        frames=['At short {a}, the {b} pattern collapses toward the axis.',
                'Increasing the {a} broadens the point spread and reduces contrast.',
                'The {a} of the source sets how far {b} survives propagation.',
                'A quarter-wave plate rotates {a} without attenuating the beam.',
                'Chromatic error scales with {a} and is corrected by a doublet.'],
        rare='Zernike Fizeau Ronchi Foucault Strehl Airy'.split()),
    monetary=dict(
        terms='inflation interest liquidity reserve yield curve issuance tightening deficit currency'.split(),
        frames=['Persistent {a} forced the committee to reconsider the path of {b}.',
                'The {a} inverted three quarters before the contraction in {b}.',
                'Sterilised intervention changed {a} without altering the stock of {b}.',
                'A widening {a} was financed by short-dated {b} at rising cost.',
                'Expectations of {a} feed into wage settlements with a long lag.'],
        rare='Bagehot Wicksell Triffin Gresham Fisherian Bretton'.split()),
    metallurgy=dict(
        terms='alloy tempering quench austenite ferrite hardness ductility annealing lattice carbide'.split(),
        frames=['Rapid {a} traps carbon and raises {b} at the cost of toughness.',
                'Holding above the transformation point coarsens {a} and softens the {b}.',
                'Trace boron shifts the {a} curve and improves hardenability.',
                'Residual stress from {a} is relieved by a second, lower {b}.',
                'Grain refinement raises both strength and {a}, which is unusual.'],
        rare='Widmanstatten Jominy Bainite Martensite Charpy Vickers'.split()),
    liturgy=dict(
        terms='chant antiphon vespers psalter rubric feast vestment procession matins responsory'.split(),
        frames=['The {a} is sung before the {b} on ferial days.',
                'A doubled {a} marks the feast and displaces the ordinary {b}.',
                'The {a} directs that the {b} be omitted in penitential seasons.',
                'Local use retained an older {a} long after the reform of the {b}.',
                'The tone of the {a} is fixed by the mode of its {b}.'],
        rare='Sarum Mozarabic Ambrosian Gallican Tridentine Neume'.split()),
    reptiles=dict(
        terms='scale clutch carapace venom basking moult vivarium arboreal oviparous squamate'.split(),
        frames=['Females deposit the {a} where substrate temperature governs {b}.',
                'Prolonged {a} precedes the shed and dulls the {b}.',
                'The {a} is keeled in terrestrial forms and smooth in {b} ones.',
                'Delivery of {a} is solenoglyphous, with the fang folded when at rest.',
                'Thermal preference narrows during {a}, which constrains {b}.'],
        rare='Uromastyx Tiliqua Varanus Chelonia Gekkota Serpentes'.split()),
)

BOILER_LINES = [
    'We use cookies and similar technologies to personalise content and analyse traffic.',
    'All rights reserved. Reproduction in whole or in part without written permission is prohibited.',
    'You may manage your preferences at any time from the link in the footer of any page.',
    'This message and any attachments are confidential and intended solely for the addressee.',
    'If you have received this in error please notify the sender and delete it from your system.',
    'Registered office: 14 Threadneedle Buildings. Company number 04471902. VAT registered.',
    'Unsubscribe from these notifications by updating your communication preferences.',
    'By continuing to browse the site you consent to our terms of service and privacy policy.',
]

def _para(rng, spec, rare, n=4):
    t = spec['terms']
    return ' '.join(rng.choice(spec['frames']).format(a=rng.choice(t), b=rng.choice(t))
                    + (f' See also the {rng.choice(rare)} treatment.' if rng.random() < 0.4 else '')
                    for _ in range(n))

def _boiler(rng, n=5):
    ls = BOILER_LINES[:]; rng.shuffle(ls)
    return ' '.join(ls[:n])

def make(n_content=60, n_boiler=8, n_survey=4, glued=0.4, seed=0):
    """`[(title, text, is_noise, topic)]` — a corpus that knows which of its documents are noise.

    `glued` is the fraction of content documents carrying a boilerplate tail. Those are *not*
    labelled noise: the document is good and only part of it is junk. That is the case a
    document-level score is allowed to get wrong, and the reason `noise@k` is measured at the
    section level rather than the document level.
    """
    rng, names, out = random.Random(seed), list(TOPICS), []
    for i in range(n_content):
        t = names[i % len(names)]
        spec = TOPICS[t]
        rare = rng.sample(spec['rare'], 2)          # this document's own vocabulary
        body = '\n\n'.join(_para(rng, spec, rare) for _ in range(4))
        if rng.random() < glued: body += '\n\n' + _boiler(rng)
        out.append((f'{t.title()} note {i}', body, False, t))
    for i in range(n_boiler):
        out.append((f'Footer {i}', '\n\n'.join(_boiler(rng) for _ in range(3)), True, 'boiler'))
    for i in range(n_survey):
        # broad, not generic: one topic per paragraph, every topic represented
        paras = [_para(rng, TOPICS[t], TOPICS[t]['rare']) for t in names]
        rng.shuffle(paras)
        out.append((f'Survey {i}', '\n\n'.join(paras), False, 'survey'))
    return out

def build(vault, seed=0, **kw):
    "Fill a vault with `make(...)` and return `{doc_id: (is_noise, topic)}`."
    truth = {}
    for title, text, noise, topic in make(seed=seed, **kw):
        r = vault.add(text, title=title, source=f'syn://{seed}/{title}', kind='note')
        truth[r['doc_id']] = (noise, topic)
    return truth

def queries(n=90, seed=1):
    """`[(question, topic)]` — known-item queries phrased in one topic's language.

    A retrieved section counts as relevant when its document is on the query's topic. Coarse, but
    true by construction, which is exactly what a citation log is not.
    """
    rng, names = random.Random(seed), list(TOPICS)
    out = []
    for i in range(n):
        t = names[i % len(names)]
        spec = TOPICS[t]
        out.append((rng.choice(spec['frames']).format(a=rng.choice(spec['terms']), b=rng.choice(spec['terms'])), t))
    return out


def known_item(n=90, seed=1, **kw):
    """`[(query, gold_doc_title, topic)]` — each query is answerable by exactly one document.

    The other query set, `queries`, marks a whole topic relevant. That measures the regime where
    you keep coming back to the same material, and it is the regime the Beta prior is built for —
    but it is also a regime in which a model can score well by memorising which six topics exist.
    Known-item is the opposite case and the harder one: the gold document is different for every
    query, so nothing document-level transfers from training to test, and a ranker has to have
    learned something about matching. Both are real; a vault contains both.
    """
    rng, docs = random.Random(seed), make(seed=seed, **kw)
    content = [(t, txt, tp) for t, txt, noise, tp in docs if not noise and tp != 'survey']
    out = []
    for i in range(n):
        title, text, tp = content[i % len(content)]
        rare = [w for w in TOPICS[tp]['rare'] if w in text]
        terms = TOPICS[tp]['terms']
        q = ' '.join(rng.sample(rare, min(2, len(rare))) + rng.sample(terms, 3))
        out.append((q, title, tp))
    return out
