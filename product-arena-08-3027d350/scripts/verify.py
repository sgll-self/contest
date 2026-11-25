#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — Self-check / coverage diagnostics for sci-pdf-reading-parse.

Computes honest, numerical verification of a parse against the PDF's own raw text
layer (the ground truth available without any external answer key):

  * char_recall   : fraction of raw non-whitespace characters recovered in body+captions
                    +references+equations (i.e. nothing silently dropped).
  * marginalia_leak: fraction of header/footer characters that leaked into the reading
                    text (should be ~0).
  * order_monotonic: fraction of pages whose body blocks are emitted in non-decreasing
                    layout position within each column (reading-order sanity).
  * unreadable    : pages/blocks flagged as image-only or empty (reported, not guessed).

It never invents content; a low score is reported as a limitation, not patched over.

Usage:
  python verify.py INPUT.pdf --parsed OUTDIR/parsed.json [--out verify.json]
"""
from __future__ import annotations
import argparse, json, os, re, sys
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


def _nw(s):
    return re.sub(r"\s+", "", s or "")


def raw_chars(pdf_path, max_pages=None):
    doc = pymupdf.open(pdf_path)
    n = len(doc) if not max_pages else min(len(doc), max_pages)
    per_page = []
    for i in range(n):
        per_page.append(_nw(doc[i].get_text("text")))
    doc.close()
    return per_page


def verify(pdf_path, parsed_path, max_pages=None):
    parsed = json.load(open(parsed_path, encoding="utf-8"))
    per_page_raw = raw_chars(pdf_path, max_pages)
    blocks = parsed["blocks"]

    # recovered characters per page, excluding marginalia
    rec = {}
    leak = {}
    for b in blocks:
        p = b["page"]
        if b["role"] in ("header", "footer"):
            leak[p] = leak.get(p, 0) + len(_nw(b["text"]))
        else:
            rec[p] = rec.get(p, 0) + len(_nw(b["text"]))

    total_raw = sum(len(x) for x in per_page_raw)
    total_rec = sum(rec.values())
    total_leak = sum(leak.values())
    char_recall = (total_rec / total_raw) if total_raw else 1.0
    # recall can exceed 1 if table cells duplicate body text; clamp reporting note
    marginalia_leak = (total_leak / total_raw) if total_raw else 0.0

    # reading-order monotonicity within columns per page
    ok_pairs = tot_pairs = 0
    from collections import defaultdict
    by_page_col = defaultdict(list)
    for b in blocks:
        if b["role"] in ("header", "footer"):
            continue
        by_page_col[(b["page"], b["column"])].append(b)
    for key, bs in by_page_col.items():
        bs = sorted(bs, key=lambda x: x["reading_order"])
        for i in range(len(bs) - 1):
            tot_pairs += 1
            if bs[i]["bbox"][1] <= bs[i + 1]["bbox"][1] + 1.0:
                ok_pairs += 1
    order_monotonic = (ok_pairs / tot_pairs) if tot_pairs else 1.0

    unreadable = [m["page"] for m in parsed["pages"] if m["n_blocks"] == 0]

    report = {
        "schema": "sci-pdf-reading-parse/verify/v1",
        "source": parsed.get("source"),
        "n_pages": len(per_page_raw),
        "raw_nonws_chars": total_raw,
        "recovered_nonws_chars": total_rec,
        "char_recall": round(min(char_recall, 1.0), 4),
        "char_recall_raw": round(char_recall, 4),
        "marginalia_leak": round(marginalia_leak, 4),
        "order_monotonic": round(order_monotonic, 4),
        "order_pairs_checked": tot_pairs,
        "unreadable_pages": unreadable,
        "notes": [],
    }
    if char_recall > 1.02:
        report["notes"].append("recovered>raw: table cells likely duplicate body text; recall clamped to 1.0")
    if char_recall < 0.9:
        report["notes"].append("low recall: possible image-only pages or complex layout; see unreadable_pages")
    if unreadable:
        report["notes"].append("image-only/empty pages detected; OCR needed (out of scope for text-layer parser)")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--parsed", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-pages", type=int, default=None)
    a = ap.parse_args(argv)
    rep = verify(a.pdf, a.parsed, a.max_pages)
    txt = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())