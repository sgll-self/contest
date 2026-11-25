# sci-pdf-reading-parse

**Bohrium Playground · product-arena-08-3027d350 · 阅读01｜文献文档解析**

一个可被 Agent 调用的科研 PDF 解析 Skill，聚焦题面四个检查点：**提得全 · 排得对 · 拆得清 · 核得回**。
它把 PDF 解析成带证据锚点的结构化结果，而不是「看起来像全文」的文本。

---

## 1. 它解决什么

科研论文常用双栏/多栏版式。常见的「 naive 自上而下」文字提取会**串栏、错行、漏段**，把左右两栏交错拼接，
导致后续翻译/问答/知识提取读到拼错的句子；页眉页脚混进正文；表格单元格字形被重排（`0.99`→`099.`）。

本 Skill 的解析器：
- **排得对**：分栏检测 + 「跨栏带分隔、栏内左→右、每栏上→下」的阅读顺序，跨页按页序。
- **提得全**：正文/题注/脚注/参考文献逐字提取；页眉页脚识别后排除，不混入正文。
- **拆得清**：章节标题、表格 row/col/cell、公式编号与希腊字母/上下标保真。
- **核得回**：每个块/表都带 `page` + `bbox` + `id`，任何答案可回锚到原文区域；读不出的如实标注。

## 2. 目录结构

```
SKILL.md                     Skill 本体（frontmatter + 工作流 + 异常处理）
scripts/parse_pdf.py         核心解析器（确定性、无网络、无模型）
scripts/verify.py            覆盖率/顺序/泄漏自检
scripts/requirements.txt     依赖与版本
src/reproduce.py             ARM entrypoint：受控真值测试 + 真实论文演示
examples/                    最小调用示例（明确标注 EXAMPLE，非正式案例）
execution/run.log            实际演示运行日志
execution/results/           实际产物：metrics.json、gt_parsed.json、real_parsed.json、fig_*.png
characterization.json        经验包络 / 失败模式 / 数值偏差
trace/trace.jsonl            实际运行的 typed-step 轨迹
arm_manifest.json            ARM v1.1 清单
```

## 3. 安装与调用

依赖：`pymupdf>=1.24`、`pdfplumber>=0.11`（演示另需 `matplotlib`、`reportlab`）。
```bash
pip install -r scripts/requirements.txt
```

解析一份 PDF：
```bash
python scripts/parse_pdf.py paper.pdf --out parsed --case-id my-case
python scripts/verify.py  paper.pdf --parsed parsed/parsed.json --out parsed/verify.json
```
产物：`parsed/parsed.json`（结构+锚点）、`parsed/reading.md`（版面顺序文本）、`parsed/verify.json`（自检）。

Agent 完整工作流见 `SKILL.md`：读 `/input/case.json`+`task.md` → 解析 → 自检 → 作答回锚 →
写 `/app/output/result.json`（含 output_contract 全部字段 + case_id + status/sources/uncertainty/change_log）。

## 4. 实际验证证据（可复核，非自述）

`src/reproduce.py` 在两条输入上实跑：

**A. 受控真值文档**（自己生成、已知正确答案，故可算精确数值指标）：
| 指标 | Skill | Naive 基线 |
|-|-|-|
| 文本召回 char_recall | **1.000** | — |
| 阅读顺序一致性 concordance | **1.000** | 0.893 |
| 行级列内连续率 column_continuity | **0.667** | 0.077 |
| 表格单元格匹配 table_cell_match | **1.000** | — |
| 页眉泄漏正文 | **否** | — |

行级列内连续率 0.077→0.667（约 8.7×）直接量化了「串栏」修复幅度。

**B. 真实开放论文**（arXiv 1512.03385，He et al. *Deep Residual Learning*，双栏 CVPR 版式，实下载）：
6 页解析出 356 块、7 表、22 公式块、27 标题、11 题注；SHA-256 记录于 `metrics.json`。

图表（真实渲染 PNG）：`fig_order.png`（顺序一致性对比）、`fig_recall.png`（提取保真）、
`fig_layout.png`（页面渲染 + 检测分栏 + 阅读顺序编号叠加）。

复现：`python src/reproduce.py`（约 4 秒，日志写入 `execution/run.log`）。

## 5. 关键方法改进点（创新增益）

1. **跨栏带分隔的阅读顺序重建**：跨栏块作带分隔符，栏内列主序，避免串栏。
2. **表格单元格 pdfplumber 重建**：规避 PyMuPDF `find_tables().extract()` 的 cell 内字形重排伪影
   （受控测试中 `0.99`→`099.`，改用 pdfplumber 后单元格匹配 0.556→1.000）。
3. **单页也成立的页眉页脚识别**：重复串 + 页码样式 + 边距带小字号三重判据。
4. **诚实自检**：`verify.py` 把低召回/泄漏/不可读页作为限制上报，不猜补。

## 6. 适用范围与限制

- 适用：有文字层的科研 PDF（原生/已 OCR），双栏/多栏/单栏。
- 限制：纯扫描件无文字层 → 标 `unreadable`，需 OCR（不在本文字层解析器范围）；
  图片型表格/乱码字体尽力而为；图表/公式只做结构识别，不做科学含义理解。
- 运行预算友好：解析为单次确定性脚本调用，适配平台 64 请求 / 900 秒预算。

## 7. 复用与维护

解析器 `scripts/parse_pdf.py` 与自检 `scripts/verify.py` 为独立可复用模块（标准库 + pymupdf/pdfplumber）。
版本与依赖见 `scripts/requirements.txt`。示例见 `examples/`（标注 EXAMPLE）。