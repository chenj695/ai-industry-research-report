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

## Error handling

- `ERROR_TOPIC_TOO_LONG`: `字数超出限制，请尝试其它主体。`
- other failures: `报告生成服务暂时不可用，请稍后重试。`

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

## Windows Task Scheduler (optional)

Create daily task (08:30):

```powershell
schtasks /Create /SC DAILY /TN "AI_Industry_Daily_Report" /TR "python d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/scripts/tracker.py --query AI产业 --mode daily --history-path d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/outputs/tracker_history.jsonl" /ST 08:30
```

Create weekly task (Monday 09:00):

```powershell
schtasks /Create /SC WEEKLY /D MON /TN "AI_Industry_Weekly_Report" /TR "python d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/scripts/tracker.py --query AI产业 --mode weekly --weekly-day 1 --history-path d:/rag-system/industry_resarch_report/.cursor/skills/industry-research-report/outputs/tracker_history.jsonl" /ST 09:00
```
