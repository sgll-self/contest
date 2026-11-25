---
name: sci-pdf-reading-parse
description: "Evidence-anchored scientific PDF reading-order parser. Use when a task asks to read/parse a scientific PDF and answer questions WITH source evidence: extract body text verbatim, fix two/multi-column reading order (no column interleaving), recover section hierarchy, table rows/cols/cells, equation numbers and special characters, and anchor every result back to a page + bounding box. Trigger on: 'parse this paper', 'read this PDF and answer', 'extract text/tables from this PDF', '文献解析', '科研阅读', '回答问题也给出依据', 'reading order', 'two-column extraction'. Produces structured, located, self-verified output; flags unreadable parts instead of guessing."
---

# sci-pdf-reading-parse — 科研 PDF 阅读顺序解析与证据回锚

把一份科研 PDF 解析成**可用、可核验、可回锚**的结构化结果，而不是「看起来像全文」的一段文本。
聚焦题面四个检查点：**提得全 · 排得对 · 拆得清 · 核得回**。

## 何时使用 / 适用条件
- 输入是 PDF（含双栏/多栏会议论文、期刊论文、预印本），任务要求阅读、解析、提取、问答并给出原文依据。
- 适用：有文字层的 PDF（原生或已 OCR）。对**无文字层的纯扫描件**，本 Skill 如实标注 `unreadable`，不猜补（见异常处理）。
- 不适用：需要理解图表/公式科学含义的任务——本 Skill 只做**结构元素识别与保真提取**，不做科学推断。

## 调用方式（Agent 工作流）
脚本相对本 SKILL.md 所在目录解析。设 `SKILL_DIR` 为本文件目录。

1. **识别输入与边界**：读取 `/input/case.json` 与 `/input/task.md`（或用户给定的 PDF 路径与问题）。
   从 case.json 取出 `case_id` 与 `output_contract`（输出字段契约）；**不要**凭领域标签假设内容。
2. **运行解析器**（一次确定性调用，无网络、无模型）：
   ```bash
   python "$SKILL_DIR/scripts/parse_pdf.py" INPUT.pdf --out /app/work/parsed --case-id CASE_ID
   ```
   产出 `parsed.json`（带证据锚点的结构）、`reading.md`（按版面顺序的 markdown）。
3. **自检**（覆盖率/顺序/泄漏诊断）：
   ```bash
   python "$SKILL_DIR/scripts/verify.py" INPUT.pdf --parsed /app/work/parsed/parsed.json --out /app/work/parsed/verify.json
   ```
4. **作答与回锚**：基于 `reading.md` 回答问题；每个关键结论引用 `parsed.json` 中的
   `block.id` / `page` / `bbox`（或 `table.id`）。无法从材料判断的，明确写「未报告/无法判断」。
5. **写出结果**：在 `/app/output/result.json` 写入 case.json `output_contract` 要求的**全部字段** + `case_id`，
   并附 `status`、`sources`（证据定位）、`uncertainty`、`change_log`。工作产物留在 `/app/work`。

## 输入 / 输出
- 输入：`INPUT.pdf`；可选 `--case-id`、`--max-pages N`。
- `parsed.json` 关键字段：
  - `pages[]`：每页宽高、检测到的分栏边界 `column_bounds`、块/表计数。
  - `blocks[]`：`id`、`page`(1-based)、`bbox`[x0,y0,x1,y1]、`text`(逐字)、`role`
    (body/header/footer/caption/heading/reference/equation)、`column`(-1=跨栏)、`reading_order`、`font_size`。
  - `tables[]`：`id`、`page`、`bbox`、`n_rows`、`n_cols`、`cells[{row,col,text}]`、`markdown`、`extractor`。
  - `stats`：块/表/字符计数与角色分布。
- `verify.json`：`char_recall`、`marginalia_leak`、`order_monotonic`、`unreadable_pages`、`notes`。

## 关键方法（为什么排得对、拆得清）
- **分栏检测**：按块水平中心聚类，最大间隙切分 2/3 栏；宽度 > 0.62×页宽的块视为跨栏带分隔符。
- **阅读顺序**：跨栏块按 y 作为「带」分隔；带内各栏**从左到右**、每栏**从上到下**；跨页按页序。
  这避免双栏「串栏/错行」，也不把相邻段落拼成一句。
- **页眉页脚**：跨页重复字符串 + 页码样式 + 极窄边距带内小字号块 → 标 header/footer，**不混入正文**。
- **表格保真**：单元格文本用 **pdfplumber** 重建（PyMuPDF `find_tables().extract()` 会把 cell 内字形重排，
  如 `0.99`→`099.`）；保留 row/col 归属与 bbox。这是相对常见解析器的一个实质改进点。
- **公式/特殊字符**：逐字保留 unicode（希腊字母、上下标）；按数学符号密度与尾部编号 `(n)` 标 equation。

## 异常处理（可靠体验）
- **加密 PDF**：尝试空口令认证；失败则在 result.json `status="failed"`、`uncertainty` 注明加密。
- **无文字层扫描件**：`verify.json.unreadable_pages` 列出；result.json 标 `status="partial"`，
  说明需 OCR（超出本文字层解析器范围），**不伪造文本**。
- **图片型表格 / 乱码字体**：表格检测尽力而为；检不出则 `tables` 为空并在 notes 说明，不猜补单元格。
- **材料冲突 / 未报告**：在答案与 `uncertainty` 中如实区分「原文未报告」「无法判断」「材料相互冲突」。

## 自查方法
运行 `verify.py`：`char_recall` 应接近 1（漏行/丢段会拉低）；`marginalia_leak` 应≈0；
`order_monotonic` 反映栏内顺序合理性。任何低分都作为**限制**上报，而不是掩盖。

## 最小调用示例（示意，非正式案例结果）
见 `examples/` 目录：输入 `examples/sample_input.json`，调用上述脚本，示意输出 `examples/sample_output.json`
（明确标注为 EXAMPLE）。正式 3 案例由平台提供，本 Skill 不预置答案。

## 依赖与版本
`pymupdf>=1.24`、`pdfplumber>=0.11`（表格保真）；标准库其余。见 `scripts/requirements.txt`。
解析器本体 `scripts/parse_pdf.py`、自检 `scripts/verify.py` 可被他人直接复用。