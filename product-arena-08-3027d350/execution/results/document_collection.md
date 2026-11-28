# Evidence-preserving document collection

## gt.pdf
SHA-256: `724abd49fe36943efbbdd72f3ede647eba7d06561725b500dfe8d4f504ddc11a`

Evidence-Anchored Reading Order for Two-Column Scientific Documents

We present a deterministic parser that recovers the true reading order of two-column scientific pages and anchors

every block to a page and bounding box.

L1 Introduction. Scientific documents frequently use a
two-column layout. A naive top-to-bottom text
extraction interleaves the columns and produces
broken sentences.

L2 Method. We cluster text blocks by horizontal
position, treat full-width blocks as band separators, and
order each column from top to bottom before moving
right.

L3 Anchoring. Every emitted block keeps its page
number and bounding box so that any downstream
answer can be traced back to the exact source region.

Table 1. Parsing quality on the controlled document.

R1 Evaluation. On a controlled document with known
ground truth we measure character recall and
reading-order concordance against the intended
sequence.

R2 Results. The parser recovers essentially all body
characters and preserves the column-major reading
order, while a naive y-sort interleaves the two columns.

R3 Limitations. Image-only scanned pages have no
text layer and require OCR, which is outside the scope
of this text-layer parser and is reported as unreadable.

| Method | Recall | Order |
| --- | --- | --- |
| Naive y-sort | 0.99 | 0.52 |
| Skill parser | 1.00 | 1.00 |

## structure_formula.pdf
SHA-256: `aa941726ec64cf2eb114199fc7e27f48f3480aabca2e957261f33b065f9ab3e1`

Structured Scientific Parsing with Verifiable Evidence

Alice A. Example, Bob B. Example

Department of Testing, Example University

Abstract—A controlled fixture for structure and formulas.

1. Introduction

This paragraph belongs to the first-level section and remains unchanged.

1.1. Layout

This paragraph belongs to the second-level section.

1.1.1. Ordering

This paragraph belongs to the third-level section.

x2 + yi = α + β = γ
(12)


Fig. S1 Controlled raster figure.

References

[1] First numeric reference.

2. Second numeric reference.

Example, A. Author-first reference.

* Controlled footnote retained verbatim with sufficient identifying text.

2. Sparse Layout

L1 sparse left column begins here and contains
enough words to establish the dominant column.

Fig. 2 Left-column caption.

L2 left column continues after its local caption without
moving to the right column.

R1 sparse right column starts at the same vertical
band but must follow all left content.

R2 right column finishes after the complete left-column
sequence.

中文段落：逐字提取、阅读顺序与证据定位。

Résumé : précision, intégrité et traçabilité.
