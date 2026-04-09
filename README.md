# Industry Research Report Skill

An extensible Cursor skill for generating data-enhanced industry research reports with:

- real-time data collection (compute/model/market/news layers)
- automatic report generation (`md`, `json`, `docx`, `pdf`, `html`)
- daily/weekly tracking mode
- configurable watchlist for US + A/HK symbols
- auto theme selection and weighted multi-theme blending

## Features

- **Structured report generation**
  - extracts topic from free-form query
  - writes analyst-style Chinese report in Markdown
  - exports DOCX/PDF and shareable HTML
- **Real data snapshot**
  - compute layer: infra repo release/activity signals
  - model layer: framework/model ecosystem snapshots
  - market layer: US + A/HK quotes
  - news layer: topic and AI macro RSS streams
- **Tracking mode**
  - daily/weekly report generation
  - optional tracker history output (`jsonl`)
- **Theme-aware watchlist**
  - `--theme auto|default|compute|model|application`
  - weighted keyword dictionary for theme scoring
  - multi-theme merge with `--mix-top-k`

## Project Structure

```text
.cursor/skills/industry-research-report/
├─ SKILL.md
├─ requirements.txt
├─ watchlist.json
└─ scripts/
   ├─ get_data.py
   └─ tracker.py
```

## Requirements

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
```

## Usage

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

## watchlist.json Overview

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

## Outputs

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

## Notes

- Keep secrets out of logs and repository files.
- If quote/news endpoints are temporarily unavailable, script falls back gracefully and still returns report output.
