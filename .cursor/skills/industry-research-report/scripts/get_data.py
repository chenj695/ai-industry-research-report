#!/usr/bin/env python3
import argparse
import datetime as dt
import csv
import subprocess
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import quote

from docx import Document
import httpx
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


MAX_TOPIC_LEN = 500
DEFAULT_MODEL = "gpt-4o-mini"
HTTP_TIMEOUT = 20.0
DEFAULT_TOPIC = "AI产业"
DEFAULT_WATCHLIST_FILE = "watchlist.json"


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("_")
    return cleaned[:120] or "industry_report"


def ensure_output_dirs(base_dir: Path) -> Path:
    out_dir = base_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def build_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def get_http_client() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": "industry-research-skill/1.1"})


def safe_get_json(client: httpx.Client, url: str) -> Dict:
    try:
        rsp = client.get(url)
        rsp.raise_for_status()
        return rsp.json()
    except Exception:
        return {}


def safe_get_text(client: httpx.Client, url: str) -> str:
    try:
        rsp = client.get(url)
        rsp.raise_for_status()
        return rsp.text
    except Exception:
        return ""


def normalize_mode(mode: str) -> str:
    v = (mode or "general").strip().lower()
    return v if v in {"general", "daily", "weekly"} else "general"


def load_watchlist(base_dir: Path, watchlist_path: str = "") -> Dict:
    default_payload = {
        "theme_keyword_map": {
            "compute": {"算力": 1.0, "gpu": 2.0, "服务器": 1.0, "idc": 1.5, "光模块": 1.8, "数据中心": 1.3, "芯片": 1.2},
            "model": {"模型": 1.0, "大模型": 1.5, "llm": 1.8, "多模态": 1.4, "agent": 1.2, "推理": 1.5, "训练": 1.2},
            "application": {"应用": 1.0, "aigc": 1.5, "saas": 1.3, "智能体": 1.4, "办公": 0.8, "营销": 0.8},
        },
        "themes": {
            "default": {
                "us_symbols_stooq": ["nvda.us", "amd.us", "tsm.us", "smci.us", "msft.us", "goog.us", "amzn.us", "meta.us"],
                "cn_hk_symbols_yahoo": {
                    "688256.SS": "寒武纪",
                    "300308.SZ": "中际旭创",
                    "601138.SS": "工业富联",
                    "0700.HK": "腾讯控股",
                    "9988.HK": "阿里巴巴-SW",
                },
            },
            "compute": {
                "us_symbols_stooq": ["nvda.us", "amd.us", "tsm.us", "smci.us", "avgo.us", "mrvl.us", "eqix.us", "dlr.us"],
                "cn_hk_symbols_yahoo": {
                    "688256.SS": "寒武纪",
                    "300308.SZ": "中际旭创",
                    "601138.SS": "工业富联",
                    "002281.SZ": "光迅科技",
                    "603083.SS": "剑桥科技",
                    "0700.HK": "腾讯控股",
                },
            },
            "model": {
                "us_symbols_stooq": ["msft.us", "goog.us", "amzn.us", "meta.us", "orcl.us", "crm.us", "adbe.us", "snow.us"],
                "cn_hk_symbols_yahoo": {
                    "0700.HK": "腾讯控股",
                    "9988.HK": "阿里巴巴-SW",
                    "9888.HK": "百度集团-SW",
                    "0241.HK": "阿里健康",
                    "600941.SS": "中国移动",
                },
            },
            "application": {
                "us_symbols_stooq": ["msft.us", "goog.us", "meta.us", "adbe.us", "crm.us", "shop.us", "now.us", "intu.us"],
                "cn_hk_symbols_yahoo": {
                    "0700.HK": "腾讯控股",
                    "9988.HK": "阿里巴巴-SW",
                    "3690.HK": "美团-W",
                    "9626.HK": "哔哩哔哩-W",
                    "002230.SZ": "科大讯飞",
                },
            },
        },
    }
    candidate = Path(watchlist_path) if watchlist_path else base_dir / DEFAULT_WATCHLIST_FILE
    try:
        if not candidate.exists():
            return default_payload
        data = json.loads(candidate.read_text(encoding="utf-8"))
        themes = data.get("themes", {})
        keyword_map = data.get("theme_keyword_map", {})
        if not isinstance(themes, dict) or not isinstance(keyword_map, dict):
            return default_payload
        if "default" not in themes:
            return default_payload
        return data
    except Exception:
        return default_payload


def _normalize_theme_bucket(bucket: Dict) -> Dict:
    us = bucket.get("us_symbols_stooq", []) if isinstance(bucket, dict) else []
    cn_hk = bucket.get("cn_hk_symbols_yahoo", {}) if isinstance(bucket, dict) else {}
    us_symbols = [str(x).strip().lower() for x in us if str(x).strip()]
    cn_hk_map = {str(k).strip(): str(v).strip() for k, v in cn_hk.items() if str(k).strip()}
    return {"us_symbols_stooq": us_symbols, "cn_hk_symbols_yahoo": cn_hk_map}


def _merge_buckets_weighted(
    themes: Dict[str, Dict], weighted_themes: List[Tuple[str, float]], default_bucket: Dict
) -> Dict:
    if not weighted_themes:
        return default_bucket
    us_weight: Dict[str, float] = {}
    cn_hk_weight: Dict[str, Tuple[str, float]] = {}
    for theme, weight in weighted_themes:
        bucket = _normalize_theme_bucket(themes.get(theme, {}))
        for sym in bucket.get("us_symbols_stooq", []):
            us_weight[sym] = us_weight.get(sym, 0.0) + weight
        for sym, name in bucket.get("cn_hk_symbols_yahoo", {}).items():
            prev = cn_hk_weight.get(sym)
            if prev:
                cn_hk_weight[sym] = (prev[0], prev[1] + weight)
            else:
                cn_hk_weight[sym] = (name, weight)

    us_sorted = [k for k, _ in sorted(us_weight.items(), key=lambda x: x[1], reverse=True)]
    cn_hk_sorted = {
        k: v[0]
        for k, v in sorted(cn_hk_weight.items(), key=lambda x: x[1][1], reverse=True)
    }
    return {"us_symbols_stooq": us_sorted, "cn_hk_symbols_yahoo": cn_hk_sorted}


def _normalize_keyword_weights(keywords: object) -> Dict[str, float]:
    # Backward compatible: supports list[str] (weight=1.0) and dict[str, number].
    result: Dict[str, float] = {}
    if isinstance(keywords, list):
        for kw in keywords:
            k = str(kw).strip().lower()
            if k:
                result[k] = 1.0
        return result
    if isinstance(keywords, dict):
        for k_raw, w_raw in keywords.items():
            k = str(k_raw).strip().lower()
            if not k:
                continue
            try:
                w = float(w_raw)
            except Exception:
                w = 1.0
            if w <= 0:
                continue
            result[k] = w
    return result


def pick_watchlist_by_topic(
    watchlist_config: Dict, text: str, force_theme: str = "", top_k: int = 2
) -> Tuple[str, Dict, Dict]:
    themes = watchlist_config.get("themes", {})
    theme_keyword_map = watchlist_config.get("theme_keyword_map", {})
    default_bucket = _normalize_theme_bucket(themes.get("default", {}))
    if force_theme and force_theme in themes:
        wl = _normalize_theme_bucket(themes.get(force_theme, {}))
        return force_theme, wl, {"selected_themes": [force_theme], "theme_scores": {force_theme: 1.0}}

    target = (text or "").lower()
    scores: Dict[str, float] = {}
    match_details: Dict[str, Dict[str, float]] = {}
    for theme, keywords in theme_keyword_map.items():
        if theme not in themes:
            continue
        score = 0.0
        hit_map: Dict[str, float] = {}
        keyword_weights = _normalize_keyword_weights(keywords)
        for kw, weight in keyword_weights.items():
            if kw in target:
                score += weight
                hit_map[kw] = weight
        scores[theme] = score
        if hit_map:
            match_details[theme] = hit_map

    ranked = [(theme, score) for theme, score in scores.items() if score > 0]
    ranked.sort(key=lambda x: x[1], reverse=True)
    if not ranked:
        return "default", default_bucket, {"selected_themes": ["default"], "theme_scores": {"default": 1.0}}

    picked = ranked[: max(1, top_k)]
    total = float(sum(x[1] for x in picked))
    weighted = [(theme, score / total) for theme, score in picked]
    merged = _merge_buckets_weighted(themes, weighted, default_bucket)
    selected = [x[0] for x in weighted]
    selected_theme = "+".join(selected)
    return selected_theme, merged, {
        "selected_themes": selected,
        "theme_scores": {theme: round(weight, 4) for theme, weight in weighted},
        "raw_weighted_hits": {theme: round(score, 4) for theme, score in picked},
        "matched_keywords": {theme: match_details.get(theme, {}) for theme in selected},
    }


def fetch_github_releases(client: httpx.Client, repo: str, limit: int = 2) -> List[Dict]:
    url = f"https://api.github.com/repos/{repo}/releases?per_page={limit}"
    data = safe_get_json(client, url)
    if not isinstance(data, list):
        return []
    out = []
    for item in data[:limit]:
        out.append(
            {
                "repo": repo,
                "tag": item.get("tag_name", ""),
                "name": item.get("name", ""),
                "published_at": item.get("published_at", ""),
                "url": item.get("html_url", ""),
            }
        )
    return out


def fetch_github_issue_velocity(client: httpx.Client, repo: str) -> Dict:
    open_url = f"https://api.github.com/search/issues?q=repo:{repo}+type:issue+state:open"
    closed_30d_url = (
        "https://api.github.com/search/issues?"
        f"q=repo:{repo}+type:issue+state:closed+closed:>={dt.date.today() - dt.timedelta(days=30)}"
    )
    open_data = safe_get_json(client, open_url)
    closed_data = safe_get_json(client, closed_30d_url)
    return {
        "repo": repo,
        "open_issues": int(open_data.get("total_count", 0)) if isinstance(open_data, dict) else 0,
        "closed_30d": int(closed_data.get("total_count", 0)) if isinstance(closed_data, dict) else 0,
    }


def fetch_hf_top_models(client: httpx.Client, limit: int = 8) -> List[Dict]:
    url = f"https://huggingface.co/api/models?sort=downloads&direction=-1&limit={limit}"
    data = safe_get_json(client, url)
    if not isinstance(data, list):
        return []
    out = []
    for item in data[:limit]:
        out.append(
            {
                "id": item.get("id", ""),
                "downloads": item.get("downloads", 0),
                "likes": item.get("likes", 0),
                "pipeline_tag": item.get("pipeline_tag", ""),
                "last_modified": item.get("lastModified", ""),
            }
        )
    return out


def fetch_google_news_rss(client: httpx.Client, query: str, limit: int = 6) -> List[Dict]:
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    text = safe_get_text(client, url)
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except Exception:
        return []
    items = []
    for item in root.findall(".//item")[:limit]:
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "pub_date": (item.findtext("pubDate") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "source": (item.findtext("source") or "").strip(),
            }
        )
    return items


def fetch_stooq_quotes(client: httpx.Client, symbols: List[str]) -> List[Dict]:
    if not symbols:
        return []
    q = ",".join(symbols)
    url = f"https://stooq.com/q/l/?s={q}&f=sd2t2c8ohlv&e=csv"
    text = safe_get_text(client, url)
    if not text:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return []
    reader = csv.DictReader(lines)
    out = []
    for row in reader:
        try:
            change_pct = float(row.get("% Change", "0") or 0)
        except ValueError:
            change_pct = 0.0
        out.append(
            {
                "symbol": row.get("Symbol", ""),
                "date": row.get("Date", ""),
                "time": row.get("Time", ""),
                "close": row.get("Close", ""),
                "open": row.get("Open", ""),
                "high": row.get("High", ""),
                "low": row.get("Low", ""),
                "volume": row.get("Volume", ""),
                "change_pct": change_pct,
            }
        )
    return out


def fetch_yahoo_quotes(client: httpx.Client, symbol_name_map: Dict[str, str]) -> List[Dict]:
    symbols = list(symbol_name_map.keys())
    if not symbols:
        return []
    url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" + quote(",".join(symbols))
    data = safe_get_json(client, url)
    result = data.get("quoteResponse", {}).get("result", []) if isinstance(data, dict) else []
    out = []
    for item in result:
        symbol = item.get("symbol", "")
        out.append(
            {
                "symbol": symbol,
                "name": symbol_name_map.get(symbol, symbol),
                "currency": item.get("currency", ""),
                "exchange": item.get("fullExchangeName", ""),
                "price": item.get("regularMarketPrice", ""),
                "change": item.get("regularMarketChange", ""),
                "change_pct": item.get("regularMarketChangePercent", 0),
                "market_time": item.get("regularMarketTime", 0),
            }
        )
    return out


def fetch_real_data(topic: str, watchlist: Dict, mode: str = "general") -> Dict:
    with get_http_client() as client:
        compute_repos = [
            "pytorch/pytorch",
            "triton-lang/triton",
            "vllm-project/vllm",
            "NVIDIA/TensorRT",
            "openxla/xla",
        ]
        model_repos = [
            "huggingface/transformers",
            "ollama/ollama",
            "ggml-org/llama.cpp",
            "openai/openai-python",
        ]

        compute_updates: List[Dict] = []
        compute_velocity: List[Dict] = []
        for repo in compute_repos:
            compute_updates.extend(fetch_github_releases(client, repo, limit=1))
            compute_velocity.append(fetch_github_issue_velocity(client, repo))

        model_updates: List[Dict] = []
        for repo in model_repos:
            model_updates.extend(fetch_github_releases(client, repo, limit=1))

        market_symbols = watchlist.get("us_symbols_stooq", [])
        market_quotes = fetch_stooq_quotes(client, market_symbols)
        market_sorted = sorted(
            market_quotes,
            key=lambda x: abs(float(x.get("change_pct", 0.0))),
            reverse=True,
        )

        cn_hk_symbol_map = watchlist.get("cn_hk_symbols_yahoo", {})
        cn_hk_quotes = fetch_yahoo_quotes(client, cn_hk_symbol_map)
        cn_hk_sorted = sorted(
            cn_hk_quotes,
            key=lambda x: abs(float(x.get("change_pct", 0) or 0)),
            reverse=True,
        )

        return {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "topic": topic,
            "mode": mode,
            "watchlist": watchlist,
            "compute_layer": {
                "release_updates": compute_updates,
                "issue_velocity_30d": compute_velocity,
            },
            "model_layer": {
                "release_updates": model_updates,
                "huggingface_top_models": fetch_hf_top_models(client, limit=8),
            },
            "market_layer": {
                "us_quotes": market_quotes,
                "cn_hk_quotes": cn_hk_quotes,
                "largest_daily_moves": market_sorted[:5],
                "cn_hk_largest_daily_moves": cn_hk_sorted[:5],
            },
            "news_layer": {
                "ai_general_news": fetch_google_news_rss(client, "人工智能 算力 模型", limit=6),
                "topic_news": fetch_google_news_rss(client, topic, limit=6),
            },
        }


def extract_topic_with_llm(client: OpenAI, raw_query: str, model: str) -> str:
    prompt = (
        "你是行业关键词提取助手。"
        "请从用户输入中提取最核心的行业/产业主题，"
        "仅返回主题词，不要解释，不要加引号。"
        "如果有多个主题，请保留最核心或并列主题短语。"
    )
    rsp = client.responses.create(
        model=model,
        temperature=0.1,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": raw_query},
        ],
    )
    topic = (rsp.output_text or "").strip()
    if not topic:
        topic = raw_query.strip()
    return topic[:MAX_TOPIC_LEN]


def generate_report_markdown(
    client: OpenAI, topic: str, model: str, data_snapshot: Dict, mode: str = "general"
) -> Tuple[str, str]:
    mode = normalize_mode(mode)
    today = dt.date.today().isoformat()
    system_prompt = (
        "你是一名资深行业分析师。请使用中文输出专业、结构化行业研究报告。"
        "输出必须是 markdown，包含：\n"
        "# 标题\n"
        "## 执行摘要\n"
        "## 数据快照（算力层->模型层->市场层）\n"
        "## 行业定义与边界\n"
        "## 市场规模与增速（给出区间/假设）\n"
        "## 产业链与关键环节\n"
        "## 竞争格局（5力/CRn/商业模式）\n"
        "## 核心驱动因素\n"
        "## 风险与不确定性\n"
        "## 未来3年情景推演（乐观/基准/悲观）\n"
        "## 结论与建议\n"
        "要求：逻辑清晰、可用于面试与业务沟通，避免空话。"
    )
    mode_hint = "常规深度报告"
    if mode == "daily":
        mode_hint = "日报：重点写过去24小时更新、市场异动和次日观察点。"
    elif mode == "weekly":
        mode_hint = "周报：重点写过去7天变化、周度复盘和下周前瞻。"
    data_json = json.dumps(data_snapshot, ensure_ascii=False)
    user_prompt = (
        f"请围绕“{topic}”生成完整行业研究报告。\n"
        f"报告模式：{mode_hint}\n"
        f"报告日期：{today}\n"
        "你必须优先使用我给你的实时数据快照进行事实陈述，"
        "并在正文中明确区分“事实数据”和“基于数据的判断”。\n\n"
        f"实时数据快照如下：\n{data_json}\n"
    )
    rsp = client.responses.create(
        model=model,
        temperature=0.35,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    text = (rsp.output_text or "").strip()
    if not text:
        text = f"# {topic}行业研究报告\n\n## 执行摘要\n暂无内容。"
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"{topic}行业研究报告"
    if mode == "daily" and "日报" not in title:
        title = f"{today} {topic}产业日报"
    if mode == "weekly" and "周报" not in title:
        iso_week = dt.date.today().isocalendar().week
        title = f"{dt.date.today().year}W{iso_week:02d} {topic}产业周报"
    return title, text


def write_markdown(md_path: Path, content: str) -> None:
    md_path.write_text(content, encoding="utf-8")


def write_json(json_path: Path, payload: Dict) -> None:
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_docx(docx_path: Path, title: str, markdown_text: str) -> None:
    doc = Document()
    doc.add_heading(title, level=1)
    for line in markdown_text.splitlines():
        striped = line.strip()
        if not striped:
            doc.add_paragraph("")
            continue
        if striped.startswith("### "):
            doc.add_heading(striped[4:], level=3)
        elif striped.startswith("## "):
            doc.add_heading(striped[3:], level=2)
        elif striped.startswith("# "):
            continue
        else:
            doc.add_paragraph(striped)
    doc.save(str(docx_path))


def write_pdf(pdf_path: Path, title: str, markdown_text: str) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    x = 40
    y = height - 40
    line_height = 16
    c.setFont("STSong-Light", 14)
    c.drawString(x, y, title)
    y -= 24
    c.setFont("STSong-Light", 11)

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip().replace("#", "").strip()
        if not line:
            y -= line_height
        else:
            parts = [line[i : i + 45] for i in range(0, len(line), 45)]
            for p in parts:
                if y < 40:
                    c.showPage()
                    c.setFont("STSong-Light", 11)
                    y = height - 40
                c.drawString(x, y, p)
                y -= line_height
        if y < 40:
            c.showPage()
            c.setFont("STSong-Light", 11)
            y = height - 40
    c.save()


def build_html_share(share_path: Path, title: str, markdown_text: str) -> None:
    body = markdown_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; margin: 32px; line-height: 1.75; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <pre>{body}</pre>
</body>
</html>
"""
    share_path.write_text(html, encoding="utf-8")


def make_truncated_text(markdown_text: str, limit: int = 600) -> str:
    plain = re.sub(r"^#{1,6}\s*", "", markdown_text, flags=re.MULTILINE).strip()
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    if len(plain) <= limit:
        return plain
    return plain[:limit].rstrip() + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate industry research report.")
    parser.add_argument("--query", required=False, default=DEFAULT_TOPIC, help="Free-form user query or topic")
    parser.add_argument(
        "--mode",
        required=False,
        default="general",
        choices=["general", "daily", "weekly"],
        help="Report mode",
    )
    parser.add_argument(
        "--open-share",
        action="store_true",
        help="Open generated share html in default browser",
    )
    parser.add_argument(
        "--watchlist",
        required=False,
        default="",
        help="Optional custom watchlist JSON path",
    )
    parser.add_argument(
        "--theme",
        required=False,
        default="auto",
        help="Theme for watchlist: auto/default/compute/model/application",
    )
    parser.add_argument(
        "--mix-top-k",
        required=False,
        type=int,
        default=2,
        help="When theme=auto, mix top-k themes by keyword hit weights",
    )
    args = parser.parse_args()

    query = (args.query or "").strip()
    mode = normalize_mode(args.mode)
    if not query:
        query = DEFAULT_TOPIC
    if len(query) > MAX_TOPIC_LEN:
        print("ERROR_TOPIC_TOO_LONG", file=sys.stderr)
        return 2

    try:
        base_dir = Path(__file__).resolve().parents[1]
        out_dir = ensure_output_dirs(base_dir)
        watchlist_config = load_watchlist(base_dir, args.watchlist)
        client = build_client()
        model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        topic = extract_topic_with_llm(client, query, model)
        force_theme = "" if (args.theme or "auto") == "auto" else (args.theme or "").strip().lower()
        selected_theme, watchlist, mix_info = pick_watchlist_by_topic(
            watchlist_config,
            text=f"{query} {topic}",
            force_theme=force_theme,
            top_k=max(1, args.mix_top_k),
        )
        data_snapshot = fetch_real_data(topic, watchlist=watchlist, mode=mode)
        data_snapshot["theme_mix"] = mix_info
        title, md_text = generate_report_markdown(client, topic, model, data_snapshot, mode=mode)

        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = sanitize_filename(title)
        stem = f"{ts}_{safe}"

        md_path = out_dir / f"{stem}.md"
        docx_path = out_dir / f"{stem}.docx"
        pdf_path = out_dir / f"{stem}.pdf"
        json_path = out_dir / f"{stem}.json"
        data_path = out_dir / f"{stem}_data.json"
        html_path = out_dir / f"{stem}.html"

        write_markdown(md_path, md_text)
        write_docx(docx_path, title, md_text)
        write_pdf(pdf_path, title, md_text)
        build_html_share(html_path, title, md_text)
        write_json(data_path, data_snapshot)

        payload = {
            "title": title,
            "topic": topic,
            "mode": mode,
            "selected_theme": selected_theme,
            "theme_mix": mix_info,
            "watchlist_path": (Path(args.watchlist).as_posix() if args.watchlist else (base_dir / DEFAULT_WATCHLIST_FILE).as_posix()),
            "truncated_text": make_truncated_text(md_text),
            "pdf_output_path": pdf_path.as_posix(),
            "docx_output_path": docx_path.as_posix(),
            "md_output_path": md_path.as_posix(),
            "json_output_path": json_path.as_posix(),
            "data_output_path": data_path.as_posix(),
            "share_url": html_path.resolve().as_uri(),
            "data_snapshot": data_snapshot,
        }
        write_json(json_path, payload)
        if args.open_share:
            try:
                subprocess.run(["cmd", "/c", "start", "", str(html_path.resolve())], check=False)
            except Exception:
                pass
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception:
        print("报告生成服务暂时不可用，请稍后重试。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
