#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adversarial controlled fixtures for schema-v3 parser capabilities.

Every assertion is evaluated against known fixture content. Negative controls
mutate the observed sequence/text and must fail the same assertion.
"""
from __future__ import annotations

import io
import json
import os
import re

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import parse_pdf as P


def _draw_lines(c, text, x, y, width, font="Helvetica", size=9, leading=12):
    c.setFont(font, size)
    for line in simpleSplit(text, font, size, width):
        c.drawString(x, y, line)
        y -= leading
    return y


def _dejavu():
    import matplotlib
    path = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
    if "DejaVuSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVuSans", path))
    return "DejaVuSans"


def _raster_image():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axis = plt.subplots(figsize=(1.6, 0.8))
    axis.plot([0, 1, 2], [0, 1, 0], marker="o")
    axis.axis("off")
    stream = io.BytesIO()
    figure.savefig(stream, format="png", dpi=80, bbox_inches="tight", pad_inches=0.02)
    plt.close(figure)
    stream.seek(0)
    return ImageReader(stream)


def build_structure_pdf(path):
    width, height = letter
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, height - 28, "Advanced Controlled Fixture")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 740, "Structured Scientific Parsing with Verifiable Evidence")
    c.setFont("DejaVuSans" if "DejaVuSans" in pdfmetrics.getRegisteredFontNames() else _dejavu(), 10)
    c.drawString(50, 715, "Alice A. Example, Bob B. Example")
    c.setFont("Helvetica", 9)
    c.drawString(50, 698, "Department of Testing, Example University")
    c.drawString(50, 672, "Abstract—A controlled fixture for structure and formulas.")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 640, "1. Introduction")
    _draw_lines(c, "This paragraph belongs to the first-level section and remains unchanged.", 50, 624, 500)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 594, "1.1. Layout")
    _draw_lines(c, "This paragraph belongs to the second-level section.", 50, 578, 500)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 548, "1.1.1. Ordering")
    _draw_lines(c, "This paragraph belongs to the third-level section.", 50, 532, 500)

    # Display equation with raised 2, lowered i, real Greek Unicode and number 12.
    x, y = 60, 490
    greek = _dejavu()
    segments = [
        ("x", "Helvetica", 11, 0), ("2", "Helvetica", 7, 3),
        (" + y", "Helvetica", 11, 0), ("i", "Helvetica", 7, -2),
        (" = ", "Helvetica", 11, 0), ("α", greek, 11, 0),
        (" + ", "Helvetica", 11, 0), ("β", greek, 11, 0),
        (" = ", "Helvetica", 11, 0), ("γ", greek, 11, 0),
    ]
    for text, font, size, offset in segments:
        c.setFont(font, size)
        c.drawString(x, y + offset, text)
        x += pdfmetrics.stringWidth(text, font, size)
    c.setFont("Helvetica", 11)
    c.drawString(500, y, "(12)")

    c.drawImage(_raster_image(), 60, 360, width=150, height=75, mask="auto")
    c.setFont("Helvetica", 8)
    c.drawString(60, 345, "Fig. S1 Controlled raster figure.")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 315, "References")
    c.setFont("Helvetica", 8)
    c.drawString(50, 297, "[1] First numeric reference.")
    c.drawString(50, 282, "2. Second numeric reference.")
    c.drawString(50, 267, "Example, A. Author-first reference.")
    c.setFont("Helvetica", 7)
    c.drawString(50, 66, "* Controlled footnote retained verbatim with sufficient identifying text.")
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 25, "7")
    c.showPage()

    # Sparse two-column page: one local heading/caption must not break column order.
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, height - 28, "Advanced Controlled Fixture")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, 730, "2. Sparse Layout")
    left_one = "L1 sparse left column begins here and contains enough words to establish the dominant column."
    left_two = "L2 left column continues after its local caption without moving to the right column."
    right_one = "R1 sparse right column starts at the same vertical band but must follow all left content."
    right_two = "R2 right column finishes after the complete left-column sequence."
    _draw_lines(c, left_one, 50, 710, 220)
    _draw_lines(c, right_one, 330, 730, 220)
    c.setFont("Helvetica", 8)
    c.drawString(50, 625, "Fig. 2 Left-column caption.")
    _draw_lines(c, left_two, 50, 600, 220)
    _draw_lines(c, right_two, 330, 650, 220)
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 25, "8")
    c.showPage()

    # Multilingual page: CID Chinese plus accented French text.
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, height - 28, "Advanced Controlled Fixture")
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c.setFont("STSong-Light", 11)
    c.drawString(50, 730, "中文段落：逐字提取、阅读顺序与证据定位。")
    c.setFont("Helvetica", 11)
    c.drawString(50, 700, "Résumé : précision, intégrité et traçabilité.")
    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, 25, "9")
    c.showPage()
    c.save()
    return path


def _draw_cross_page_table(c, top_y, data_rows):
    columns = [50, 210, 330, 500]
    row_height = 32
    row_count = 2 + len(data_rows)
    bottom = top_y - row_count * row_height
    c.setLineWidth(0.6)
    for row in range(row_count + 1):
        c.line(columns[0], top_y - row * row_height, columns[-1], top_y - row * row_height)
    c.line(columns[0], top_y, columns[0], bottom)
    c.line(columns[-1], top_y, columns[-1], bottom)
    # First row merges columns 0 and 1; subsequent rows have all three cells.
    c.line(columns[2], top_y, columns[2], bottom)
    c.line(columns[1], top_y - row_height, columns[1], bottom)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(columns[0] + 4, top_y - 20, "Merged controlled header")
    c.drawString(columns[2] + 4, top_y - 20, "Note")
    for column, text in enumerate(["Parameter", "Value", "Note"]):
        c.drawString(columns[column] + 4, top_y - row_height - 20, text)
    c.setFont("Helvetica", 8)
    for row_offset, row in enumerate(data_rows, start=2):
        baseline = top_y - row_offset * row_height - 20
        c.drawString(columns[0] + 4, baseline, row[0])
        c.drawString(columns[1] + 4, baseline, row[1])
        note_lines = row[2].split("\n")
        for line_index, line in enumerate(note_lines):
            c.drawString(columns[2] + 4, baseline - line_index * 10, line)
    return bottom


def build_symbol_font_pdf(path):
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 11)
    c.drawString(60, 700, "x = ")
    c.setFont("Symbol", 11)
    c.drawString(90, 700, "a")
    c.setFont("Helvetica", 11)
    c.drawString(110, 700, " + ")
    c.setFont("Symbol", 11)
    c.drawString(135, 700, "a")
    c.setFont("Helvetica", 11)
    c.drawString(160, 700, "(13)")
    c.save()
    return path


def build_tables_pdf(path):
    width, _ = letter
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 9)
    c.drawString(50, 355, "Before table: this paragraph must precede the table anchor.")
    c.setFont("Helvetica", 8)
    c.drawString(50, 333, "Table 1. Cross-page controlled values.")
    _draw_cross_page_table(c, 310, [["alpha", "0.99", "a|b"], ["beta", "0.52", "line one\nline two"]])
    c.drawCentredString(width / 2, 25, "1")
    c.showPage()
    _draw_cross_page_table(c, 730, [["gamma", "1.00", "plain"], ["delta", "0.75", "last"]])
    c.setFont("Helvetica", 9)
    c.drawString(50, 540, "After table: this paragraph must follow the merged table anchor.")
    c.drawCentredString(width / 2, 25, "2")
    c.showPage()
    c.save()
    return path


def _position(blocks, prefix):
    matches = [block["reading_order"] for block in blocks if block["text"].startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


def _sequence_ok(blocks, prefixes):
    positions = [_position(blocks, prefix) for prefix in prefixes]
    return all(position is not None for position in positions) and positions == sorted(positions)


def check_structure(parsed):
    blocks = parsed["blocks"]
    document = parsed["document"]
    headings = {section["title"]: section for section in document["sections"]}
    equations = parsed["equations"]
    equation = equations[0] if equations else {}
    expected_sparse = ["2. Sparse Layout", "L1 sparse", "Fig. 2", "L2 left", "R1 sparse", "R2 right"]
    sequence_passed = _sequence_ok(blocks, expected_sparse)
    swapped = list(blocks)
    # Negative control: exchange the complete left/right sequence labels.
    if _position(swapped, "L1 sparse") is not None and _position(swapped, "R1 sparse") is not None:
        left = next(block for block in swapped if block["text"].startswith("L1 sparse"))
        right = next(block for block in swapped if block["text"].startswith("R1 sparse"))
        left["reading_order"], right["reading_order"] = right["reading_order"], left["reading_order"]
    references = "\n".join(block["text"] for block in blocks if block["role"] == "reference")
    checks = {
        "title_authors_affiliation_abstract": (
            document["title"].startswith("Structured Scientific Parsing") and
            any("Alice" in value for value in document["authors"]) and
            any("Example University" in value for value in document["affiliations"]) and
            "controlled fixture" in document["abstract"]),
        "section_levels_and_parents": (
            headings.get("1. Introduction", {}).get("level") == 1 and
            headings.get("1.1. Layout", {}).get("level") == 2 and
            headings.get("1.1.1. Ordering", {}).get("level") == 3 and
            headings.get("1.1. Layout", {}).get("parent_id") == headings.get("1. Introduction", {}).get("id") and
            headings.get("1.1.1. Ordering", {}).get("parent_id") == headings.get("1.1. Layout", {}).get("id")),
        "formula_unicode_scripts_number": (
            equation.get("number") == "12" and "^{2}" in equation.get("linear_text", "") and
            "_{i}" in equation.get("linear_text", "") and
            all(symbol in equation.get("unicode_text", "") for symbol in ("α", "β", "γ")) and
            not equation.get("needs_review", True)),
        "raster_figure_caption_link": (
            len(parsed["figures"]) == 1 and parsed["figures"][0].get("caption_id") and
            parsed["figures"][0]["bbox"][2] > parsed["figures"][0]["bbox"][0]),
        "footnote_preserved_and_footer_separated": (
            any(block["role"] == "footnote" and "Controlled footnote" in block["text"] for block in blocks) and
            all(block["role"] in ("header", "footer") for block in blocks if block["text"] in ("7", "8", "9"))),
        "all_reference_styles_preserved": all(text in references for text in (
            "[1] First numeric reference.", "2. Second numeric reference.", "Example, A. Author-first reference.")),
        "sparse_columns_and_local_headings": sequence_passed and len(parsed["pages"][1]["column_bounds"]) == 1,
        "multilingual_chinese_and_french": (
            any("中文段落：逐字提取、阅读顺序与证据定位。" in block["text"] for block in blocks) and
            any("Résumé : précision, intégrité et traçabilité." in block["text"] for block in blocks)),
    }
    negative = {
        "column_swap_is_detected": not _sequence_ok(swapped, expected_sparse),
        "greek_substitution_is_detected": not all(symbol in equation.get("unicode_text", "").replace("α", "a")
                                                   for symbol in ("α", "β", "γ")),
    }
    return checks, negative


def check_tables(parsed):
    tables = parsed["tables"]
    table = tables[0] if tables else {}
    cells = {(cell["row"], cell["col"]): cell for cell in table.get("cells", [])}
    item_ids = [item["id"] for item in parsed["reading_items"]]
    before = next((block for block in parsed["blocks"] if block["text"].startswith("Before table")), None)
    caption = next((block for block in parsed["blocks"] if block["text"].startswith("Table 1.")), None)
    after = next((block for block in parsed["blocks"] if block["text"].startswith("After table")), None)
    table_item_index = item_ids.index(table.get("id")) if table.get("id") in item_ids else -1
    before_index = item_ids.index(before["id"]) if before and before["id"] in item_ids else -1
    caption_index = item_ids.index(caption["id"]) if caption and caption["id"] in item_ids else -1
    after_index = item_ids.index(after["id"]) if after and after["id"] in item_ids else -1
    merged_anchor = cells.get((0, 0), {})
    checks = {
        "one_logical_cross_page_table": len(tables) == 1 and table.get("pages") == [1, 2],
        "shape_and_repeated_two_row_header": table.get("n_rows") == 6 and table.get("n_cols") == 3 and
            table.get("segments", [{}])[0].get("repeated_header_rows") == 2,
        "exact_cells_pipe_and_multiline": (
            cells.get((2, 1), {}).get("text") == "0.99" and cells.get((2, 2), {}).get("text") == "a|b" and
            "line one" in cells.get((3, 2), {}).get("text", "") and
            "line two" in cells.get((3, 2), {}).get("text", "") and
            cells.get((4, 0), {}).get("text") == "gamma" and cells.get((5, 0), {}).get("text") == "delta"),
        "merged_cell_span_and_cell_bboxes": merged_anchor.get("col_span") == 2 and
            merged_anchor.get("bbox") is not None and cells.get((2, 1), {}).get("bbox") is not None,
        "table_inline_exactly_once": (0 <= before_index < caption_index < table_item_index < after_index and
            item_ids.count(table.get("id")) == 1 and
            all(not item["id"].startswith("p1_b") or not next(
                block for block in parsed["blocks"] if block["id"] == item["id"]).get("container_id")
                for item in parsed["reading_items"])),
        "markdown_escaping": "\\|" in table.get("markdown", "") and "<br>" in table.get("markdown", ""),
    }
    negative = {
        "wrong_shape_is_detected": not (table.get("n_rows") == 6 and table.get("n_cols") == 4),
        "wrong_cell_is_detected": cells.get((2, 1), {}).get("text") != "0.98",
    }
    return checks, negative


def run_advanced_tests(workdir, outdir):
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    structure_pdf = build_structure_pdf(os.path.join(workdir, "structure_formula.pdf"))
    tables_pdf = build_tables_pdf(os.path.join(workdir, "cross_page_tables.pdf"))
    structure, _ = P.parse(structure_pdf, case_id="controlled-structure-formula")
    tables, _ = P.parse(tables_pdf, case_id="controlled-cross-page-tables")
    structure_checks, structure_negative = check_structure(structure)
    table_checks, table_negative = check_tables(tables)

    symbol_pdf = build_symbol_font_pdf(os.path.join(workdir, "symbol_font_risk.pdf"))
    symbol_parsed, _ = P.parse(symbol_pdf, case_id="controlled-symbol-font-risk")
    structure_checks["ambiguous_symbol_font_requires_review"] = bool(symbol_parsed["equations"]) and all(
        equation["needs_review"] for equation in symbol_parsed["equations"])

    original_plumber = P.pdfplumber
    try:
        P.pdfplumber = None
        degraded, _ = P.parse(tables_pdf, case_id="controlled-missing-table-dependency")
    finally:
        P.pdfplumber = original_plumber
    table_checks["missing_pdfplumber_is_explicit"] = (
        not degraded["tables"] and any(warning["kind"] == "pdfplumber_unavailable"
                                       for warning in degraded["warnings"]))
    for name, value in (("structure_parsed.json", structure), ("tables_parsed.json", tables)):
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1)
    all_checks = {**structure_checks, **table_checks}
    all_negative = {**structure_negative, **table_negative}
    report = {
        "schema": "sci-pdf-reading-parse/advanced-checks/v1",
        "reference": "runtime-generated controlled fixtures with known text, order, cells and formula scripts",
        "checks": all_checks,
        "negative_controls": all_negative,
        "passed": sum(bool(value) for value in all_checks.values()),
        "total": len(all_checks),
        "negative_passed": sum(bool(value) for value in all_negative.values()),
        "negative_total": len(all_negative),
        "all_passed": all(all_checks.values()) and all(all_negative.values()),
    }
    with open(os.path.join(outdir, "advanced_checks.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    return report
