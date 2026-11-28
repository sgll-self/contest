---
name: sci-pdf-reading-parse
description: "Evidence-anchored scientific PDF parser for tasks such as 'parse this paper', 'read this PDF and answer with evidence', 'extract text/tables/equations', '文献解析', '科研阅读', 'reading order', and two-column extraction. Restores column-aware order, section hierarchy, cell-level and cross-page tables, formula scripts and Unicode glyphs, raster/vector figure anchors, footnotes and references. Includes optional content-hash document memory and cross-document evidence merge. Use only for PDF structure/extraction; do not trigger for general chat, non-PDF text, or requests to infer the scientific meaning of a figure or equation."
---

# sci-pdf-reading-parse — 科研 PDF 结构解析与证据回锚

将科研 PDF 转为**按阅读顺序排列、结构明确、逐项可回锚**的结果。核心原则是保留原文证据、报告不确定性，不用猜测补齐扫描件、乱码或缺失材料。

## 1. 适用边界

适用于有文字层的单栏、双栏及多栏 PDF，以及已 OCR 的页面。无文字层扫描件仍需 OCR；本 Skill 会标出 `unreadable_pages`，不会伪造文本。公式输出保留 Unicode 原文并恢复上下标的线性结构，不声称生成完整语义 LaTeX；图片/矢量图提供位置与题注关联，不解释科学含义。

## 2. 固定案例工作流（优先使用）

脚本路径均相对于本 `SKILL.md` 所在目录，不依赖当前工作目录。

1. **准备案例并尽早保存部分结果**：
   ```bash
   python "$SKILL_DIR/scripts/case_workflow.py" prepare \
     --case /input/case.json --task /input/task.md --out /app/output --work /app/work
   ```
   该步骤解析实际 PDF，而非根据文件名推断内容；写出 `/app/output/result.json`、`reading.md` 和每案例 `evidence.json`。`result.json` 已包含 `output_contract` 要求的字段、`case_id`、状态、来源、不确定性和变更记录。
2. **阅读实际材料**：读取 `/app/output/reading.md` 与 `evidence.json` 指向的 `parsed.json`。按 `reading_items` 的顺序理解正文、章节、表格和图；关键答案必须回到真实 `id/page/bbox`。
3. **完成问题**：依据 `task.md` 填写全部契约字段。原文未报告、无法判断、材料冲突、扫描件和加密失败分别说明，不得写成事实。
4. **最终校验**：
   ```bash
   python "$SKILL_DIR/scripts/case_workflow.py" validate \
     --case /input/case.json --result /app/output/result.json --work /app/work
   ```
   校验器检查必填字段、状态和全部证据 ID/页码；未知锚点会使校验失败。校验通过后再结束任务。

## 3. 单篇 PDF 直接调用

```bash
python "$SKILL_DIR/scripts/parse_pdf.py" INPUT.pdf --out parsed --case-id CASE_ID
python "$SKILL_DIR/scripts/verify.py" INPUT.pdf --parsed parsed/parsed.json --out parsed/verify.json
```

产物为 `parsed.json` 和 `reading.md`；验证器生成 `verify.json`。`--max-pages N` 仅用于明确限定的调试或演示，正式案例默认解析全文。

## 4. 输出结构（schema v3）

- `document`：标题、作者、单位、摘要及其块 ID；`sections[]` 含编号、层级、父节点、`section_path`。
- `blocks[]`：稳定 `id`、`page`、`bbox`、`text`、未规范化 `raw_text`、`role`、`column`、`reading_order`、`source_line_ids`；跨栏/跨页续接以 `continuation_of` 表达，不擅自合并段落。
- `tables[]`：`pages`、`segments`、`n_rows/n_cols`；每个单元格含 `row/col/text/bbox/row_span/col_span/covered_by`。重复表头删除有记录， constituent 文本标为 `table_text`，表格在阅读流中仅出现一次。
- `equations[]`：`unicode_text`、`linear_text`、上下标 `scripts`、公式编号、逐 span 字体/bbox、`needs_review`。
- `figures[]`：位图或矢量候选的 `page/bbox/kind/caption_id`；`table_candidate_reclassified_figure` 警告保留判定依据。
- `reading_items[]`：块、表格、图的统一顺序；`warnings[]` 记录降级和失败。
- `verify.json`：文本层覆盖、行级边距泄漏、顺序内部诊断、`reading_anchor_coverage` 和锚点错误。内部诊断不是独立人工真值准确率。

## 5. 关键方法

- **稀疏分栏与栏内标题**：大块先建立栏组，小居中块若同时跨越两组则作为桥接碎片排除；只有实际宽块或跨越栏界的块才是全宽分隔符。标题、题注不因角色而被强制跨栏。
- **混合块拆分**：按原始文本行的边距带和字号突变拆分页眉/标题等混合物理块，保留行级来源，避免整块边距规则误删标题。
- **表格原位与跨页续表**：单元格 bbox 推导合并跨度；Markdown 转义 `|`、换行转为 `<br>`；相邻页、列数一致且位于页断点附近，并有重复表头或 continued 题注时才合并。
- **公式后处理**：根据 span 字号、基线与 superscript flag 恢复 `^{...}`/`_{...}`。若 PyMuPDF 出现替换符，且本机存在 Poppler `pdftotext`，仅对相同页/bbox 的词进行恢复，并要求 ASCII 骨架一致；失败则标 `needs_review`。Symbol/Dingbats 的可疑 ASCII 映射不直接当作希腊字母。
- **结构覆盖**：识别标题、作者/单位混合块、摘要续块、编号章节、图/表中英文题注、脚注及数字/作者开头的参考文献。

## 6. 可审计文档记忆与跨文档合并（可选）

```bash
python "$SKILL_DIR/scripts/document_memory.py" ingest a.pdf --memory /app/work/memory
python "$SKILL_DIR/scripts/document_memory.py" ingest b.pdf --memory /app/work/memory
python "$SKILL_DIR/scripts/document_memory.py" query "exact phrase" --memory /app/work/memory
python "$SKILL_DIR/scripts/document_memory.py" merge --memory /app/work/memory --out /app/output/collection.json
```

记忆以 PDF 的 SHA-256 和解析 schema 为键；相同字节重复载入直接复用结构，文件改变会产生新键。查询为精确/大小写折叠匹配，结果带文档哈希和原始锚点。合并采用来源前缀 ID 的有序拼接，**不做未经证实的语义去重或跨论文事实融合**。首次 ingest 仍需完整解析，缓存只改善重复文档场景。

## 7. 异常与降级

- 加密 PDF：空口令失败时明确报错，CLI 退出码 2；损坏或不存在文件同样返回失败状态。
- 无文字层页面：标为不可读并保留人工接管位置；状态应为 `partial` 或 `failed`。
- 缺少 pdfplumber：不猜表格，写 `pdfplumber_unavailable` 警告；安装 `scripts/requirements.txt` 后重跑。
- 公式或字体无法核验：保留原文与 `needs_review`，不得编造符号。
- 最终输出：保留 `status`、`sources`、`uncertainty`、`change_log`，并运行固定案例校验器。

## 8. 依赖与复现证据

核心依赖为 `pymupdf>=1.24`、`pdfplumber>=0.11`；`pdftotext` 是可选字形恢复后端。复现与测试还需 matplotlib、reportlab。运行 `python src/reproduce.py` 可重建全部受控真值、真实论文、异常、记忆与工作流证据。实测定义和结果见 `execution/results/metrics.json`、`advanced_checks.json`、`integration_checks.json`；完整日志以 `execution/run.txt` 收录。
