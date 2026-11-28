# sci-pdf-reading-parse

**Bohrium Playground · product-arena-08-3027d350 · 阅读01｜文献文档解析**

可被 Agent 调用的科研 PDF 解析 Skill。v3 聚焦评分中的基础正确性与完整性：逐行文字来源、跨栏阅读顺序、原位表格、合并单元格与跨页续表、章节层级、公式上下标和 Unicode 字形、图表位置、脚注、参考文献及逐项证据锚点；另提供可审计文档记忆和跨文档证据合并。

## 1. 提交目录

```text
SKILL.md                     触发条件、固定案例工作流、输入输出与限制
scripts/parse_pdf.py         核心解析器（parsed/v3）
scripts/verify.py            行级覆盖、边距泄漏与阅读锚点检查（verify/v3）
scripts/case_workflow.py     固定案例准备、提前保存部分结果、最终证据校验
scripts/document_memory.py   内容寻址缓存、精确查询、跨文档来源合并
scripts/advanced_tests.py    结构/公式/跨页表受控真值与负面对照
scripts/integration_tests.py 确定性、记忆和完整安全链路集成测试
scripts/verify_gain.py       基础阅读顺序增益复核
scripts/requirements.txt     运行与复现依赖
src/reproduce.py             一键完整复现入口
examples/                    明确标注 EXAMPLE 的接口示例
execution/run.txt            本次真实运行日志
execution/results/*.json     实际解析、指标、高级与集成测试证据
execution/results/document_collection.md  跨文档合并的可读证据
characterization.json        能力包络、指标定义与失败模式
GITHUB_URL.txt               公开作品链接
```

所有 Skill 资源均为 UTF-8 文本；PDF、PNG 和缓存数据库文件仅由脚本写入运行期工作目录，不进入资源包。

## 2. 调用

### 单篇 PDF

```bash
pip install -r scripts/requirements.txt
python scripts/parse_pdf.py paper.pdf --out parsed --case-id my-case
python scripts/verify.py paper.pdf --parsed parsed/parsed.json --out parsed/verify.json
```

`parsed/reading.md` 按统一 `reading_items` 顺序穿插正文、表格和图；`parsed.json` 保存全部结构及页码/bbox。

### 固定案例安全链路

```bash
python scripts/case_workflow.py prepare --case /input/case.json --task /input/task.md --out /app/output --work /app/work
# Agent 阅读 reading.md，回答 task.md 并填写 output_contract 的全部字段
python scripts/case_workflow.py validate --case /input/case.json --result /app/output/result.json --work /app/work
```

准备阶段即写出诚实的部分结果；最终校验拒绝未知证据 ID、错误页码、缺失字段和 case_id 不匹配。

### 文档记忆与跨文档合并

```bash
python scripts/document_memory.py ingest a.pdf --memory work/memory
python scripts/document_memory.py ingest b.pdf --memory work/memory
python scripts/document_memory.py query "exact phrase" --memory work/memory
python scripts/document_memory.py merge --memory work/memory --out output/collection.json
```

缓存键为文件 SHA-256 与解析 schema；合并结果保留 `document_sha256`、`source_id` 和 `global_id`，不做无依据的语义去重。该能力是可选增强，不影响单篇解析。

## 3. 本次实际验证

复现命令：

```bash
python src/reproduce.py
# 不需要运行期图形时：python src/reproduce.py --skip-figures
```

### A. 基础受控真值

| 指标 | Skill | 对照 |
|-|-:|-:|
| 小写化、去空白 GT 4-gram 召回 | 1.0000 | — |
| 完整 GT 字符串恢复率 | 1.0000 | — |
| 阅读顺序成对一致性（28 对） | 1.0000 | naive 纯纵向排序 0.8929 |
| 行级列内连续率（双方同为 14 行） | 0.9231 | naive 0.0769 |
| 表格单元格匹配（9 格） | 1.0000 | PyMuPDF 0.5556 |
| 行级几何边距泄漏 | 0.0000 | — |
| 阅读项锚点覆盖 | 1.0000 | — |

### B. 新增基础与创新能力

`advanced_checks.json` 的 **16/16 项断言、4/4 项负面对照全部通过**：

- 标题、作者、单位、摘要和三级章节的编号、父节点及路径；
- 稀疏双栏中栏内标题/题注不打断列主序，交换左右栏会被负面对照检测；
- 公式编号 `(12)`、`x^{2}`、`y_{i}` 和 `α/β/γ`；替换符经 Poppler bbox 对齐恢复，Symbol 风险字体必须进入人工复核；
- 位图位置与 `Fig. S1` 题注关联，中英文题注、脚注与三种参考文献样式；
- 两页表格合并、两行重复表头删除、合并表头 `col_span=2`、单元格 bbox、`a|b` 转义和多行单元格；
- 表格在阅读流中位于“前文 → 题注 → 表格 → 后文”，且只出现一次；缺少 pdfplumber 时明确降级；
- 中文与法文重音字符逐字保留。

负面对照分别交换栏顺序、替换希腊字母、改变表格形状和修改单元格值，均被对应断言拒绝。

### C. 真实开放论文

对 arXiv 1512.03385 的**前 6/12 页**解析，缓存 SHA-256 为 `1e0651b6810ecba34a3dbc5b5b0209226f889004607c1f203540a48d64e5a93a`。输出 357 块、3 个逻辑表格、4 个图位置、7 个公式候选、12 个标题、11 个题注、3 个脚注；标题、作者、单位和完整摘要均有显式字段。内部覆盖和阅读锚点覆盖均为 1.0000，边距泄漏为 0.0000。

这些计数和内部诊断证明真实输入上的运行与结构输出，**不构成独立人工真值准确率**。

### D. 记忆、可靠性与效率

`integration_checks.json` 的 **9/9 项检查通过**：三次重复解析结构一致、缓存命中、两个文档幂等入库、精确查询回锚、希腊字母查询定位公式、跨文档来源前缀唯一、合法结果通过、伪造锚点被拒绝、缺失材料明确失败。

同一受控 PDF 三次直接冷解析中位耗时 **0.045682 秒**，三次内容哈希缓存命中中位耗时 **0.003281 秒**，重复文档场景实测 **13.923×**；首次 ingest 为 **0.051916 秒**，仍需完整解析，不宣称首次提速。

无文字层图片页、非空密码加密 PDF、损坏 PDF 均按预期报告。完整复现总耗时 **6.37 秒**，真实论文前六页解析 **1.1505 秒**。数值均来自 `execution/results/metrics.json` 和 `execution/run.txt`。

## 4. 适用范围与限制

当前定量包络覆盖单栏/双栏、多页受控文档、中文/英文/法文文本、位图与由题注确认的矢量图候选、两行表头的两页续表。三栏虽有算法支持，但尚未纳入定量真值包络。无文字层扫描件仍需 OCR；图片型表格、复杂嵌套表、完整公式语义 LaTeX、跨文档语义推理不属于已验证能力。矢量图位置来自被拒绝的表格候选与邻近图题注，需结合 `warnings` 复核。

维护与复现以本目录为准；修改解析器后必须重新运行 `src/reproduce.py`，并确认 `acceptance` 的四项检查全部为 true。
