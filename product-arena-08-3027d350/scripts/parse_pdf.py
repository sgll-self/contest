#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence-anchored scientific PDF parser, schema v3.

The parser keeps raw and normalized text, reading order, section hierarchy,
cell-level table evidence, display-equation scripts, raster-figure locations,
footnotes and references. It is deterministic and never invents OCR text or
scientific semantics. Runtime artifacts belong to the caller's work directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict, dataclass, field

try:
    import pymupdf
except ImportError:  # pragma: no cover
    import fitz as pymupdf

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None


def _clean(value: str) -> str:
    """Normalize layout whitespace while retaining the unmodified raw_text field."""
    if value is None:
        return ""
    value = value.replace("\u00ad", "")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _norm_for_match(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", "", value).lower()


def _nw(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _round_bbox(bbox) -> list:
    return [round(float(v), 2) for v in bbox]


def _overlap_ratio(a, b) -> float:
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    return intersection / max(1.0, min(a[2] - a[0], b[2] - b[0]))


def _inside_ratio(inner, outer) -> float:
    area = max(1.0, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    intersection = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0])) * max(
        0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    return intersection / area


@dataclass
class Block:
    id: str
    page: int
    bbox: list
    text: str
    raw_text: str = ""
    role: str = "body"
    column: int = -1
    reading_order: int = -1
    font_size: float = 0.0
    n_chars: int = 0
    flags: list = field(default_factory=list)
    source_ids: list = field(default_factory=list)
    source_line_ids: list = field(default_factory=list)
    line_count: int = 0
    bold_ratio: float = 0.0
    level: int | None = None
    number: str | None = None
    parent_id: str | None = None
    section_path: list = field(default_factory=list)
    container_id: str | None = None
    continuation_of: str | None = None
    spans: list = field(default_factory=list)


def _span_record(span) -> dict:
    return {
        "text": span.get("text", ""),
        "bbox": _round_bbox(span.get("bbox", [0, 0, 0, 0])),
        "font": span.get("font", ""),
        "size": round(float(span.get("size", 0.0)), 3),
        "flags": int(span.get("flags", 0)),
        "origin": [round(float(v), 2) for v in span.get("origin", [0, 0])],
    }


def extract_blocks(page, page_no: int):
    """Extract stable raw lineage, splitting mixed-margin/font physical blocks."""
    data = page.get_text("dict")
    blocks, figures = [], []
    for block_index, raw in enumerate(data.get("blocks", [])):
        if raw.get("type") == 1:
            figures.append({
                "id": f"p{page_no}_f{block_index}", "page": page_no,
                "bbox": _round_bbox(raw.get("bbox", [0, 0, 0, 0])), "kind": "raster_image",
                "pixel_width": raw.get("width"), "pixel_height": raw.get("height"),
                "caption_id": None, "source_block_id": f"p{page_no}_b{block_index}",
            })
            continue
        if raw.get("type") != 0:
            continue
        lines = []
        for line_index, line in enumerate(raw.get("lines", [])):
            raw_spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in raw_spans)
            spans = [_span_record(span) for span in raw_spans]
            sizes = [span["size"] for span in spans if span["size"]]
            font_size = sum(sizes) / len(sizes) if sizes else 0.0
            bbox = _round_bbox(line.get("bbox", [0, 0, 0, 0]))
            band = "top" if bbox[3] < page.rect.height * 0.08 else (
                "bottom" if bbox[1] > page.rect.height * 0.92 else "content")
            lines.append({"text": text, "spans": spans, "bbox": bbox,
                          "font_size": font_size, "band": band,
                          "source_line_id": f"p{page_no}_b{block_index}_l{line_index}"})
        groups = []
        for line in lines:
            split = False
            if groups:
                previous = groups[-1][-1]
                ratio = max(previous["font_size"], line["font_size"]) / max(
                    0.1, min(previous["font_size"], line["font_size"]))
                split = previous["band"] != line["band"] or ratio > 1.25
            if split or not groups:
                groups.append([line])
            else:
                groups[-1].append(line)
        base_id = f"p{page_no}_b{block_index}"
        for group_index, group in enumerate(groups):
            raw_text = "\n".join(line["text"] for line in group)
            text = _clean(raw_text)
            if not text:
                continue
            spans = [span for line in group for span in line["spans"]]
            sizes = [span["size"] for span in spans if span["size"]]
            bold_chars = sum(len(_nw(span["text"])) for span in spans
                             if span["flags"] & 16 or "bold" in span["font"].lower())
            block_id = base_id if len(groups) == 1 else f"{base_id}_s{group_index}"
            blocks.append(Block(
                id=block_id, page=page_no,
                bbox=[round(min(line["bbox"][0] for line in group), 2),
                      round(min(line["bbox"][1] for line in group), 2),
                      round(max(line["bbox"][2] for line in group), 2),
                      round(max(line["bbox"][3] for line in group), 2)],
                text=text, raw_text=raw_text,
                font_size=round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
                n_chars=len(text), source_ids=[base_id],
                source_line_ids=[line["source_line_id"] for line in group],
                line_count=len(group), bold_ratio=round(bold_chars / max(1, len(_nw(text))), 4),
                spans=spans,
            ))
    return blocks, figures, page.rect.width, page.rect.height


def _poppler_words(pdf_path, page_no):
    executable = shutil.which("pdftotext")
    if not executable:
        return None
    result = subprocess.run(
        [executable, "-f", str(page_no), "-l", str(page_no), "-bbox", pdf_path, "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode != 0:
        return None
    root = ET.fromstring(result.stdout.decode("utf-8", errors="strict"))
    words = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "word":
            continue
        words.append({
            "text": element.text or "",
            "bbox": [float(element.attrib["xMin"]), float(element.attrib["yMin"]),
                     float(element.attrib["xMax"]), float(element.attrib["yMax"])],
        })
    return words


def _words_in_bbox(words, bbox):
    selected = []
    for word in words:
        center_x = (word["bbox"][0] + word["bbox"][2]) / 2
        center_y = (word["bbox"][1] + word["bbox"][3]) / 2
        if bbox[0] - 2 <= center_x <= bbox[2] + 2 and bbox[1] - 2 <= center_y <= bbox[3] + 2:
            selected.append(word)
    return selected


def _words_to_text(words):
    lines = []
    for word in sorted(words, key=lambda item: ((item["bbox"][1] + item["bbox"][3]) / 2, item["bbox"][0])):
        center_y = (word["bbox"][1] + word["bbox"][3]) / 2
        if not lines or abs(center_y - lines[-1][0]) > 2.5:
            lines.append([center_y, [word]])
        else:
            lines[-1][1].append(word)
    return "\n".join(" ".join(word["text"] for word in sorted(line[1], key=lambda item: item["bbox"][0]))
                     for line in lines)


def _ascii_skeleton(text):
    return "".join(char for char in text if ord(char) < 128 and not char.isspace() and char != "\ufffd")


def recover_unmapped_glyphs(blocks, pdf_path, page_no, warnings):
    """Recover only replacement-character blocks with bbox-aligned Poppler words.

    ASCII skeleton equality guards against substituting unrelated text. The raw
    PyMuPDF text remains available in raw_text and every recovery is flagged.
    """
    affected = [block for block in blocks if "\ufffd" in block.text]
    if not affected:
        return
    try:
        words = _poppler_words(pdf_path, page_no)
    except Exception as exc:
        warnings.append({"page": page_no, "kind": "glyph_recovery_failed", "detail": str(exc)[:300]})
        return
    if words is None:
        warnings.append({"page": page_no, "kind": "glyph_recovery_unavailable",
                         "detail": "pdftotext unavailable; replacement glyphs retained for review"})
        return
    for block in affected:
        selected = _words_in_bbox(words, block.bbox)
        recovered = _words_to_text(selected)
        if (not recovered or "\ufffd" in recovered or
                _ascii_skeleton(recovered) != _ascii_skeleton(block.text)):
            block.flags.append("glyph_recovery_rejected")
            continue
        block.text = _clean(recovered)
        block.n_chars = len(block.text)
        block.flags.append("glyph_recovered:pdftotext-bbox")
        for span in block.spans:
            if "\ufffd" not in span["text"]:
                continue
            span_words = _words_in_bbox(words, span["bbox"])
            if span_words:
                span["text"] = " ".join(word["text"] for word in sorted(
                    span_words, key=lambda item: item["bbox"][0]))
                span["glyph_recovered"] = True


def detect_repeating_marginalia(pages_blocks, page_shapes):
    top_texts, bottom_texts = defaultdict(int), defaultdict(int)
    for blocks, (_, height) in zip(pages_blocks, page_shapes):
        for block in blocks:
            key = _norm_for_match(block.text)
            if not key:
                continue
            if block.bbox[3] < height * 0.08:
                top_texts[key] += 1
            elif block.bbox[1] > height * 0.92:
                bottom_texts[key] += 1
    threshold = max(2, int(len(pages_blocks) * 0.5))
    return ({key for key, count in top_texts.items() if count >= threshold},
            {key for key, count in bottom_texts.items() if count >= threshold})


_CAPTION_RE = re.compile(
    r"^(?:fig(?:ure)?\.?|table|tab\.|scheme|chart|图|表)\s*[sS]?\d+", re.I)
_HEADING_NUMBER_RE = re.compile(r"^\s*((?:\d+\.)*\d+\.?)\s+\S")
_REFERENCES_RE = re.compile(r"^(?:references|bibliography|参考文献)\b", re.I)
_ABSTRACT_RE = re.compile(r"^(?:abstract|摘要)\b\s*[:.—-]?", re.I)
_AFFILIATION_RE = re.compile(
    r"university|institute|college|department|laboratory|academy|research|hospital|"
    r"大学|研究院|研究所|学院|实验室|医院|@", re.I)


def _math_density(text: str) -> float:
    if not text:
        return 0.0
    count = sum(1 for char in text if unicodedata.category(char).startswith("S")
                or char in "=+−×÷∑∏∫√∂∇∈∉≤≥≠≈∞αβγδεζηθικλμνξοπρστυφχψωΓΔΘΛΞΠΣΦΨΩ")
    return count / max(1, len(text))


def _looks_display_equation(block) -> bool:
    has_number = re.search(r"\((?:\d+|[sS]\d+)(?:[.-]\d+)?\)\s*$", block.text)
    if has_number and _math_density(block.text) > 0.005 and block.line_count <= 6:
        return True
    if block.n_chars <= 8 and any(span["flags"] & 2 for span in block.spans):
        return True
    return _math_density(block.text) > 0.18 and block.n_chars < 300 and block.line_count <= 5


def classify_roles(blocks, width, height, headers, footers, body_font):
    for block in blocks:
        if block.role == "table_text":
            continue
        key = _norm_for_match(block.text)
        y0, y1 = block.bbox[1], block.bbox[3]
        small = block.font_size > 0 and block.font_size < body_font * 0.9
        page_number = re.fullmatch(r"[\divxlc]+", key)
        if y1 < height * 0.08 and (key in headers or page_number or (small and block.n_chars < 50)):
            block.role = "header"
            continue
        if re.match(r"^arxiv:", block.text, re.I) and y1 < height * 0.16:
            block.role = "header"
            continue
        if y0 > height * 0.92 and (key in footers or page_number or (small and block.n_chars < 50)):
            block.role = "footer"
            continue
        lower = block.text.lower()
        numbered_heading = _HEADING_NUMBER_RE.match(block.text)
        if y0 > height * 0.78 and small and block.n_chars >= 12:
            block.role = "footnote"
        elif _CAPTION_RE.match(lower):
            block.role = "caption"
        elif _ABSTRACT_RE.match(block.text):
            block.role = "abstract"
        elif _REFERENCES_RE.match(block.text) and block.n_chars < 80:
            block.role = "heading"
            block.flags.append("references_heading")
        elif (numbered_heading and block.n_chars < 160 and
              (block.bold_ratio >= 0.35 or block.font_size >= body_font * 0.95)):
            block.role = "heading"
        elif _looks_display_equation(block):
            block.role = "equation"
            block.flags.append("math")
        elif (block.font_size >= body_font * 1.12 and 6 <= block.n_chars < 120) or (
                block.bold_ratio >= 0.65 and block.font_size >= body_font * 0.9
                and 4 <= block.n_chars < 90 and block.line_count <= 2
                and not re.search(r"[.!?:]\s+\S", block.text)):
            block.role = "heading"
        else:
            block.role = "body"
    return blocks


def classify_front_matter(blocks, body_font):
    """Conservative first-page title/authors/affiliation detection."""
    if not blocks:
        return
    page_one = [b for b in blocks if b.page == 1 and b.role in ("body", "heading")]
    top = [b for b in page_one if b.bbox[1] < 0.38 * max(
        [b.bbox[3] for b in blocks if b.page == 1] + [792])]
    if not top:
        return
    title_candidates = [b for b in top if b.font_size >= body_font * 1.15 and 12 <= b.n_chars < 300
                        and not re.match(r"^(?:arxiv:|doi:|https?://)", b.text, re.I)]
    if not title_candidates:
        return
    bold_candidates = [b for b in title_candidates if b.bold_ratio >= 0.45]
    if bold_candidates:
        title_candidates = bold_candidates
    title = max(title_candidates, key=lambda b: (b.font_size, b.n_chars, -b.bbox[1]))
    title.role = "title"
    title.flags.append("front_matter")
    title_bottom = title.bbox[3]
    for block in sorted(page_one, key=lambda b: (b.bbox[1], b.bbox[0])):
        if block.id == title.id or block.bbox[1] < title_bottom - 2 or block.bbox[1] > title_bottom + 150:
            continue
        if block.role not in ("body", "heading") or block.n_chars > 400:
            continue
        first_line = block.text.split("\n", 1)[0]
        mixed_front_matter = "\n" in block.text and _AFFILIATION_RE.search(block.text) and not _AFFILIATION_RE.search(first_line)
        if mixed_front_matter:
            block.role = "authors"
            block.flags.extend(["front_matter", "mixed_authors_affiliation"])
        elif _AFFILIATION_RE.search(block.text):
            block.role = "affiliation"
            block.flags.append("front_matter")
        elif (block.n_chars < 180 and len(block.text.split()) <= 20
              and not re.match(r"^(?:we|this|here)\b", block.text, re.I)
              and not block.text.endswith((".", "。", "!", "?"))
              and ("," in block.text or " and " in block.text.lower() or "，" in block.text
                   or ("\n" in block.text and block.line_count <= 6))):
            block.role = "authors"
            block.flags.append("front_matter")


def _column_groups(blocks, width, height):
    """Infer columns without allowing small centered bridges to join two columns."""
    candidates = [b for b in blocks if b.role not in (
        "header", "footer", "table_text", "title", "authors", "affiliation")
        and (b.bbox[2] - b.bbox[0]) < 0.62 * width]
    if len(candidates) < 2:
        return []
    # Large blocks establish the layout first. A later small block overlapping two
    # established groups is a centered/full-width fragment, not a column connector.
    groups = []
    for block in sorted(candidates, key=lambda b: (-b.n_chars, b.bbox[1], b.bbox[0])):
        overlapping = []
        for index, members in enumerate(groups):
            if any(_overlap_ratio(block.bbox, member.bbox) >= 0.20 for member in members):
                overlapping.append(index)
        if len(overlapping) == 1:
            groups[overlapping[0]].append(block)
        elif not overlapping:
            groups.append([block])
    groups = [members for members in groups
              if sum(b.n_chars for b in members) >= 50 and
              (len(members) >= 2 or max(b.bbox[3] for b in members) - min(b.bbox[1] for b in members) >= 0.12 * height)]
    groups.sort(key=lambda members: min(b.bbox[0] for b in members))
    changed = True
    while changed and len(groups) > 1:
        changed = False
        for index in range(len(groups) - 1):
            left, right = groups[index], groups[index + 1]
            if min(b.bbox[0] for b in right) < max(b.bbox[2] for b in left) - 0.03 * width:
                if sum(b.n_chars for b in left) < sum(b.n_chars for b in right):
                    groups.pop(index)
                else:
                    groups.pop(index + 1)
                changed = True
                break
    if len(groups) > 3:
        groups = sorted(sorted(groups, key=lambda members: sum(b.n_chars for b in members), reverse=True)[:3],
                        key=lambda members: min(b.bbox[0] for b in members))
    return groups if 2 <= len(groups) <= 3 else []


def detect_columns(blocks, width, height):
    groups = _column_groups(blocks, width, height)
    bounds = []
    for left, right in zip(groups, groups[1:]):
        bounds.append((max(b.bbox[2] for b in left) + min(b.bbox[0] for b in right)) / 2)
    assignment = {}
    for block in blocks:
        x0, _, x1, _ = block.bbox
        center = (x0 + x1) / 2
        crosses = any(x0 < boundary - 2 and x1 > boundary + 2 for boundary in bounds)
        if (x1 - x0) >= 0.62 * width or crosses or block.role in (
                "header", "footer", "title", "authors", "affiliation"):
            assignment[block.id] = -1
        elif bounds:
            assignment[block.id] = sum(center > boundary for boundary in bounds)
        else:
            assignment[block.id] = 0
    return bounds, assignment


def order_blocks(blocks, assignment):
    content = [b for b in blocks if b.role not in ("header", "footer")]
    ordered = sorted(content, key=lambda b: (b.page, b.bbox[1], b.bbox[0]))
    result, band = [], []

    def flush():
        columns = defaultdict(list)
        for block in band:
            columns[assignment.get(block.id, 0)].append(block)
        for column in sorted(columns):
            result.extend(sorted(columns[column], key=lambda b: (b.bbox[1], b.bbox[0])))
        band.clear()

    for block in ordered:
        if assignment.get(block.id, 0) == -1:
            flush()
            result.append(block)
        else:
            band.append(block)
    flush()
    for index, block in enumerate(result):
        block.reading_order = index
        block.column = assignment.get(block.id, 0)
    return result


def _heading_level(block):
    match = _HEADING_NUMBER_RE.match(block.text)
    if match:
        normalized = match.group(1).rstrip(".")
        return len(normalized.split(".")), normalized
    if _REFERENCES_RE.match(block.text) or block.text.lower().startswith(("acknowledg", "appendix")):
        return 1, None
    return 1, None


def propagate_abstract(blocks):
    active = False
    for block in blocks:
        if block.role == "abstract":
            active = True
            continue
        if active and block.role == "heading":
            active = False
        elif active and block.role == "body":
            block.role = "abstract"
        elif active and block.role in ("caption", "equation", "table_text"):
            active = False


def build_section_hierarchy(blocks):
    stack, sections = [], []
    in_references = False
    reference_level = None
    for block in blocks:
        if block.role in ("header", "footer", "table_text"):
            continue
        if block.role == "heading":
            level, number = _heading_level(block)
            block.level, block.number = level, number
            while stack and stack[-1][0] >= level:
                stack.pop()
            block.parent_id = stack[-1][1].id if stack else None
            block.section_path = [item[1].text for item in stack] + [block.text]
            sections.append(block)
            stack.append((level, block))
            if "references_heading" in block.flags:
                in_references, reference_level = True, level
            elif in_references and level <= reference_level:
                in_references, reference_level = False, None
        else:
            block.section_path = [item[1].text for item in stack]
            if in_references and block.role == "body":
                block.role = "reference"
    for index, section in enumerate(sections):
        section.flags.append(f"section_index:{index}")
    return [{
        "id": block.id, "number": block.number, "title": block.text,
        "level": block.level, "parent_id": block.parent_id,
        "section_path": block.section_path, "page": block.page, "bbox": block.bbox,
        "reading_order": block.reading_order,
    } for block in sections]


def link_continuations(blocks):
    content = [b for b in blocks if b.role == "body"]
    for previous, current in zip(content, content[1:]):
        previous_text = previous.text.rstrip()
        current_text = current.text.lstrip()
        if not previous_text or not current_text:
            continue
        open_sentence = not re.search(r"[.!?。！？:：;；]$", previous_text)
        starts_continuation = bool(re.match(r"^[a-zà-ÿ),;:\]]", current_text))
        if (open_sentence and starts_continuation and
                abs(previous.font_size - current.font_size) <= 0.3 and
                (previous.page != current.page or previous.column != current.column or
                 current.bbox[1] - previous.bbox[3] < 2.5 * max(previous.font_size, 1))):
            current.continuation_of = previous.id
            previous.flags.append(f"continues_to:{current.id}")


def _cell_spans(table):
    positions = defaultdict(list)
    for row_index, row in enumerate(table.rows):
        for col_index, bbox in enumerate(row.cells):
            if bbox is not None:
                positions[tuple(round(float(v), 3) for v in bbox)].append((row_index, col_index))
    return positions


def _table_md(rows):
    if not rows:
        return ""
    normalized = [[_clean(cell or "") for cell in row] for row in rows]
    column_count = max(len(row) for row in rows)
    normalized = [row + [""] * (column_count - len(row)) for row in normalized]

    def escape(cell):
        return cell.replace("\\", "\\\\").replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")

    output = ["| " + " | ".join(escape(cell) for cell in normalized[0]) + " |",
              "| " + " | ".join(["---"] * column_count) + " |"]
    output.extend("| " + " | ".join(escape(cell) for cell in row) + " |" for row in normalized[1:])
    return "\n".join(output)


def extract_tables(plumber_page, page_no: int, warnings: list):
    tables = []
    if pdfplumber is None or plumber_page is None:
        return tables
    try:
        found = list(plumber_page.find_tables())
    except Exception as exc:
        warnings.append({"page": page_no, "kind": "table_detection_failed", "detail": str(exc)[:300]})
        return tables
    for table_index, table in enumerate(found):
        try:
            rows = table.extract()
            span_positions = _cell_spans(table)
            all_bboxes = [cell for row in table.rows for cell in row.cells if cell is not None]
            x_grid = sorted({round(float(value), 3) for bbox in all_bboxes for value in (bbox[0], bbox[2])})
            y_grid = sorted({round(float(value), 3) for bbox in all_bboxes for value in (bbox[1], bbox[3])})

            def geometric_span(bbox, grid, start, end):
                if not bbox:
                    return 0
                return sum(1 for left, right in zip(grid, grid[1:])
                           if bbox[start] - 0.2 <= (left + right) / 2 <= bbox[end] + 0.2)

            cells = []
            for row_index, row in enumerate(rows):
                for col_index, value in enumerate(row):
                    bbox = None
                    if row_index < len(table.rows) and col_index < len(table.rows[row_index].cells):
                        raw_bbox = table.rows[row_index].cells[col_index]
                        bbox = _round_bbox(raw_bbox) if raw_bbox is not None else None
                    key = tuple(round(float(v), 3) for v in bbox) if bbox else None
                    positions = span_positions.get(key, [])
                    anchor = min(positions) if positions else (row_index, col_index)
                    if bbox is None and col_index < len(x_grid) - 1 and row_index < len(y_grid) - 1:
                        center_x = (x_grid[col_index] + x_grid[col_index + 1]) / 2
                        center_y = (y_grid[row_index] + y_grid[row_index + 1]) / 2
                        for owner_key, owner_positions in span_positions.items():
                            if (owner_key[0] - 0.2 <= center_x <= owner_key[2] + 0.2 and
                                    owner_key[1] - 0.2 <= center_y <= owner_key[3] + 0.2):
                                anchor = min(owner_positions)
                                positions = owner_positions
                                break
                    covered = (row_index, col_index) != anchor and (
                        bbox is None or len(positions) > 1)
                    cells.append({
                        "row": row_index, "col": col_index, "text": _clean(value or ""),
                        "bbox": bbox,
                        "row_span": 0 if covered else geometric_span(bbox, y_grid, 1, 3),
                        "col_span": 0 if covered else geometric_span(bbox, x_grid, 0, 2),
                        "covered_by": {"row": anchor[0], "col": anchor[1]} if covered else None,
                    })
            tables.append({
                "id": f"p{page_no}_t{table_index}", "page": page_no, "pages": [page_no],
                "bbox": _round_bbox(table.bbox), "n_rows": len(rows),
                "n_cols": max((len(row) for row in rows), default=0),
                "cells": cells, "markdown": _table_md(rows), "extractor": "pdfplumber",
                "needs_review": False, "segments": [], "merged_into": None,
            })
        except Exception as exc:
            warnings.append({"page": page_no, "kind": "table_extraction_failed", "detail": str(exc)[:300]})
    return tables


def filter_figure_table_candidates(tables, blocks, figures, page_no, warnings):
    """Reject ruled chart regions misdetected as tables; retain vector-figure anchors."""
    captions = [block for block in blocks if block.page == page_no and _CAPTION_RE.match(block.text)]
    accepted = []
    for table in tables:
        nearby = []
        for caption in captions:
            distance = min(abs(caption.bbox[1] - table["bbox"][3]),
                           abs(table["bbox"][1] - caption.bbox[3]))
            if distance <= 220 and _overlap_ratio(caption.bbox, table["bbox"]) >= 0.03:
                nearby.append((distance, caption))
        caption = min(nearby, key=lambda item: item[0])[1] if nearby else None
        if caption is not None and re.match(r"^(?:fig|图)", caption.text, re.I):
            duplicate = any(figure["page"] == page_no and _inside_ratio(figure["bbox"], table["bbox"]) >= 0.20
                            for figure in figures)
            if not duplicate:
                figures.append({
                    "id": f"p{page_no}_vf{table['id'].rsplit('_t', 1)[-1]}",
                    "page": page_no, "bbox": table["bbox"], "kind": "vector_figure",
                    "pixel_width": None, "pixel_height": None, "caption_id": None,
                    "source_block_id": None, "source_table_candidate_id": table["id"],
                })
            warnings.append({"page": page_no, "kind": "table_candidate_reclassified_figure",
                             "candidate_id": table["id"], "caption_id": caption.id})
        else:
            accepted.append(table)
    return accepted


def attach_tables(blocks, tables):
    for table in tables:
        for block in blocks:
            if block.page == table["page"] and block.role not in ("header", "footer") and _inside_ratio(block.bbox, table["bbox"]) >= 0.45:
                block.role = "table_text"
                block.container_id = table["id"]


def _row_text(table, row_index):
    return [_nw(cell["text"]).lower() for cell in table["cells"] if cell["row"] == row_index]


def merge_cross_page_tables(tables, page_meta, blocks):
    """Conservatively merge adjacent-page segments with repeated headers or a continued caption."""
    by_page = defaultdict(list)
    for table in tables:
        by_page[table["page"]].append(table)
    merged = []
    for table in sorted(tables, key=lambda item: (item["page"], item["bbox"][1])):
        if table["merged_into"]:
            continue
        current = table
        while True:
            next_page = current["page"] + 1
            candidates = [item for item in by_page.get(next_page, []) if not item["merged_into"]]
            if not candidates or current["n_cols"] < 1:
                break
            candidate = min(candidates, key=lambda item: item["bbox"][1])
            previous_meta = page_meta[current["page"] - 1]
            next_meta = page_meta[next_page - 1]
            near_break = (current["bbox"][3] > previous_meta["height"] * 0.60 and
                          candidate["bbox"][1] < next_meta["height"] * 0.38)
            same_shape = candidate["n_cols"] == current["n_cols"]
            repeated_header_rows = 0
            for row_index in range(min(3, current["n_rows"], candidate["n_rows"])):
                if _row_text(current, row_index) == _row_text(candidate, row_index):
                    repeated_header_rows += 1
                else:
                    break
            repeated_header = repeated_header_rows > 0
            continued_caption = any(
                block.page == next_page and block.role == "caption" and "continued" in block.text.lower()
                and abs(block.bbox[1] - candidate["bbox"][1]) < 100 for block in blocks)
            if not (near_break and same_shape and (repeated_header or continued_caption)):
                break
            segment = {
                "id": candidate["id"], "page": candidate["page"], "bbox": candidate["bbox"],
                "n_rows": candidate["n_rows"], "n_cols": candidate["n_cols"],
                "repeated_header_removed": repeated_header,
                "repeated_header_rows": repeated_header_rows,
            }
            offset = current["n_rows"]
            for cell in candidate["cells"]:
                if repeated_header and cell["row"] < repeated_header_rows:
                    continue
                copied = dict(cell)
                copied["row"] = cell["row"] - repeated_header_rows + offset
                if copied.get("covered_by"):
                    copied["covered_by"] = dict(copied["covered_by"])
                    copied["covered_by"]["row"] += offset - repeated_header_rows
                copied["segment_id"] = candidate["id"]
                current["cells"].append(copied)
            current["segments"].append(segment)
            current["pages"].append(next_page)
            current["n_rows"] += candidate["n_rows"] - repeated_header_rows
            candidate["merged_into"] = current["id"]
            rows = [[cell["text"] for cell in sorted(
                [c for c in current["cells"] if c["row"] == row], key=lambda c: c["col"])]
                    for row in range(current["n_rows"])]
            current["markdown"] = _table_md(rows)
            current["flags"] = ["cross_page_merged"]
            # The measured envelope is a two-page continuation; further segments
            # require another independently validated continuation rule.
            break
        merged.append(current)
    # Keep unmerged segments out of the logical table list, but retain their evidence in root segments.
    return [table for table in merged if not table.get("merged_into")]


def _linear_math(spans):
    if not spans:
        return "", [], False
    char_sizes = defaultdict(int)
    for span in spans:
        char_sizes[span["size"]] += len(_nw(span["text"]))
    main_size = max(char_sizes, key=char_sizes.get) if char_sizes else 10.0
    main_origins = [span["origin"][1] for span in spans
                    if span["size"] >= main_size * 0.9 and _nw(span["text"])]
    main_origin = sorted(main_origins)[len(main_origins) // 2] if main_origins else 0.0
    pieces, scripts, review = [], [], False
    for span in spans:
        text = span["text"]
        if not text:
            continue
        role = "base"
        if span["size"] < main_size * 0.88 or span["flags"] & 1:
            if span["flags"] & 1 or span["origin"][1] < main_origin - main_size * 0.12:
                role = "superscript"
                pieces.append("^{" + text + "}")
            elif span["origin"][1] > main_origin + main_size * 0.12:
                role = "subscript"
                pieces.append("_{" + text + "}")
            else:
                pieces.append(text)
            if role != "base":
                scripts.append({"text": text, "role": role, "bbox": span["bbox"], "font": span["font"]})
        else:
            pieces.append(text)
        font_name = span["font"].lower()
        if ("symbol" in font_name or "dingbat" in font_name) and text and all(
                ord(char) < 128 for char in text if char.strip()):
            review = True
        if "\ufffd" in text or any(unicodedata.category(char) == "Co" for char in text):
            review = True
    return "".join(pieces), scripts, review


def build_equations(blocks):
    equations = []
    for block in blocks:
        if block.role != "equation":
            continue
        match = re.search(r"\(((?:\d+|[sS]\d+)(?:[.-]\d+)?)\)\s*$", block.text)
        linear, scripts, needs_review = _linear_math(block.spans)
        equations.append({
            "id": block.id.replace("_b", "_e"), "source_block_id": block.id,
            "page": block.page, "bbox": block.bbox, "number": match.group(1) if match else None,
            "unicode_text": block.text, "raw_text": block.raw_text,
            "linear_text": linear, "scripts": scripts, "spans": block.spans,
            "needs_review": needs_review,
            "review_reason": "suspect Symbol/private-use/replacement glyph; verify against source" if needs_review else None,
        })
    return equations


def link_figure_captions(figures, blocks):
    captions = [b for b in blocks if b.role == "caption" and re.match(r"^(?:fig|图)", b.text, re.I)]
    for figure in figures:
        candidates = []
        for caption in captions:
            if caption.page != figure["page"]:
                continue
            vertical = caption.bbox[1] - figure["bbox"][3]
            if -30 <= vertical <= 180 and _overlap_ratio(figure["bbox"], caption.bbox) > 0.05:
                candidates.append((abs(vertical), caption))
        if candidates:
            caption = min(candidates, key=lambda item: item[0])[1]
            figure["caption_id"] = caption.id
            caption.flags.append(f"figure_id:{figure['id']}")


def _geometric_order(item, blocks):
    if item.get("reading_order") is not None and item["reading_order"] >= 0:
        return item["reading_order"]
    following = [b.reading_order for b in blocks if b.page == item["page"] and
                 b.reading_order >= 0 and b.bbox[1] >= item["bbox"][1]]
    return min(following) - 0.4 if following else 10**8 + item["bbox"][1]


def build_reading_items(blocks, tables, figures):
    table_order = defaultdict(list)
    for block in blocks:
        if block.container_id and block.reading_order >= 0:
            table_order[block.container_id].append(block.reading_order)
    for table in tables:
        table["reading_order"] = min(table_order.get(table["id"], [-1]))
    items = []
    for block in blocks:
        if block.role not in ("header", "footer", "table_text"):
            items.append({"kind": "block", "id": block.id, "page": block.page,
                          "bbox": block.bbox, "_order": float(block.reading_order)})
    for table in tables:
        if not table.get("merged_into"):
            items.append({"kind": "table", "id": table["id"], "page": table["page"],
                          "bbox": table["bbox"], "_order": _geometric_order(table, blocks) + 0.1})
    for figure in figures:
        items.append({"kind": "figure", "id": figure["id"], "page": figure["page"],
                      "bbox": figure["bbox"], "_order": _geometric_order(figure, blocks) - 0.1})
    items.sort(key=lambda item: (item["page"], item["_order"], item["bbox"][1], item["bbox"][0]))
    return [{key: value for key, value in item.items() if key != "_order"} for item in items]


def _document_summary(blocks, sections, tables, figures, equations):
    def texts(role):
        return [b.text for b in blocks if b.role == role]
    authors, affiliations, affiliation_ids = [], [], []
    for block in blocks:
        if block.role == "authors" and "mixed_authors_affiliation" in block.flags:
            lines = block.text.split("\n")
            split_at = next((index for index, line in enumerate(lines) if _AFFILIATION_RE.search(line)), len(lines))
            if lines[:split_at]:
                authors.append("\n".join(lines[:split_at]))
            if lines[split_at:]:
                affiliations.append("\n".join(lines[split_at:]))
                affiliation_ids.append(block.id)
        elif block.role == "authors":
            authors.append(block.text)
    affiliations.extend(texts("affiliation"))
    affiliation_ids.extend(b.id for b in blocks if b.role == "affiliation")
    return {
        "title_block_id": next((b.id for b in blocks if b.role == "title"), None),
        "title": "\n".join(texts("title")),
        "author_block_ids": [b.id for b in blocks if b.role == "authors"],
        "authors": authors,
        "affiliation_block_ids": affiliation_ids,
        "affiliations": affiliations,
        "abstract_block_ids": [b.id for b in blocks if b.role == "abstract"],
        "abstract": "\n".join(texts("abstract")),
        "sections": sections,
        "counts": {
            "references": len(texts("reference")), "footnotes": len(texts("footnote")),
            "captions": len(texts("caption")), "figures": len(figures),
            "tables": len(tables), "equations": len(equations),
        },
    }


def parse(pdf_path: str, case_id: str = "", max_pages: int | None = None):
    if not os.path.isfile(pdf_path):
        raise ValueError(f"input PDF does not exist: {pdf_path}")
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise ValueError(f"cannot open PDF: {exc}") from exc
    warnings = []
    try:
        if len(doc) == 0:
            raise ValueError("PDF has zero pages")
        if doc.is_encrypted:
            try:
                authenticated = doc.authenticate("")
            except Exception:
                authenticated = 0
            if not authenticated:
                raise ValueError("encrypted PDF: empty-password authentication failed; a password is required")
        page_count = min(len(doc), max_pages) if max_pages else len(doc)
        plumber = None
        if pdfplumber is not None:
            try:
                plumber = pdfplumber.open(pdf_path)
            except Exception as exc:
                warnings.append({"kind": "pdfplumber_open_failed", "detail": str(exc)[:300]})
        else:
            warnings.append({"kind": "pdfplumber_unavailable", "detail": "structured table extraction disabled"})
        pages_blocks, pages_figures, shapes = [], [], []
        for index in range(page_count):
            blocks, figures, width, height = extract_blocks(doc[index], index + 1)
            recover_unmapped_glyphs(blocks, pdf_path, index + 1, warnings)
            pages_blocks.append(blocks)
            pages_figures.append(figures)
            shapes.append((width, height))
        headers, footers = detect_repeating_marginalia(pages_blocks, shapes)
        all_blocks, all_tables, all_figures, page_meta = [], [], [], []
        for index in range(page_count):
            blocks, figures = pages_blocks[index], pages_figures[index]
            width, height = shapes[index]
            plumber_page = plumber.pages[index] if plumber is not None and index < len(plumber.pages) else None
            tables = extract_tables(plumber_page, index + 1, warnings)
            tables = filter_figure_table_candidates(tables, blocks, figures, index + 1, warnings)
            attach_tables(blocks, tables)
            sizes = sorted(b.font_size for b in blocks if b.font_size > 0 and b.role != "table_text"
                           and b.n_chars >= 20 and b.bbox[1] > height * 0.05 and b.bbox[3] < height * 0.92)
            body_font = sizes[len(sizes) // 2] if sizes else 10.0
            classify_roles(blocks, width, height, headers, footers, body_font)
            classify_front_matter(blocks, body_font) if index == 0 else None
            bounds, assignment = detect_columns(blocks, width, height)
            ordered = order_blocks(blocks, assignment)
            marginalia = [block for block in blocks if block.role in ("header", "footer")]
            all_blocks.extend(ordered + marginalia)
            all_tables.extend(tables)
            all_figures.extend(figures)
            page_meta.append({
                "page": index + 1, "width": round(width, 2), "height": round(height, 2),
                "column_bounds": [round(value, 2) for value in bounds],
                "n_blocks": len(blocks), "n_tables": len(tables), "n_figures": len(figures),
                "status": "unreadable" if not blocks and not figures else "ok",
            })
        if plumber is not None:
            plumber.close()
    finally:
        doc.close()
    all_blocks.sort(key=lambda block: (block.page, block.reading_order))
    for index, block in enumerate(all_blocks):
        if block.role not in ("header", "footer"):
            block.reading_order = index
    propagate_abstract(all_blocks)
    sections = build_section_hierarchy(all_blocks)
    link_continuations(all_blocks)
    link_figure_captions(all_figures, all_blocks)
    equations = build_equations(all_blocks)
    logical_tables = merge_cross_page_tables(all_tables, page_meta, all_blocks)
    reading_items = build_reading_items(all_blocks, logical_tables, all_figures)
    # Keep detailed spans only where they add structural evidence.
    for block in all_blocks:
        if block.role not in ("title", "authors", "affiliation", "abstract", "heading", "equation"):
            block.spans = []
    parsed = {
        "schema": "sci-pdf-reading-parse/parsed/v3", "case_id": case_id,
        "source": os.path.basename(pdf_path), "pages": page_meta,
        "document": _document_summary(all_blocks, sections, logical_tables, all_figures, equations),
        "blocks": [asdict(block) for block in all_blocks],
        "tables": logical_tables, "figures": all_figures, "equations": equations,
        "reading_items": reading_items, "warnings": warnings,
        "stats": {
            "n_pages": page_count, "n_blocks": len(all_blocks), "n_tables": len(logical_tables),
            "n_figures": len(all_figures), "n_equations": len(equations),
            "n_body_chars": sum(b.n_chars for b in all_blocks if b.role == "body"),
            "n_total_chars": sum(b.n_chars for b in all_blocks),
            "roles": {role: sum(1 for b in all_blocks if b.role == role)
                      for role in sorted({b.role for b in all_blocks})},
        },
    }
    block_map = {block.id: block for block in all_blocks}
    table_map = {table["id"]: table for table in logical_tables}
    figure_map = {figure["id"]: figure for figure in all_figures}
    parts = []
    for item in reading_items:
        if item["kind"] == "block":
            parts.append(block_map[item["id"]].text)
        elif item["kind"] == "table":
            parts.append(table_map[item["id"]]["markdown"])
        else:
            figure = figure_map[item["id"]]
            caption = block_map.get(figure.get("caption_id"))
            parts.append("[Figure %s]%s" % (figure["id"], (" " + caption.text) if caption else ""))
    return parsed, "\n\n".join(parts)


def render_markdown(parsed):
    lines = [f"# Reading-order extraction — {parsed['source']}", ""]
    block_map = {block["id"]: block for block in parsed["blocks"]}
    table_map = {table["id"]: table for table in parsed["tables"]}
    figure_map = {figure["id"]: figure for figure in parsed.get("figures", [])}
    current_page = None
    for item in parsed.get("reading_items", []):
        if item["page"] != current_page:
            current_page = item["page"]
            lines.extend([f"\n<!-- page {current_page} -->", ""])
        if item["kind"] == "table":
            table = table_map[item["id"]]
            lines.extend([f"<!-- {table['id']} p{table['page']} bbox={table['bbox']} -->",
                          table["markdown"], ""])
            continue
        if item["kind"] == "figure":
            figure = figure_map[item["id"]]
            lines.append(f"**[{figure['kind']} {figure['id']}]** <!-- p{figure['page']} bbox={figure['bbox']} -->")
            continue
        block = block_map[item["id"]]
        anchor = f"[{block['id']} p{block['page']} bbox={block['bbox']}]"
        role = block["role"]
        if role == "title":
            lines.append(f"# {block['text']}  <!-- {anchor} -->")
        elif role == "heading":
            level = min(6, max(2, (block.get("level") or 1) + 1))
            lines.append(f"{'#' * level} {block['text']}  <!-- {anchor} -->")
        elif role == "caption":
            lines.append(f"*{block['text']}*  <!-- {anchor} -->")
        elif role == "footnote":
            lines.append(f"<small>{block['text']}</small>  <!-- {anchor} -->")
        elif role == "equation":
            lines.append(f"{block['text']}  <!-- equation {anchor} -->")
        else:
            lines.append(f"{block['text']}  <!-- {anchor} -->")
    return "\n".join(lines)


def _write_text_atomic(path, text):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-anchored scientific PDF parser v3")
    parser.add_argument("pdf")
    parser.add_argument("--out", default="parsed_out")
    parser.add_argument("--case-id", default="")
    parser.add_argument("--max-pages", type=int, default=None)
    args = parser.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    try:
        parsed, _ = parse(args.pdf, args.case_id, args.max_pages)
        _write_text_atomic(os.path.join(args.out, "parsed.json"),
                           json.dumps(parsed, ensure_ascii=False, indent=1))
        _write_text_atomic(os.path.join(args.out, "reading.md"), render_markdown(parsed))
    except ValueError as exc:
        print(json.dumps({"status": "failed", "source": os.path.basename(args.pdf),
                          "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "failed", "source": os.path.basename(args.pdf),
                          "error": f"unexpected parser failure: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "source": parsed["source"],
                      "stats": parsed["stats"], "warnings": parsed["warnings"],
                      "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
