"""Real regulatory documents, for measuring a detector against prose nobody wrote to be a test case.

The generated corpus in `evals/pii.py` has ground truth and can be resampled, which is what makes it
useful and also what makes it blind: every lookalike in it is one somebody thought of. Legislation
is the opposite. It is dense with numbers that are not identity (article references, money, legal
citations, dates), it is public, and it contains no real person's details, so the whole of it is a
labelled negative that nobody had to annotate.

Five jurisdictions, because a detector written against one is a detector tuned to its digit shapes:

- **EU**: eight acts as PDFs, shipped in `litesearch/examples/pdfs` and read through `pdf_parse`, so
  the text carries the line breaks, hyphenation and header noise a real ingest carries, plus the AI
  Act and the GDPR.
- **US**: 45 CFR Part 164, whose citation style (`42 U.S.C. 1302(a)`, `Pub. L. 104-191`,
  `110 Stat. 2033-2034`, `65 FR 82802`) is a different set of digit shapes from EU numbering.
- **Australia**: the Privacy Act 1988 and the Telecommunications Act 1997. The second is a statute
  about telephone numbering, which is the most adversarial thing available to a phone pattern.
- **India**: the Penal Code, the Criminal Procedure Code, the Evidence Act and the DPDP Act 2023.
  Indian digit grouping is 2-2-3 (`12,34,567`), not 3-3-3, and rupee amounts run to lakhs and crores.
- **Thailand**: the PDPA (B.E. 2562), in Thai script and Thai numerals, which is the only document
  here that the patterns cannot read at all.

Southeast Asia is one statute rather than four. Singapore Statutes Online, AGC Malaysia and the
Philippine Official Gazette are all outside what the sandbox can reach, and no GitHub mirror of
their English text turned up.

    python -m evals.regcorpus          # fetch, extract, and report sizes
"""
import sys, re, json, html, time, shutil, subprocess, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HERE = Path(__file__).parent
CORPUS = HERE/'corpus/regulatory'

#: `litesearch/examples/pdfs`, wherever it is. A sibling checkout is the usual case.
PDF_DIRS = [Path(p) for p in (
    HERE.parents[1]/'litesearch/examples/pdfs', HERE.parents[2]/'litesearch/examples/pdfs')]

_GH = 'https://raw.githubusercontent.com/'

#: name -> (url, how to turn the bytes into text). Mirrors throughout, because eur-lex.europa.eu,
#: huggingface.co, legislation.gov.au, indiacode.nic.in and the US government hosts are all outside
#: what the sandbox can reach. Every one of these is a copy of a public act, not the register.
SOURCES = {
    'eu_ai_act_2024_1689': (
        f'{_GH}bojkovski-cpu/ai-act-annotated/main/'
        'source/eur-lex/2026-05-19_L_202401689EN.000101.fmx.xml.html', 'html'),
    'eu_gdpr_2016_679': (f'{_GH}coolharsh55/GDPRtEXT/master/gdpr.json', 'gdpr'),
    'us_hipaa_45cfr164': (
        f'{_GH}nebius/nebius-partner-cookbook/main/blueprints/'
        'sentinel-compliance-auditor/data/regulations/hipaa_45cfr_part164_2024.xml', 'html'),
    'au_privacy_act_1988': (
        f'{_GH}xlfe/gitlaw-au/master/acts/current/p/privacy%20act%201988.md', 'html'),
    'au_telecommunications_act_1997': (
        f'{_GH}xlfe/gitlaw-au/master/acts/current/t/telecommunications%20act%201997.md', 'html'),
    'in_penal_code_1860': (f'{_GH}civictech-India/Indian-Law-Penal-Code-Json/main/ipc.json', 'india'),
    'in_crpc_1973': (f'{_GH}civictech-India/Indian-Law-Penal-Code-Json/main/crpc.json', 'india'),
    'in_evidence_act_1872': (f'{_GH}civictech-India/Indian-Law-Penal-Code-Json/main/iea.json', 'india'),
}

#: Statutes published one file per section. Cloned rather than fetched, because codeload tarballs
#: are 403 through the sandbox proxy and ninety raw requests is not a fetch, it is a crawl.
CLONES = {
    'in_dpdp_act_2023': ('https://github.com/rahulmatthan/dpdp.git', 'src/content'),
    'th_pdpa_2562': ('https://github.com/sidataplus/pdpa.git', 'content'),
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


_FRONT = re.compile(r'\A---\n.*?\n---\n', re.S)

def india_text(d) -> str:
    "Section titles and bodies out of the Indian-Law-Penal-Code-Json list of sections."
    return '\n\n'.join(f"{r.get('section_title') or ''}\n{r.get('section_desc') or ''}".strip()
                       for r in d if isinstance(r, dict))


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


def clone():
    "Shallow-clone the one-file-per-section statutes. Returns name -> the directory to read."
    out = {}
    for name, (url, sub) in CLONES.items():
        repo = CORPUS/name
        if not (repo/sub).is_dir():
            if repo.exists(): shutil.rmtree(repo)
            CORPUS.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(['git', 'clone', '-q', '--depth', '1', url, str(repo)],
                               capture_output=True, text=True)
            if r.returncode: print(f'  FAILED {name} ({r.stderr.strip().splitlines()[-1:]})'); continue
            print(f'  {name}: cloned')
        out[name] = repo/sub
    return out


def _section_text(d:Path) -> str:
    "Every markdown file under `d`, front matter stripped, in path order."
    return '\n\n'.join(untag(_FRONT.sub('', p.read_text(errors='replace')))
                       for p in sorted(d.rglob('*.md')))


def _pdf_text(p:Path) -> str:
    "Pages joined, cached next to the PDF's name so a re-run does not re-parse."
    cache = CORPUS/f'{p.stem}.txt'
    if cache.exists(): return cache.read_text(errors='replace')
    from litesearch.data import pdf_parse
    txt = '\n\n'.join(pdf_parse(str(p)))
    CORPUS.mkdir(parents=True, exist_ok=True); cache.write_text(txt)
    return txt


#: How each source's raw bytes become text.
READ = {'gdpr': lambda s: gdpr_text(json.loads(s)), 'india': lambda s: india_text(json.loads(s)),
        'html': lambda s: untag(s)}


def documents(pdfs=True, downloads=True):
    "`[(name, text)]` over every real regulatory document that is present, in a stable order."
    out = []
    if pdfs and (d := pdf_dir()):
        for p in sorted(d.glob('*.pdf')): out.append((f'eu_{p.stem}', _pdf_text(p)))
    if downloads:
        for name, path in fetch().items():
            out.append((name, READ[SOURCES[name][1]](path.read_text(errors='replace'))))
        for name, d in clone().items(): out.append((name, _section_text(d)))
    return sorted(out)


if __name__ == '__main__':
    d = pdf_dir()
    print(f'PDFs: {d or "not found, tried " + " and ".join(map(str, PDF_DIRS))}')
    docs = documents()
    print()
    for name, text in docs: print(f'  {name:34} {len(text):9,} chars')
    print(f'\n{len(docs)} documents, {sum(len(t) for _, t in docs):,} chars')
