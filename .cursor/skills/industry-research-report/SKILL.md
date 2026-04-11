---
name: industry-research-report
description: Generate deep industry research reports from free-form user prompts, including title, key analysis text, and downloadable PDF/DOCX files. Use when the user asks for industry analysis, industry reports, sector deep dives, market outlooks, or competitive landscape research.
---

# Industry Research Report

## What this skill does

This skill generates a complete industry research report from user input and returns:

- report title
- truncated preview text
- local PDF and DOCX file paths
- local markdown source path
- local HTML share page path
- real-time data snapshot (compute/model/market layers)

## Trigger conditions

Apply this skill when the user intent matches industry cognition or report writing, for example:

- `XX 行业研究`
- `XX 行业报告`
- `帮我分析 XX 行业`
- `XX 产业深度研究`
- `XX 领域市场分析`

## Prerequisites

1. Python 3.9+
2. Install dependencies once:

```bash
pip install -r .cursor/skills/industry-research-report/requirements.txt
```

3. Set API key (required):

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

Optional:

```powershell
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o-mini"
```

## Workflow

### Step 1: Extract `{{topic}}`

Extract the core industry noun from user input:

- keep only the core topic
- remove filler phrases
- if multiple industries appear, use the primary one

Examples:

- `帮我生成一份半导体行业的研究报告` -> `半导体`
- `我想了解新能源汽车产业的发展趋势` -> `新能源汽车`
- `请分析消费电子与智能家居交叉趋势` -> `消费电子与智能家居`

### Step 2: Run report generation script

Run synchronously in the current session:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "{{topic}}"
```

Do not run this in background; wait for stdout JSON.

The script will fetch real data from public sources before writing:

- compute layer updates: GitHub releases/issues velocity for AI infra repos
- model layer updates: model ecosystem snapshots (e.g. Hugging Face model stats, core framework releases)
- market layer行情: AI-related ticker quotes and daily change

For tracking mode:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode daily
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode weekly
```

Or use tracker entry:

```bash
python .cursor/skills/industry-research-report/scripts/tracker.py --query "AI产业" --mode both --weekly-day 1
```

Use custom watchlist:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode daily --watchlist ".cursor/skills/industry-research-report/watchlist.json"
```

Theme auto-switch watchlist:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI算力和光模块跟踪" --mode daily --theme auto
python .cursor/skills/industry-research-report/scripts/get_data.py --query "大模型推理成本变化" --mode daily --theme auto
python .cursor/skills/industry-research-report/scripts/get_data.py --query "算力+模型协同趋势" --mode daily --theme auto --mix-top-k 2
```

Manual theme override:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode weekly --theme compute
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode weekly --theme model
```

Template style switch:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业景气度" --template-style industry_deep_dive
python .cursor/skills/industry-research-report/scripts/get_data.py --query "某AI公司首次覆盖" --template-style company_initiation
python .cursor/skills/industry-research-report/scripts/get_data.py --query "某AI公司估值与盈利预测" --template-style auto
```

Toggle optional modules:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究" --include-pest --include-five-forces --include-segmentation
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究（短版）" --no-include-pest --no-include-five-forces --no-include-segmentation
```

Quick presets:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究（短版）" --preset quick
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究（全量版）" --preset full
```

Narrative strength switch:

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业周报" --mode weekly --narrative-strength medium
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业深度研究" --narrative-strength high
```

### Step 3: Return result

Use this output template:

```markdown
《[title]》

已经生成行业研究报告。此处仅展示部分正文内容，请下载附件查看报告详情和参考信息。（不要删减这段话）

[truncated_text]...

**附件：**
- 📄 [title].pdf 已保存到 [pdf_output_path]
- 📄 [title].docx 已保存到 [docx_output_path]

**可编辑源文件：**
- 📝 Markdown: [md_output_path]
- 📦 JSON: [json_output_path]
- 📊 Data snapshot: [data_output_path]

**分享链接：**
[share_url]
```

If `truncated_text` is empty, summarize from generated markdown and fill non-empty text.

## Research Report Template (CN)

Use this section template when generating reports:

```markdown
# [行业/公司研究报告标题]

## 执行摘要
- 核心结论（3-5条）
- 关键证据（数据与事实）
- 投资/战略建议

## 数据快照（算力层 -> 模型层 -> 市场层）
- 实时更新要点
- 关键行情与异动
- 新闻与政策信号

## 第一章：公司概况与治理结构
### 1.1 公司简介与产品矩阵
### 1.2 历史沿革与关键战略变更
### 1.3 股权结构、核心团队与激励机制
### 1.4 财务概览（CAGR、ROE、现金流）

## 第二章：行业分析（量价框架）
### 2.1 行业定义与边界
### 2.2 产业链（上中下游）与关键环节
### 2.3 量：需求、渗透率、装机/订单先导指标
### 2.4 价：成本、ASP、溢价与利润结构
### 2.5 市场规模、增速与空间测算

## 第三章：竞争格局与竞争优势
### 3.1 竞争格局（CRn、5力、商业模式）
### 3.2 竞争优势验证（产品、技术、研发、客户、成本）
### 3.3 三维比较（同行比较 / 历史比较 / 国际比较）

## 第四章：预测与情景推演
### 4.1 核心驱动因素与边际变化
### 4.2 乐观/基准/悲观三情景
### 4.3 盈利预测与关键假设（收入、毛利、费用率）
### 4.4 敏感性分析与风险触发条件

## 风险与不确定性
- 政策风险
- 供需错配风险
- 技术迭代与替代风险
- 客户集中度风险

## 数据来源与口径说明
- 官方统计/行业协会/公司公告/权威机构优先
- 明确口径与时间区间
- 不以未经验证的二手自媒体数据作为核心论据

## 结论与建议
- 结论
- 投资建议/战略建议
- 后续跟踪指标
```

## Error handling

- `ERROR_TOPIC_TOO_LONG`: `字数超出限制，请尝试其它主体。`
- other failures: `报告生成服务暂时不可用，请稍后重试。`

## Universal Industry Template (Extended)

Use this expanded structure when you need a classic industry-analysis report:

```markdown
# [行业分析报告标题]

## 一、报告引言/摘要
### 1. 报告目的
### 2. 行业定义与范围
### 3. 核心结论摘要

## 二、行业发展环境分析
### 1. 宏观环境（PEST：政策/经济/社会/技术）
### 2. 产业链分析（上游/中游/下游/利润分配）

## 三、行业发展现状
### 1. 行业规模与增长（3-5年、CAGR）
### 2. 市场结构（CR3/CR5/CR10、企业类型）
### 3. 区域分布与差异原因

## 四、行业细分市场（可选）
### 1. 按产品/场景/客户拆分
### 2. 各细分市场规模、增速、竞争特点

## 五、行业竞争态势（波特五力）
### 1. 供应商议价能力
### 2. 购买者议价能力
### 3. 潜在进入者威胁
### 4. 替代品威胁
### 5. 现有竞争者竞争程度

## 六、行业趋势与前景
### 1. 未来3-5年趋势（技术/市场/模式）
### 2. 机遇与挑战
### 3. 市场规模预测（含预测依据）

## 七、标杆企业分析（可选）
### 1. 核心业务与定位
### 2. 竞争优势
### 3. 财务表现
### 4. 战略布局

## 八、结论与建议
### 1. 主要结论
### 2. 对企业建议
### 3. 对投资者建议

## 数据来源与口径
- 优先官方/协会/财报/权威机构数据
- 明确口径、时间区间和不确定性
```

## Notes

- All paths must use POSIX-style slashes in skill instructions.
- Keep secrets out of logs and responses.
- A/HK mapped tickers include:
  - 寒武纪 `688256.SS`
  - 中际旭创 `300308.SZ`
  - 工业富联 `601138.SS`
  - 腾讯控股 `0700.HK`
  - 阿里巴巴-SW `9988.HK`
- Watchlist is configurable in `.cursor/skills/industry-research-report/watchlist.json`:
  - `theme_keyword_map`: weighted keyword dictionary for theme match (e.g. `gpu: 2.0`, `算力: 1.0`, `推理: 1.5`)
  - `themes.default|compute|model|application`: per-theme symbol pools
  - `us_symbols_stooq`: list of US symbols for stooq feed
  - `cn_hk_symbols_yahoo`: map of symbol to display name for A/HK quotes
- Theme selection:
  - `--theme auto` uses query/topic keyword match
  - `--mix-top-k` controls how many themes are mixed in auto mode (default `2`)
  - if matched keywords include 算力/GPU/IDC/光模块 -> `compute`
  - if matched keywords include 模型/LLM/多模态/推理/训练 -> `model`
  - no match falls back to `default`
- Multi-theme weighted blend:
  - when auto mode hits multiple themes, the script mixes top themes by weighted keyword scores
  - symbol pools are merged and deduplicated
  - merged order follows total theme weights (higher weight first)
  - output includes `theme_mix` and `selected_theme` (example: `compute+model`)
  - `theme_mix` includes `raw_weighted_hits` and `matched_keywords` for explainability
- Template style:
  - `--template-style industry_deep_dive`: default industry deep-dive structure
  - `--template-style company_initiation`: company initiation/coverage structure
  - `--template-style auto`: keyword-based auto routing between the two styles
- Optional section toggles:
  - `--include-pest` / `--no-include-pest`
  - `--include-five-forces` / `--no-include-five-forces`
  - `--include-segmentation` / `--no-include-segmentation`
- Preset:
  - `--preset quick`: turn off PEST/Five-Forces/Segmentation for concise report
  - `--preset full`: turn on all optional sections
  - `--preset custom`: keep manual toggle values (default)
- Narrative strength:
  - `--narrative-strength medium`: short and concise style, faster reading
  - `--narrative-strength high`: deep argumentative style with fuller evidence chain (default)
- **Comparable company financial table vs non-listed innovators (writing rule for agents):**
  - The script post-processes a「重点公司财务对比表」that is **limited to listed issuers** (US SEC path); table rows use **full company names**, not bare ticker codes.
  - **Non-listed** AI innovators (e.g. 深度求索/DeepSeek、智谱、月之暗面/Kimi、MiniMax 等) **must not** appear in that financial comparison table, and the report **must not invent** revenue, profit, or other financial numbers for them.
  - Those entities **may** be covered **qualitatively** in sections such as **竞争格局**、**技术/开源生态**、**应用与商业模式**; always **cite the source** and **state uncertainty** where figures are not from audited public filings.

## Windows Task Scheduler (optional)

Create daily task (08:30):

```powershell
schtasks /Create /SC DAILY /TN "AI_Industry_Daily_Report" /TR "python d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/scripts/tracker.py --query AI产业 --mode daily --history-path d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/outputs/tracker_history.jsonl" /ST 08:30
```

Create weekly task (Monday 09:00):

```powershell
schtasks /Create /SC WEEKLY /D MON /TN "AI_Industry_Weekly_Report" /TR "python d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/scripts/tracker.py --query AI产业 --mode weekly --weekly-day 1 --history-path d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/outputs/tracker_history.jsonl" /ST 09:00
```
