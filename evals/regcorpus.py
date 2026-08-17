"""Real regulatory documents, for measuring a detector against prose nobody wrote to be a test case.

The generated corpus in `evals/pii.py` has ground truth and can be resampled, which is what makes it
useful and also what makes it blind: every lookalike in it is one somebody thought of. Legislation
is the opposite. It is dense with numbers that are not identity (article references, money, legal
citations, dates), it is public, and it contains no real person's details, so the whole of it is a
labelled negative that nobody had to annotate.

Two sources, because neither alone is enough:

- Eight EU acts as PDFs, shipped in `litesearch/examples/pdfs` and read through `pdf_parse`, so the
  text carries the line breaks, hyphenation and header noise a real ingest carries.
- Three more downloaded: the EU AI Act, the GDPR, and 45 CFR Part 164. The last is US, and US legal
  citation (`42 U.S.C. 1302(a)`, `Pub. L. 104-191`, `110 Stat. 2033-2034`, `65 FR 82802`) is a
  different set of digit shapes from EU numbering.

    python -m evals.regcorpus          # fetch, extract, and report sizes
"""
import sys, re, json, html, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HERE = Path(__file__).parent
CORPUS = HERE/'corpus/regulatory'

#: `litesearch/examples/pdfs`, wherever it is. A sibling checkout is the usual case.
PDF_DIRS = [Path(p) for p in (
    HERE.parents[1]/'litesearch/examples/pdfs', HERE.parents[2]/'litesearch/examples/pdfs')]

#: name -> (url, how to turn the bytes into text). Mirrors, because eur-lex.europa.eu,
#: huggingface.co and the US government hosts are all outside what the sandbox can reach.
SOURCES = {
    'ai_act_2024_1689': (
        'https://raw.githubusercontent.com/bojkovski-cpu/ai-act-annotated/main/'
        'source/eur-lex/2026-05-19_L_202401689EN.000101.fmx.xml.html', 'html'),
    'gdpr_2016_679': (
        'https://raw.githubusercontent.com/coolharsh55/GDPRtEXT/master/gdpr.json', 'gdpr'),
    'hipaa_45cfr164': (
        'https://raw.githubusercontent.com/nebius/nebius-partner-cookbook/main/blueprints/'
        'sentinel-compliance-auditor/data/regulations/hipaa_45cfr_part164_2024.xml', 'html'),
}

UA = {'User-Agent': 'vishalakshi-eval/0.1 (+https://github.com/vedicreader/vishalakshi)'}


def _get(url, dest, tries=4):
    "Download with backoff. A partial file is removed rather than left to poison a later run."
    if dest.exists() and dest.stat().st_size > 1024: return dest
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                data = r.read()
            if len(data) < 1024: raise IOError(f'{len(data)} bytes')
            dest.write_bytes(data)
            return dest
        except Exception as e:
            print(f'  {dest.name}: {type(e).__name__} {e} (try {i+1})', flush=True)
            if dest.exists(): dest.unlink()
            time.sleep(2**i)
    return None


def untag(s:str) -> str:
    "Tags out, entities in, runs of spaces collapsed. Enough for a detector; not enough for a reader."
    s = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', s)
    s = re.sub(r'(?s)<[^>]+>', ' ', s)
    return re.sub(r'[ \t]+', ' ', html.unescape(html.unescape(s)))


def gdpr_text(d) -> str:
    "The titles and paragraph text out of GDPRtEXT's nested chapter/article/point JSON."
    out = []
    def walk(o):
        if isinstance(o, dict):
            out.extend(o[k] for k in ('title', 'text') if isinstance(o.get(k), str))
            for k, v in o.items():
                if k not in ('title', 'text'): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(d)
    return '\n\n'.join(out)


def pdf_dir():
    "Where the litesearch example PDFs are, or None."
    return next((d for d in PDF_DIRS if d.is_dir()), None)


def fetch():
    "Download what is missing. Returns name -> path for what is present afterwards."
    CORPUS.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, (url, _) in SOURCES.items():
        dest = CORPUS/f'{name}{Path(url).suffix or ".txt"}'
        if dest.exists(): pass
        elif _get(url, dest): print(f'  {dest.name}: {dest.stat().st_size//1024} KB')
        else: print(f'  FAILED {name} ({url})'); continue
        out[name] = dest
    return out


def _pdf_text(p:Path) -> str:
    "Pages joined, cached next to the PDF's name so a re-run does not re-parse."
    cache = CORPUS/f'{p.stem}.txt'
    if cache.exists(): return cache.read_text(errors='replace')
    from litesearch.data import pdf_parse
    txt = '\n\n'.join(pdf_parse(str(p)))
    CORPUS.mkdir(parents=True, exist_ok=True); cache.write_text(txt)
    return txt


def documents(pdfs=True, downloads=True):
    "`[(name, text)]` over every real regulatory document that is present, in a stable order."
    out = []
    if pdfs and (d := pdf_dir()):
        for p in sorted(d.glob('*.pdf')): out.append((p.stem, _pdf_text(p)))
    if downloads:
        for name, path in fetch().items():
            raw = path.read_text(errors='replace')
            out.append((name, gdpr_text(json.loads(raw)) if SOURCES[name][1] == 'gdpr' else untag(raw)))
    return out


if __name__ == '__main__':
    d = pdf_dir()
    print(f'PDFs: {d or "not found, tried " + " and ".join(map(str, PDF_DIRS))}')
    print('downloads:')
    docs = documents()
    print()
    for name, text in docs: print(f'  {name:34} {len(text):9,} chars')
    print(f'\n{len(docs)} documents, {sum(len(t) for _, t in docs):,} chars')
