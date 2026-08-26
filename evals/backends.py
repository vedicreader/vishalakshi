"""The two learned PII backends, kept here and out of the library.

Neither wins the gate. `evals/pii_model.py` measures both against `rahasya` and the patterns
win on precision, on recall and by two orders of magnitude on speed. So `pii.py` ships the
arithmetic and these live in `evals/`, where a number can be attached to them without the wheel
carrying an `onnxruntime` import or a gigabyte of weights.

  onnx    `onnx-community/piiranha-v1-detect-personal-information-ONNX`, DeBERTa-v3, fp32 and int8
  litert  `litert-community/LFM2.5-Encoder-350M-PII-Detector`, 350M tflite, fp16 and wi8fc

Both return spans in the shape `pii_spans` uses, `(start, end, kind, text)`, with model labels folded
onto `rahasya.PATTERNS` kinds, so a caller can union them with `pii_spans` output and measure what that
did. `litert_spans` collapses BIOES tags per entity, because a raw argmax over byte-BPE tokens
fragments every span it finds.

    pip install onnxruntime ai-edge-litert tokenizers huggingface-hub
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastcore.all import L

#: Kinds these models emit that no pattern has. Deliberately outside `rahasya.IDENTIFYING`: a caller
#: that wants them to gate has to say so.
MODEL_ONLY = frozenset({'idnum', 'taxnum', 'city', 'username', 'mac', 'gps'})

#: What a union with the patterns should take from a model, and the only place either one earns its
#: weights. Unioning every kind they emit costs precision 0.996 -> 0.845 and buys no recall.
MODEL_ADDS = frozenset({'person'})


PII_ONNX, PII_ONNX_FILE = 'onnx-community/piiranha-v1-detect-personal-information-ONNX', 'onnx/model.onnx'
MODEL_CHARS = 1400   #: chars per window, kept under the 512-token limit with room for long digit runs

#: piiranha label -> our kind. `city` and `username` are reportable and do not gate: it calls
#: `London` a city and the local part of an address a username.
MODEL_KINDS = {'I-EMAIL': 'email', 'I-CREDITCARDNUMBER': 'card', 'I-SOCIALNUM': 'ssn',
               'I-TELEPHONENUM': 'phone', 'I-DATEOFBIRTH': 'dob', 'I-ACCOUNTNUM': 'account',
               'I-IDCARDNUM': 'idnum', 'I-TAXNUM': 'taxnum', 'I-DRIVERLICENSENUM': 'licence',
               'I-PASSWORD': 'secret', 'I-STREET': 'address', 'I-BUILDINGNUM': 'address',
               'I-ZIPCODE': 'address', 'I-CITY': 'city', 'I-GIVENNAME': 'person',
               'I-SURNAME': 'person', 'I-USERNAME': 'username'}
_MODEL = {}

def _model(repo:str=None, fn:str=None):
    "The ONNX session, tokenizer and label table, loaded once. Downloads ~1.1 GB the first time."
    repo, fn = repo or PII_ONNX, fn or PII_ONNX_FILE
    if (repo, fn) in _MODEL: return _MODEL[(repo, fn)]
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise ImportError('needs `pip install onnxruntime tokenizers huggingface-hub`') from e
    cfg = json.loads(Path(hf_hub_download(repo, 'config.json')).read_text())
    tok = Tokenizer.from_file(hf_hub_download(repo, 'tokenizer.json'))
    sess = ort.InferenceSession(hf_hub_download(repo, fn),
                                providers=['CPUExecutionProvider'])
    labels = [cfg['id2label'][str(i)] for i in range(len(cfg['id2label']))]
    _MODEL[(repo, fn)] = (sess, tok, labels)
    return _MODEL[(repo, fn)]

def _windows(text:str, mx:int=MODEL_CHARS) -> list:
    "`(offset, chunk)` on line then space boundaries, so a span is never cut in half mid-number."
    out, i = [], 0
    while i < len(text):
        j = min(i + mx, len(text))
        if j < len(text):
            cut = max(text.rfind('\n', i + mx//2, j), text.rfind(' ', i + mx//2, j))
            if cut > i: j = cut
        out.append((i, text[i:j]))
        i = j if j > i else i + mx
    return out


def model_spans(text:str,            # what to scan
                thresh:float=0.5,    # softmax floor for a token to count
                repo:str=None,       # ONNX repo; None -> `PII_ONNX`
                fn:str=None,         # file within it; None -> `PII_ONNX_FILE`
) -> L:
    "The classifier's spans, as `(start, end, kind, text)`. Adjacent tokens of one kind are merged."
    import numpy as np
    sess, tok, labels = _model(repo, fn)
    text, out = str(text or ''), []
    for off, chunk in _windows(text):
        enc = tok.encode(chunk)
        ids = np.asarray([enc.ids], dtype=np.int64)
        lg = sess.run(None, {'input_ids': ids, 'attention_mask': np.ones_like(ids)})[0][0]
        p = np.exp(lg - lg.max(-1, keepdims=True)); p /= p.sum(-1, keepdims=True)
        best, cur = p.argmax(-1), None
        for (a, b), i, row in zip(enc.offsets, best, p):
            if b <= a: continue                          # [CLS]/[SEP] carry an empty offset
            kind = MODEL_KINDS.get(labels[i]) if row[i] >= thresh else None
            a, b = off + a, off + b
            # one gap character absorbs the space or hyphen inside `4111 1111` and `Elm Street`
            if cur and kind == cur[2] and a - cur[1] <= 1: cur[1] = b
            else:
                if cur: out.append(tuple(cur))
                cur = [a, b, kind] if kind else None
        if cur: out.append(tuple(cur))
    return L([(a, b, k, text[a:b].strip()) for a, b, k in out if text[a:b].strip()])


#: The `.tflite` encoder, its two builds, and the fixed sequence lengths its signatures expose.
PII_LITERT = 'litert-community/LFM2.5-Encoder-350M-PII-Detector'
PII_LITERT_FILE = 'LFM2.5-Encoder-350M-PII-Detector_fp16.tflite'
LITERT_SEQ = 512

#: Its 28 types, folded onto our kinds. `org.company_name` and the special categories are dropped:
#: a company is not a person and this module does not gate on politics or religion.
LITERT_KINDS = {'contact.address': 'address', 'contact.email': 'email', 'contact.phone': 'phone',
                'contact.postal_code': 'address', 'contact.ip_address': 'ip',
                'credential.api_key': 'secret', 'device.mac_address': 'mac',
                'financial.bank_account': 'account', 'financial.credit_card': 'card',
                'financial.iban': 'iban', 'financial.swift_bic': 'account',
                'healthcare.medical_record': 'medical', 'identity.date_of_birth': 'dob',
                'identity.drivers_license': 'licence', 'identity.national_id': 'idnum',
                'identity.passport': 'passport', 'identity.person_name': 'person',
                'identity.ssn': 'ssn', 'legal.case_number': 'idnum',
                'location.gps_coordinates': 'gps', 'online.username': 'username'}
_LITERT = {}

def _litert(repo:str=None, fn:str=None, seq:int=LITERT_SEQ):
    "The tflite signature runner, tokenizer and label table, loaded once."
    repo, fn = repo or PII_LITERT, fn or PII_LITERT_FILE
    if (repo, fn, seq) in _LITERT: return _LITERT[(repo, fn, seq)]
    try:
        from ai_edge_litert.interpreter import Interpreter
        from tokenizers import Tokenizer
        from huggingface_hub import hf_hub_download
    except ImportError as e:
        raise ImportError('needs `pip install ai-edge-litert tokenizers huggingface-hub`') from e
    tok = Tokenizer.from_file(hf_hub_download(repo, 'tokenizer.json'))
    schema = json.loads(Path(hf_hub_download(repo, 'label_schema.json')).read_text())
    run = Interpreter(model_path=hf_hub_download(repo, fn)).get_signature_runner(f'pii_{seq}')
    labels = {int(i): n for i, n in schema['id2label'].items()}
    _LITERT[(repo, fn, seq)] = (run, tok, labels, schema['num_labels'])
    return _LITERT[(repo, fn, seq)]

def litert_spans(text:str,        # what to scan
                 repo:str=None,   # HF repo; None -> `PII_LITERT`
                 fn:str=None,     # build within it; None -> `PII_LITERT_FILE`
                 seq:int=LITERT_SEQ,  # 128 or 512, the two signatures the model exposes
) -> L:
    "`litert-community/LFM2.5` spans, as `(start, end, kind, text)`. BIOES tags collapsed per entity."
    import numpy as np
    run, tok, labels, n_lab = _litert(repo, fn, seq)
    text, out = str(text or ''), []
    for off, chunk in _windows(text, seq * 2):
        enc = tok.encode(chunk)
        ids = np.zeros((1, seq), np.int32); am = np.zeros((1, seq), np.int32)
        n = min(len(enc.ids), seq)
        ids[0, :n] = enc.ids[:n]; am[0, :n] = 1
        tags = run(input_ids=ids, attention_mask=am)['output_0'][0, :n, :n_lab].argmax(-1)
        cur = None
        for (a, b), t in zip(enc.offsets[:n], tags):
            if b <= a: continue
            lab = labels[int(t)]
            kind = LITERT_KINDS.get(lab.split('-', 1)[1]) if lab != 'O' else None
            a, b = off + a, off + b
            if cur and kind == cur[2] and a - cur[1] <= 1: cur[1] = b
            else:
                if cur: out.append(tuple(cur))
                cur = [a, b, kind] if kind else None
        if cur: out.append(tuple(cur))
    return L([(a, b, k, text[a:b].strip()) for a, b, k in out if text[a:b].strip()])
