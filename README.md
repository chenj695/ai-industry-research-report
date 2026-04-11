# 📊 Industry Research Report Skill

An extensible Cursor skill for generating data-enhanced industry research reports with:

- real-time data collection (compute/model/market/news layers)
- automatic report generation (`md`, `json`, `docx`, `pdf`, `html`)
- daily/weekly tracking mode
- configurable watchlist for US + A/HK symbols
- auto theme selection and weighted multi-theme blending

## ✨ Features

- 🧱 **Structured report generation**
  - extracts topic from free-form query
  - writes analyst-style Chinese report in Markdown
  - follows a 4-part framework: company profile, industry quantity-price analysis, competitive edge, and forecast
  - supports two switchable styles: `industry_deep_dive` and `company_initiation`
  - exports DOCX/PDF and shareable HTML
- 🌐 **Real data snapshot**
  - compute layer: infra repo release/activity signals
  - model layer: framework/model ecosystem snapshots
  - market layer: US + A/HK quotes
  - news layer: topic and AI macro RSS streams
  - research layer: ArXiv latest papers
  - developer ecosystem layer: PyPI package trends
  - fundamental layer: SEC filings + company financial metrics
  - cloud compute layer: Azure GPU retail price indicators
  - capital layer: AI funding & M&A news pulse
- ⏱️ **Tracking mode**
  - daily/weekly report generation
  - optional tracker history output (`jsonl`)
- 🎯 **Theme-aware watchlist**
  - `--theme auto|default|compute|model|application`
  - weighted keyword dictionary for theme scoring
  - multi-theme merge with `--mix-top-k`

## 🗂️ Project Structure

```text
.cursor/skills/industry-research-report/
├─ SKILL.md
├─ requirements.txt
├─ watchlist.json
└─ scripts/
   ├─ get_data.py
   └─ tracker.py
```

## ✅ Requirements

- Python 3.9+
- OpenAI API key

Install dependencies:

```bash
pip install -r .cursor/skills/industry-research-report/requirements.txt
```

Set environment variable:

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

Optional:

```powershell
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o-mini"
$env:SEC_EDGAR_USER_AGENT="YourName your.email@example.com"
# If the model gateway returns 413 / request too large, lower the JSON embedded in the LLM prompt (full data still in *_data.json):
$env:REPORT_DATA_SNAPSHOT_MAX_CHARS="3000"
# Show real exception in stderr when generation fails:
$env:REPORT_DEBUG="1"
```

GitHub Models note: some endpoints cap **total request size** (e.g. `gpt-4.1` ~8000 input tokens). This repo sends a **slimmed** `data_snapshot` into the prompt; use `openai/gpt-4o-mini` or raise `REPORT_DATA_SNAPSHOT_MAX_CHARS` only if your provider allows a larger body.

## 🚀 Usage

### 1) Generate a general report

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业研究"
```

### 2) Daily / weekly mode

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode daily
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --mode weekly
```

### 3) Custom watchlist

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业" --watchlist ".cursor/skills/industry-research-report/watchlist.json"
```

### 4) Theme auto-switch + weighted mix

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "GPU推理与算力协同趋势" --theme auto --mix-top-k 2
```

### 5) Tracker entry

```bash
python .cursor/skills/industry-research-report/scripts/tracker.py --query "AI产业" --mode both --weekly-day 1
```

### 6) Template style switch

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究" --template-style industry_deep_dive
python .cursor/skills/industry-research-report/scripts/get_data.py --query "某AI公司首次覆盖" --template-style company_initiation
python .cursor/skills/industry-research-report/scripts/get_data.py --query "某AI公司估值与盈利预测" --template-style auto
```

### 7) Optional section toggles (report length control)

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究" --include-pest --include-five-forces --include-segmentation
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究（短版）" --no-include-pest --no-include-five-forces --no-include-segmentation
```

### 8) Quick presets

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究（短版）" --preset quick
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI行业研究（全量版）" --preset full
```

### 9) Narrative strength switch (short vs deep)

```bash
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业周报" --mode weekly --narrative-strength medium
python .cursor/skills/industry-research-report/scripts/get_data.py --query "AI产业深度研究" --narrative-strength high
```

## 🧾 Data Sources

Current data-source coverage includes:

- **GitHub API** (`api.github.com`)
  - releases and issue velocity for compute/model repos
- **Hugging Face API** (`huggingface.co/api/models`)
  - top model ecosystem snapshot
- **Stooq CSV feed** (`stooq.com`)
  - US equity quote monitoring
- **Yahoo Finance quote API** (`query1.finance.yahoo.com`)
  - A-share and Hong Kong quote monitoring
- **Google News RSS** (`news.google.com/rss`)
  - macro AI news, topic news, and funding/M&A pulse
- **ArXiv Atom API** (`export.arxiv.org/api`)
  - latest AI-related paper stream
- **PyPI + PyPIStats APIs** (`pypi.org`, `pypistats.org`)
  - package release metadata + recent download trends
- **SEC EDGAR APIs** (`sec.gov`, `data.sec.gov`)
  - recent filings (`10-K/10-Q/8-K/20-F/6-K`)
  - company financial facts (revenue/net income/gross profit/operating income/EPS/cash/R&D/capex)
  - **Important:** SEC endpoints expect a descriptive `User-Agent` (organization + contact). Set `SEC_EDGAR_USER_AGENT` to your email or org string; otherwise requests may fail silently and financial tables show `N/A`.
  - The generated **financial comparison table** uses **full company names** for selected US-listed peers (no bare tickers in the table).
- **Azure Retail Prices API** (`prices.azure.com`)
  - cloud GPU price indicators (e.g., H100/A100/L40/V100, by region/sku)

These sources are merged into `data_snapshot` and written to `*_data.json` for traceable evidence in generated reports.

## 🧠 `watchlist.json` Overview

Key fields:

- `theme_keyword_map`: weighted keyword dictionary per theme
- `themes.default|compute|model|application`: symbol pools per theme
- `us_symbols_stooq`: US symbols for stooq quote feed
- `cn_hk_symbols_yahoo`: A/HK symbols for Yahoo quote feed

Example weighted keywords:

```json
{
  "theme_keyword_map": {
    "compute": { "gpu": 2.0, "算力": 1.0, "光模块": 1.8 },
    "model": { "llm": 1.8, "推理": 1.5, "模型": 1.0 }
  }
}
```

## 📦 Outputs

Each run writes artifacts under:

```text
.cursor/skills/industry-research-report/outputs/
```

Typical outputs:

- `<timestamp>_<title>.md`
- `<timestamp>_<title>.json`
- `<timestamp>_<title>_data.json`
- `<timestamp>_<title>.docx`
- `<timestamp>_<title>.pdf`
- `<timestamp>_<title>.html`

## 📝 Report Writing Framework

The generated report now follows a practical research-writing structure for early-stage analysts:

- **Part 1: Company profile**
  - background, product matrix, evolution, ownership/governance, management team, strategy updates, financial snapshot
- **Part 2: Industry analysis (quantity-price framework)**
  - industry boundary, value chain, demand-side volume indicators, supply-side price/cost indicators, market sizing
- **Part 3: Competitive advantages**
  - competition landscape, moat validation by product/technology/R&D/customers/cost
- **Part 4: Forecast**
  - key assumptions, 3-scenario projection, profitability outlook, sensitivity and risk triggers

It also emphasizes:

- peer/history/global benchmarking
- explicit data-source and methodology disclosure

In addition, the template now borrows from a universal industry-report framework:

- intro with objective/scope/key findings
- macro environment via PEST
- current-state analysis (size, growth, structure, region)
- optional segmented market breakdown
- Porter Five Forces competition view
- 3-5 year outlook with opportunity/challenge and forecast basis
- optional benchmark-company section
- separate recommendations for enterprises and investors

## ⚠️ Notes

- Keep secrets out of logs and repository files.
- If quote/news endpoints are temporarily unavailable, script falls back gracefully and still returns report output.
