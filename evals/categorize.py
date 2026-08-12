"""How often do the cues decide, and are they right when they do.

`extract.py` puts a cue table in front of the model and says the table is right often and cheaply.
Both halves need a number. The one that matters is not overall accuracy but accuracy *conditional
on `decisive`*: the table is allowed to be wrong about documents it declines to judge, because
those are the ones that go to a model. A table that were decisive on everything and right 80% of
the time would be worse than one decisive on half and right 99%, because the second one knows
which half.

The corpus is generated from templates, so these are documents of a shape the cues were designed
for. Read the numbers as a ceiling. A real inbox has documents that are three types at once.

    python -m evals.categorize
"""
import sys, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEMPLATES = {
'invoice': """INVOICE {n}
Invoice date: 14 March 2026        Due date: 13 April 2026
Bill to: Harrow Fabrication Ltd, 14 Threadneedle Buildings

Description                 Qty      Unit price      Amount
Machined bracket, 40mm       120         12.40      1,488.00
Surface treatment            120          3.10        372.00
                                       Subtotal      1,860.00
                                        VAT 20%        372.00
                                    Total due       2,232.00
Payment terms 30 days. Please quote the invoice number on remittance.""",

'receipt': """RECEIPT  no. {n}
Thank you for your purchase.
2 x Flat white                4.80
1 x Almond croissant          3.20
Subtotal                      8.00
Card ending 4417          PAID 8.00
14/03/2026 09:12   Till 3   Served by Amara""",

'purchase_order': """PURCHASE ORDER {n}
Supplier: Threadneedle Components   Ship to: Bay 4, Unit 12
Line  Part          Description             Qty   Unit    Delivery
1     BRK-40        Machined bracket        120   12.40   28 March
2     TRT-01        Surface treatment       120    3.10   28 March
Please confirm acceptance of this order within five working days.
Deliveries not matching this order will be refused at the gate.""",

'contract': """AGREEMENT dated 14 March 2026

BETWEEN: Harrow Fabrication Limited (the "Supplier")
AND: Threadneedle Components Limited (the "Customer")

1. DEFINITIONS
   1.1 "Services" means the services described in Schedule 1.
2. TERM
   2.1 This Agreement commences on the Effective Date and continues for
       twelve (12) months unless terminated in accordance with clause 8.
8. TERMINATION
   8.1 Either party may terminate for material breach not remedied
       within thirty (30) days of written notice.
IN WITNESS WHEREOF the parties have executed this Agreement.""",

'resume': """AMARA OKONKWO
London  |  amara.okonkwo@example.com

EXPERIENCE
Senior Metallurgist, Harrow Fabrication            2021 - present
  Led the move to induction hardening, cutting cycle time 22%.
Process Engineer, Threadneedle Components          2017 - 2021

EDUCATION
MEng Materials Science, University of Sheffield, 2017

SKILLS  Failure analysis, heat treatment, DoE, Python""",

'paper': """Late Chunking Preserves Context Across Passage Boundaries

Abstract. We show that embedding a document before splitting it retains
inter-passage context that naive chunking destroys. On three retrieval
benchmarks the method improves nDCG@10 by 0.04 on average.

1. Introduction
Dense retrieval systems split documents before embedding them [3, 7].

2. Method
We embed the full token sequence and pool per passage afterwards.

3. Results
Table 2 reports nDCG@10 across corpora.

References
[1] Karpukhin et al. Dense Passage Retrieval. EMNLP 2020.""",

'meeting_notes': """Weekly sync - 14 March
Present: Amara, Ravi, Jo, Kirsten. Apologies: Tom.

- Ravi walked through the hardening trial. Cycle time down, scrap flat.
- Jo raised the supplier audit slipping again. AGREED: Jo to escalate.
- ACTION: Amara to circulate the DoE plan before Thursday.
- ACTION: Kirsten to book the lab slot for week 14.
Next meeting 21 March, same time.""",

'email': """From: ravi.menon@example.com
To: amara.okonkwo@example.com
Subject: Re: hardening trial numbers
Date: Fri, 14 Mar 2026 09:41:00 +0000

Amara,

Thanks for sending these through. The scrap rate looks flat to me too.
Can we get one more run before I take it to the steering group?

Best,
Ravi

> On 13 Mar 2026, Amara wrote:
> Numbers attached. Cycle time is down 22%.""",

'report': """QUARTERLY OPERATIONS REPORT
Period: Q1 2026            Prepared by: Operations

EXECUTIVE SUMMARY
Output rose 8% against plan while scrap held at 2.1%. The hardening
trial concluded successfully and moves to full production in Q2.

1. PRODUCTION
Volumes by line are set out in Figure 1. Line 3 remains the constraint.

2. QUALITY
Scrap by cause is given in Table 3.

3. OUTLOOK
Capacity remains the limiting factor into Q3.
CONCLUSION: recommend approving the Line 3 investment case.""",

'documentation': """# Installing the toolchain

## Requirements
Python 3.12 or later, and a C compiler.

## Install
```
pip install harrow-toolkit
```

## Usage
Call `harrow.build()` with a path to your configuration file. See the
API reference for the full list of options.

## Troubleshooting
If the build fails with a linker error, check that `CC` is set.""",
}


#: Documents whose surface cues point at one type and whose actual type is another. `TYPE_SP` tells
#: the model "a paper about invoicing is a paper"; this is the set that checks whether the cue
#: table can do the same thing without one. Templated documents are the cue table's home ground,
#: so the clean set above is a ceiling and this is the number worth quoting.
CONFUSABLE = [
("""Automating Invoice Reconciliation with Weak Supervision

Abstract. Invoice matching is still largely manual. We present a method
that reconciles invoice line items against purchase orders using weak
supervision, and evaluate it on 40,000 invoices and purchase orders.

1. Introduction
An invoice arrives, a purchase order exists, and somebody matches them
by hand. Invoice total, invoice date, invoice number and VAT are the
fields that matter [4].

3. Results
We report precision and recall against a manually reconciled set.

References
[1] Ratner et al. Snorkel. VLDB 2017.""", 'paper'),

("""From: jo.harding@example.com
To: accounts@example.com
Subject: FW: INVOICE 88412 - please pay

Accounts,

Can you get this one paid today please, it is already past due.

Jo

> INVOICE 88412
> Invoice date: 2 March 2026     Due date: 1 April 2026
> Bill to: Harrow Fabrication Ltd
> Subtotal 1,860.00   VAT 20% 372.00   Total due 2,232.00
> Payment terms 30 days.""", 'email'),

("""Weekly sync - 21 March
Present: Amara, Ravi, Jo, Kirsten.

- Jo took us through the draft AGREEMENT with Threadneedle. Clause 8.1
  (termination for material breach, thirty days' notice) is the sticking
  point; legal want sixty. Clause 2.1 term of twelve (12) months is agreed.
- ACTION: Jo to send the redline back to their counsel by Thursday.
- ACTION: Ravi to confirm the delivery schedule feeding Schedule 1.
Next meeting 28 March.""", 'meeting_notes'),

("""# Writing a good resume for process engineering roles

This guide covers what hiring managers look for.

## Structure
Put EXPERIENCE before EDUCATION once you have three years behind you.
List each role as Title, Company, dates, then two lines of outcome.

## Skills
A SKILLS line should name tools, not adjectives: failure analysis, heat
treatment, DoE. Do not write "excellent communicator".

## Common mistakes
Listing a degree from 2017 above a senior role held since 2021.""", 'documentation'),

("""QUARTERLY OPERATIONS REPORT
Period: Q1 2026

EXECUTIVE SUMMARY
Contract renewals drove the quarter. The Threadneedle AGREEMENT was
signed on 14 March for a term of twelve (12) months, and two further
contracts are in redline. Output rose 8% against plan.

2. COMMERCIAL
Clause-level negotiation on termination (8.1) delayed two signings.

CONCLUSION: recommend approving the Line 3 investment case.""", 'report'),
]


def corpus(n_each=12, seed=0):
    "`[(text, doctype)]` — templated documents with the type known by construction."
    rng, out = random.Random(seed), []
    for t, body in TEMPLATES.items():
        for i in range(n_each):
            out.append((body.format(n=rng.randrange(10000, 99999)), t))
    return out


def _score(docs, guess_type):
    dec_right = dec_wrong = ind_right = 0
    per = {}
    for text, want in docs:
        g = guess_type(text)
        ok = g.doctype == want
        d = per.setdefault(want, [0, 0, 0]); d[2] += 1
        if g.decisive:
            d[0] += 1; d[1] += int(ok)
            dec_right += int(ok); dec_wrong += int(not ok)
        else: ind_right += int(ok)
    return dec_right, dec_wrong, ind_right, per


def run(n_each=12, seed=0):
    from vishalakshi.extract import guess_type

    dr, dw, ir, _ = _score(CONFUSABLE, guess_type)
    n_c = len(CONFUSABLE)
    print(f'confusable set: {n_c} documents whose cues point at the wrong type')
    print(f'  decisive on          {dr+dw}/{n_c}')
    print(f'  right when decisive  {dr}/{max(dr+dw,1)}')
    print(f'  right overall        {dr+ir}/{n_c}\n')

    docs = corpus(n_each, seed)
    dec_right, dec_wrong, ind_right, per = _score(docs, guess_type)
    n = len(docs)
    dec = dec_right + dec_wrong
    print(f'clean set: {n} templated documents across {len(TEMPLATES)} doctypes, no model\n')
    print(f'decisive on            {dec}/{n}  ({dec/n:.0%})')
    print(f'  right when decisive  {dec_right}/{dec}  ({dec_right/max(dec,1):.0%})')
    print(f'  right when not       {ind_right}/{max(n-dec,1)}  '
          f'({ind_right/max(n-dec,1):.0%})  <- these are the ones a model is asked about')
    print(f'overall accuracy       {(dec_right+ind_right)}/{n}  ({(dec_right+ind_right)/n:.0%})')
    print(f'\n{"doctype":<18}{"decisive":>10}{"right|dec":>12}{"n":>5}')
    for t, (d, r, tot) in sorted(per.items()):
        print(f'{t:<18}{d/tot:>10.0%}{(r/d if d else 0):>12.0%}{tot:>5}')
    return dict(n=n, decisive=dec, dec_right=dec_right, ind_right=ind_right)


if __name__ == '__main__':
    import warnings; warnings.filterwarnings('ignore')
    run()
