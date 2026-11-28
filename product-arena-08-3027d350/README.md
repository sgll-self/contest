# sci-pdf-reading-parse

**Bohrium Playground · product-arena-08-3027d350 · 阅读01｜文献文档解析**

可被 Agent 调用的科研 PDF 解析 Skill，聚焦**提得全、排得对、拆得清、核得回**。输出带页码、区块坐标和稳定 ID 的结构化结果，并明确报告不可读内容与验证边界。

## 1. 问题与方法

双栏、多栏论文的直接纵向提取容易串栏，页眉页脚可能混入正文，表格单元格还可能发生字形重排。本 Skill 采用确定性文本层解析，不调用模型或网络服务：

- **阅读顺序**：检测跨栏带与栏边界，带内按栏从左到右、栏内从上到下输出。
- **连续块合并**：对同字号、垂直相接且水平重叠率不低于 0.6 的物理块进行保守合并，避免居中摘要的短续行被误识别为中间列。
- **页眉页脚**：结合 8% 顶部／底部几何边距、跨页重复、页码样式和相对字号识别，不将已识别边注写入阅读正文。
- **表格结构**：使用 pdfplumber 保留行、列、单元格和表格 bbox；检测失败时不猜补单元格。
- **证据回锚**：每个文本块和表格均保留 `id`、`page`、`bbox`；无文字层页面明确标为不可读。

## 2. 提交目录

```text
SKILL.md                     Skill 触发条件、工作流、输入输出和异常处理
scripts/parse_pdf.py         核心解析器
scripts/verify.py            文本层覆盖、边距泄漏与顺序一致性诊断
scripts/verify_gain.py       受控指标增益规则复核
scripts/requirements.txt     运行依赖
src/reproduce.py             受控真值、真实论文和异常输入复现入口
examples/                    明确标注 EXAMPLE 的接口示例
execution/run.txt            本次实际运行的 UTF-8 日志（以 .txt 收录，.log 不是允许的 Skill 资源）
execution/results/*.json     本次实际指标、解析结果、验证和边界测试
characterization.json        实测范围、指标定义和失败模式
GITHUB_URL.txt               公开作品链接
```

题面规定 Skill 资源必须是最多 50 个 UTF-8 文本文件，单文件不超过 500KB、总量不超过 2MB。因此，复现脚本生成的 PDF 和 PNG 仅为**运行期产物**，不纳入 Skill 资源包；提交证据采用 JSON、Markdown 和日志。

## 3. 安装与调用

```bash
pip install -r scripts/requirements.txt
python scripts/parse_pdf.py paper.pdf --out parsed --case-id my-case
python scripts/verify.py paper.pdf --parsed parsed/parsed.json --out parsed/verify.json
```

产物为 `parsed/parsed.json`、`parsed/reading.md` 和 `parsed/verify.json`。若解析时使用 `--max-pages`，验证器默认跟随 `parsed.json` 的实际页数，避免将部分解析与整篇原文直接比较。

Agent 完整流程见 `SKILL.md`：读取实际案例与输出契约，运行解析和自检，依据证据锚点作答，并在 `result.json` 中保留 `case_id`、`status`、`sources`、`uncertainty` 和变更记录。

## 4. 本次实际验证

复现命令：

```bash
python src/reproduce.py
# 不需要运行期图形时可使用：python src/reproduce.py --skip-figures
```

### A. 单页受控双栏真值

受控文档包含已知顺序的标题、摘要、左右各三段正文、页眉页脚和 3×3 有框表格。

| 指标 | Skill | 对照 |
|-|-:|-:|
| 小写化、去空白 GT 4-gram 召回 | 1.0000 | — |
| 完整 GT 字符串恢复率 | 1.0000 | — |
| 阅读顺序成对一致性（28 对） | 1.0000 | naive 纯纵向排序 0.8929 |
| 行级列内连续率（双方同为 14 行） | 0.8462 | naive 0.0769 |
| 表格单元格匹配（9 格，大小写敏感、去空白） | 1.0000 | PyMuPDF 0.5556 |
| 内部文本层字符覆盖 | 1.0000 | — |
| 几何边距字符泄漏 | 0.0000 | — |

连续性比较使用完全相同的原始文本行，仅改变排序依据，避免文本块数与文本行数混用。表格对照直接复测了 PyMuPDF 的 `099.`、`052.`、`100.` 等重排结果。

### B. 真实开放论文

对 arXiv 1512.03385 的**前 6 页（原文件共 12 页）**进行解析，缓存文件 SHA-256 为 `1e0651b6810ecba34a3dbc5b5b0209226f889004607c1f203540a48d64e5a93a`。本次输出 337 个文本块、7 个表格、20 个公式候选块、22 个标题候选块、11 个题注和 6 个页脚块。内部文本层覆盖为 1.0000，几何边距泄漏为 0.0000。

这些真实论文计数和内部诊断仅证明实际运行与覆盖情况，**不构成经外部人工真值标注的准确率**。

### C. 异常与性能

- 无文字层图片页：输出 0 个文本块，`unreadable_pages=[1]`，断言通过。
- 非空密码加密 PDF：空口令认证失败，给出明确错误，命令行退出码为 2。
- 本次受控页解析约 0.04 秒，真实论文前六页解析约 1.03 秒，包含复现、验证和图形的总运行时间为 4.64 秒。缓存真实论文可避免重复下载，布局图复用已解析结果，不再重复解析受控文档。

所有数值见 `execution/results/metrics.json`，完整输出见 `execution/run.txt`。

## 5. 适用范围与限制

适用于有文字层的单栏、双栏和多栏科研 PDF；当前定量包络仅实测单页受控双栏文档和真实双栏论文前六页。纯扫描件需要 OCR，图片型表格、复杂合并单元格、乱码字体和公式语义理解不属于已验证能力。`verify.py` 是内部文本层诊断，不替代独立人工真值评估；低覆盖、边距泄漏和不可读页应作为限制报告。
