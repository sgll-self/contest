#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Internal coverage diagnostics for sci-pdf-reading-parse.

The PDF text layer is used as an internal reference, not as an independent
human-curated answer key. Metrics therefore diagnose extraction coverage and
layout consistency; they do not establish semantic correctness.

  * char_recall: recovered non-whitespace characters divided by raw characters
    outside the geometric header/footer bands. The unclamped value is retained.
  * marginalia_leak: fraction of raw top/bottom-band characters whose parsed
    block is still emitted as non-marginal content. Correct exclusion gives 0.
  * order_monotonic: within-column vertical-order sanity, not ground-truth
    reading-order accuracy.
  * unreadable_pages: pages with no extracted text blocks.

When --max-pages is omitted, verification follows the page count recorded in
parsed.json so that a truncated parse is not compared with the whole PDF.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict

try:
    import pymupdf
except ImportError:  # pragma: no cover
    import fitz as pymupdf


def _nw(text):
    return re.sub(r"\s+", "", text or "")


def _raw_block_text(block):
    lines = []
    for line in block.get("lines", []):
        lines.append("".join(span.get("text", "") for span in line.get("spans", [])))
    return "\n".join(lines)


def raw_page_data(pdf_path, max_pages=None):
    doc = pymupdf.open(pdf_path)
    try:
        n_pages = len(doc) if not max_pages else min(len(doc), max_pages)
        pages = []
        for index in range(n_pages):
            page = doc[index]
            page_height = page.rect.height
            raw_parts = []
            raw_chars = 0
            content_chars = 0
            marginalia_blocks = {}
            for block_index, block in enumerate(page.get_text("dict").get("blocks", [])):
                if block.get("type") != 0:
                    continue
                text = _raw_block_text(block)
                nonws_count = len(_nw(text))
                if not nonws_count:
                    continue
                raw_parts.append(text)
                raw_chars += nonws_count
                x0, y0, x1, y1 = block.get("bbox", [0, 0, 0, 0])
                is_margin = y1 < page_height * 0.08 or y0 > page_height * 0.92
                block_id = f"p{index + 1}_b{block_index}"
                if is_margin:
                    marginalia_blocks[block_id] = nonws_count
                else:
                    content_chars += nonws_count
            pages.append({
                "page": index + 1,
                "raw_text": "\n".join(raw_parts),
                "raw_nonws_chars": raw_chars,
                "content_nonws_chars": content_chars,
                "marginalia_blocks": marginalia_blocks,
            })
        return pages
    finally:
        doc.close()


def verify(pdf_path, parsed_path, max_pages=None):
    with open(parsed_path, encoding="utf-8") as handle:
        parsed = json.load(handle)
    if max_pages is None:
        max_pages = len(parsed.get("pages", [])) or None
    page_data = raw_page_data(pdf_path, max_pages)
    blocks = parsed["blocks"]
    block_by_id = {block["id"]: block for block in blocks}

    recovered = {}
    for block in blocks:
        if block["role"] not in ("header", "footer"):
            page = block["page"]
            recovered[page] = recovered.get(page, 0) + len(_nw(block["text"]))

    total_raw = sum(page["raw_nonws_chars"] for page in page_data)
    total_content = sum(page["content_nonws_chars"] for page in page_data)
    total_recovered = sum(recovered.values())
    total_marginalia = sum(sum(page["marginalia_blocks"].values()) for page in page_data)
    leaked_marginalia = 0
    for page in page_data:
        for block_id, char_count in page["marginalia_blocks"].items():
            parsed_block = block_by_id.get(block_id)
            if parsed_block is not None and parsed_block["role"] not in ("header", "footer"):
                leaked_marginalia += char_count

    char_recall = total_recovered / total_content if total_content else 1.0
    marginalia_leak = leaked_marginalia / total_marginalia if total_marginalia else 0.0

    ok_pairs = 0
    total_pairs = 0
    by_page_column = defaultdict(list)
    for block in blocks:
        if block["role"] not in ("header", "footer"):
            by_page_column[(block["page"], block["column"])].append(block)
    for column_blocks in by_page_column.values():
        column_blocks = sorted(column_blocks, key=lambda block: block["reading_order"])
        for index in range(len(column_blocks) - 1):
            total_pairs += 1
            if column_blocks[index]["bbox"][1] <= column_blocks[index + 1]["bbox"][1] + 1.0:
                ok_pairs += 1
    order_monotonic = ok_pairs / total_pairs if total_pairs else 1.0
    unreadable = [meta["page"] for meta in parsed["pages"] if meta["n_blocks"] == 0]

    report = {
        "schema": "sci-pdf-reading-parse/verify/v2",
        "source": parsed.get("source"),
        "n_pages": len(page_data),
        "raw_nonws_chars": total_raw,
        "content_nonws_chars": total_content,
        "recovered_nonws_chars": total_recovered,
        "char_recall": round(min(char_recall, 1.0), 4),
        "char_recall_raw": round(char_recall, 4),
        "raw_marginalia_chars": total_marginalia,
        "leaked_marginalia_chars": leaked_marginalia,
        "marginalia_leak": round(marginalia_leak, 4),
        "order_monotonic": round(order_monotonic, 4),
        "order_pairs_checked": total_pairs,
        "unreadable_pages": unreadable,
        "reference_type": "internal PDF text-layer diagnostic; not an independent ground-truth score",
        "notes": [],
    }
    if char_recall > 1.02:
        report["notes"].append("recovered>content raw: possible duplicate blocks or over-inclusion; inspect char_recall_raw")
    if char_recall < 0.9:
        report["notes"].append("low recall: possible image-only pages, dropped blocks or complex layout")
    if marginalia_leak > 0:
        report["notes"].append("geometric header/footer-band text remains in emitted content")
    if unreadable:
        report["notes"].append("image-only/empty pages detected; OCR needed (out of scope for text-layer parser)")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--parsed", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args(argv)
    report = verify(args.pdf, args.parsed, args.max_pages)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
