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
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
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
DEFAULT_TEMPLATE_STYLE = "industry_deep_dive"
DEFAULT_PRESET = "custom"
DEFAULT_NARRATIVE_STRENGTH = "high"


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


def llm_text(client: OpenAI, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """
    Return text from LLM with compatibility fallback:
    1) OpenAI Responses API
    2) OpenAI-compatible Chat Completions API (e.g. GitHub Models)
    """
    try:
        rsp = client.responses.create(
            model=model,
            temperature=temperature,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (rsp.output_text or "").strip()
    except Exception:
        chat = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return ((chat.choices[0].message.content or "") if chat.choices else "").strip()


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


def normalize_template_style(style: str) -> str:
    v = (style or DEFAULT_TEMPLATE_STYLE).strip().lower()
    return v if v in {"industry_deep_dive", "company_initiation", "auto"} else DEFAULT_TEMPLATE_STYLE


def pick_template_style(style: str, query: str, topic: str) -> str:
    style = normalize_template_style(style)
    if style != "auto":
        return style
    text = f"{query} {topic}".lower()
    company_keywords = [
        "公司",
        "首次覆盖",
        "覆盖",
        "估值",
        "财报",
        "盈利预测",
        "管理层",
        "股权",
        "竞争优势",
        "护城河",
        "roe",
        "pe",
        "pb",
        "dcf",
        "initiation",
    ]
    for kw in company_keywords:
        if kw in text:
            return "company_initiation"
    return "industry_deep_dive"


def resolve_section_toggles(
    preset: str, include_pest: bool, include_five_forces: bool, include_segmentation: bool
) -> Tuple[bool, bool, bool]:
    p = (preset or DEFAULT_PRESET).strip().lower()
    if p == "quick":
        return False, False, False
    if p == "full":
        return True, True, True
    return include_pest, include_five_forces, include_segmentation


def normalize_narrative_strength(value: str) -> str:
    v = (value or DEFAULT_NARRATIVE_STRENGTH).strip().lower()
    return v if v in {"high", "medium"} else DEFAULT_NARRATIVE_STRENGTH


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
    topic = llm_text(client, model, prompt, raw_query, temperature=0.1)
    if not topic:
        topic = raw_query.strip()
    return topic[:MAX_TOPIC_LEN]


def generate_report_markdown(
    client: OpenAI,
    topic: str,
    model: str,
    data_snapshot: Dict,
    mode: str = "general",
    template_style: str = DEFAULT_TEMPLATE_STYLE,
    include_pest: bool = True,
    include_five_forces: bool = True,
    include_segmentation: bool = True,
    narrative_strength: str = DEFAULT_NARRATIVE_STRENGTH,
) -> Tuple[str, str]:
    mode = normalize_mode(mode)
    template_style = normalize_template_style(template_style)
    today = dt.date.today().isoformat()
    pest_section = "## 宏观环境分析（PEST）\n" if include_pest else ""
    five_forces_section = "## 行业竞争态势（波特五力）\n" if include_five_forces else ""
    segmentation_section = "## 细分市场分析（可选）\n" if include_segmentation else ""
    toggle_hint = (
        f"可选模块开关：PEST={'on' if include_pest else 'off'}，"
        f"五力={'on' if include_five_forces else 'off'}，"
        f"细分市场={'on' if include_segmentation else 'off'}。"
    )
    narrative_strength = normalize_narrative_strength(narrative_strength)
    narrative_hint = (
        "写作强度：medium（短平快版，结论优先、段落更短、论证简洁）"
        if narrative_strength == "medium"
        else "写作强度：high（深论证版，证据链更完整、因果展开更充分）"
    )
    narrative_rules = (
        "表达与论证要求（medium，短平快）：\n"
        "A. 每个一级章节至少1段完整论述；每段建议40-90字，先结论后要点证据。\n"
        "B. 核心判断采用“事实 -> 结论”两步表达，因果链可简写但不得缺失关键逻辑。\n"
        "C. 执行摘要输出“结论、证据、建议”三联结构。\n"
        "D. 结论与建议部分至少给出2条可执行动作，并标注优先级（高/中/低）。\n"
        "E. 周报模式下，优先写“本周变化点、原因、下周观察指标”，减少背景铺垫。\n"
    )
    if narrative_strength == "high":
        narrative_rules = (
            "表达与论证增强要求（high，深论证，必须严格执行）：\n"
            "A. 每个一级章节至少包含2段完整论述；每段建议80-150字，避免口号式短句。\n"
            "B. 每个核心判断都采用“事实 -> 机制 -> 影响”三步表达。\n"
            "C. 对关键结论补充反方视角或约束条件，再给最终判断，避免单边叙事。\n"
            "D. 执行摘要必须输出“结论、证据、含义、建议”四联结构。\n"
            "E. 结论与建议部分至少给出3条可执行动作，并标注优先级（高/中/低）。\n"
            "F. 周报模式下，突出“本周变化点、原因、下周观察指标”；避免泛化行业科普。\n"
            "G. 公司覆盖模式下，突出“财务质量、估值框架、催化与风险对称”。\n"
        )
    if template_style == "company_initiation":
        system_prompt = (
            "你是一名资深卖方分析师。请使用中文输出公司首次覆盖风格研究报告。"
            "输出必须是 markdown，包含：\n"
            "# 标题\n"
            "## 报告引言（目的、研究范围、核心结论摘要）\n"
            "## 执行摘要（覆盖观点、评级倾向、核心催化）\n"
            "## 数据快照（算力层->模型层->市场层）\n"
            f"{pest_section}"
            "## 公司概况与治理结构（前身、产品矩阵、历史沿革、股权结构、核心团队、激励机制）\n"
            "## 商业模式与盈利模式拆解\n"
            "## 行业空间与量价框架（量=需求，价=成本/ASP）\n"
            "## 行业发展现状（规模、增长驱动、市场结构、区域分布）\n"
            f"{segmentation_section}"
            "## 竞争格局与可比公司（同行/历史/国际）\n"
            f"{five_forces_section}"
            "## 核心竞争优势与护城河（技术、客户、成本、研发）\n"
            "## 财务质量分析（成长、盈利、现金流、周转）\n"
            "## 未来3年预测（收入、毛利、费用率、利润）\n"
            "## 估值框架与敏感性分析\n"
            "## 标杆企业分析（2-3家，可选）\n"
            "## 风险与不确定性\n"
            "## 数据来源与口径说明\n"
            "## 结论与建议\n"
            "要求：逻辑清晰，强调公司基本面，先事实后判断。"
            "对建议部分需分别给出：企业建议、投资者建议。"
            "禁止只给一句话结论，必须给出论证过程与证据链。"
        )
    else:
        system_prompt = (
            "你是一名资深行业分析师。请使用中文输出专业、结构化行业研究报告。"
            "输出必须是 markdown，包含：\n"
            "# 标题\n"
            "## 报告引言（目的、行业定义与范围、核心结论摘要）\n"
            "## 执行摘要\n"
            "## 数据快照（算力层->模型层->市场层）\n"
            f"{pest_section}"
            "## 公司概况与治理结构（前身、产品矩阵、历史沿革、股权结构、核心团队、战略变更、财务概览）\n"
            "## 行业定义与边界\n"
            "## 行业分析：量价框架（量=下游需求/渗透率，价=成本/ASP/溢价）\n"
            "## 市场规模与增速（给出区间/假设）\n"
            "## 产业链与关键环节（上中下游）\n"
            "## 行业发展现状（增长驱动、市场结构、区域分布）\n"
            f"{segmentation_section}"
            "## 竞争格局（5力/CRn/商业模式）\n"
            f"{five_forces_section}"
            "## 竞争优势与护城河验证（产品、技术、研发、客户、成本）\n"
            "## 核心驱动因素与边际变化\n"
            "## 三维比较（同行比较、历史比较、国际比较）\n"
            "## 风险与不确定性\n"
            "## 未来3年情景推演（乐观/基准/悲观）与敏感性分析\n"
            "## 市场规模预测（3-5年，含依据）\n"
            "## 盈利预测与关键假设（收入、毛利、费用率、现金流）\n"
            "## 标杆企业分析（2-3家，可选）\n"
            "## 数据来源与口径说明\n"
            "## 结论与建议\n"
            "要求：逻辑清晰、可用于面试与业务沟通，避免空话。每一节先陈述事实数据，再给判断。"
            "禁止只给一句话结论，必须给出论证过程与证据链。"
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
        f"模板风格：{template_style}\n"
        f"{toggle_hint}\n"
        f"{narrative_hint}\n"
        f"报告日期：{today}\n"
        "你必须优先使用我给你的实时数据快照进行事实陈述，"
        "并在正文中明确区分“事实数据”和“基于数据的判断”。\n\n"
        "写作规则：\n"
        "1) 若是行业报告，仍需给出至少1-2个代表性公司的小节分析作为落地样本。\n"
        "2) 行业分析必须围绕“量价”展开，并给出可验证先导指标。\n"
        "3) 预测部分必须明确关键假设、变量方向和主要风险触发条件。\n"
        "4) 禁止使用未经验证的自媒体二手数据作为核心论据。\n"
        "5) 必须体现章节之间的因果链：环境 -> 现状 -> 竞争 -> 趋势/预测 -> 建议。\n"
        "6) 尽量提供表格化摘要（如CRn、CAGR、三情景假设）。\n\n"
        f"{narrative_rules}\n"
        f"实时数据快照如下：\n{data_json}\n"
    )
    text = llm_text(client, model, system_prompt, user_prompt, temperature=0.35)
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

    # Global document typography: Chinese Songti + English Times New Roman.
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Times New Roman"
    normal_style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal_style.font.size = Pt(12)  # 小四
    normal_style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    normal_style.paragraph_format.first_line_indent = Pt(24)  # 首行缩进2字符
    normal_style.paragraph_format.space_before = Pt(0)
    normal_style.paragraph_format.space_after = Pt(0)

    title_para = doc.add_heading(title, level=1)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_para.paragraph_format.first_line_indent = Pt(0)
    title_para.paragraph_format.space_before = Pt(12)
    title_para.paragraph_format.space_after = Pt(12)
    for run in title_para.runs:
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(16)  # 三号
        run.bold = True
        run.font.color.rgb = RGBColor(0, 0, 0)

    def clean_inline_md(text: str) -> str:
        text = text.replace("**", "").replace("__", "").replace("`", "")
        return text.strip()

    def is_md_table_line(text: str) -> bool:
        t = text.strip()
        return t.startswith("|") and "|" in t[1:]

    def split_md_row(text: str) -> List[str]:
        t = text.strip().strip("|")
        return [c.strip() for c in t.split("|")]

    lines = markdown_text.splitlines()
    i = 0
    while i < len(lines):
        striped = lines[i].strip()

        if is_md_table_line(striped):
            table_lines: List[str] = []
            while i < len(lines) and is_md_table_line(lines[i].strip()):
                table_lines.append(lines[i].strip())
                i += 1
            if table_lines:
                header = split_md_row(table_lines[0])
                body_lines = table_lines[1:]
                sep_pattern = re.compile(r"^\|\s*[-:| ]+\|?\s*$")
                body_lines = [ln for ln in body_lines if not sep_pattern.match(ln)]
                table = doc.add_table(rows=1, cols=max(1, len(header)))
                table.style = "Table Grid"
                for c_idx, val in enumerate(header):
                    p = table.rows[0].cells[c_idx].paragraphs[0]
                    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                    run = p.add_run(clean_inline_md(val))
                    run.font.name = "Times New Roman"
                    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                    run.font.size = Pt(12)
                    run.bold = True
                    run.font.color.rgb = RGBColor(0, 0, 0)
                for row in body_lines:
                    vals = split_md_row(row)
                    r = table.add_row()
                    for c_idx in range(len(header)):
                        cell_val = vals[c_idx] if c_idx < len(vals) else ""
                        p = r.cells[c_idx].paragraphs[0]
                        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                        run = p.add_run(clean_inline_md(cell_val))
                        run.font.name = "Times New Roman"
                        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                        run.font.size = Pt(12)
                        run.font.color.rgb = RGBColor(0, 0, 0)
            continue

        i += 1
        if not striped:
            para = doc.add_paragraph("")
            para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            para.paragraph_format.first_line_indent = Pt(24)
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.space_after = Pt(0)
            continue
        if striped in {"---", "***", "___"}:
            continue
        if striped.startswith("### "):
            para = doc.add_heading(clean_inline_md(striped[4:]), level=3)
            para.paragraph_format.first_line_indent = Pt(0)
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.space_after = Pt(6)
            para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            para.paragraph_format.keep_with_next = True
            for run in para.runs:
                run.font.name = "Times New Roman"
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                run.font.size = Pt(14)  # 四号
                run.bold = True
                run.font.color.rgb = RGBColor(0, 0, 0)
        elif striped.startswith("## "):
            para = doc.add_heading(clean_inline_md(striped[3:]), level=2)
            para.paragraph_format.first_line_indent = Pt(0)
            para.paragraph_format.space_before = Pt(10)
            para.paragraph_format.space_after = Pt(8)
            para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            para.paragraph_format.keep_with_next = True
            for run in para.runs:
                run.font.name = "Times New Roman"
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                run.font.size = Pt(15)  # 小三
                run.bold = True
                run.font.color.rgb = RGBColor(0, 0, 0)
        elif striped.startswith("# "):
            continue
        else:
            para = doc.add_paragraph(clean_inline_md(striped))
            para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            para.paragraph_format.first_line_indent = Pt(24)
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.widow_control = True
            for run in para.runs:
                run.font.name = "Times New Roman"
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                run.font.size = Pt(12)  # 小四
                run.font.color.rgb = RGBColor(0, 0, 0)
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
    parser.add_argument(
        "--template-style",
        required=False,
        default=DEFAULT_TEMPLATE_STYLE,
        choices=["industry_deep_dive", "company_initiation", "auto"],
        help="Report template style",
    )
    parser.add_argument("--include-pest", dest="include_pest", action="store_true", default=True, help="Include PEST section")
    parser.add_argument("--no-include-pest", dest="include_pest", action="store_false", help="Disable PEST section")
    parser.add_argument("--include-five-forces", dest="include_five_forces", action="store_true", default=True, help="Include Five Forces section")
    parser.add_argument("--no-include-five-forces", dest="include_five_forces", action="store_false", help="Disable Five Forces section")
    parser.add_argument("--include-segmentation", dest="include_segmentation", action="store_true", default=True, help="Include segmentation section")
    parser.add_argument("--no-include-segmentation", dest="include_segmentation", action="store_false", help="Disable segmentation section")
    parser.add_argument(
        "--preset",
        required=False,
        default=DEFAULT_PRESET,
        choices=["custom", "quick", "full"],
        help="Section preset: quick=short version, full=all sections, custom=manual toggles",
    )
    parser.add_argument(
        "--narrative-strength",
        required=False,
        default=DEFAULT_NARRATIVE_STRENGTH,
        choices=["high", "medium"],
        help="Narrative depth: medium=short concise, high=deep argumentative",
    )
    args = parser.parse_args()

    query = (args.query or "").strip()
    mode = normalize_mode(args.mode)
    requested_template_style = normalize_template_style(args.template_style)
    narrative_strength = normalize_narrative_strength(args.narrative_strength)
    include_pest, include_five_forces, include_segmentation = resolve_section_toggles(
        args.preset, args.include_pest, args.include_five_forces, args.include_segmentation
    )
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
        resolved_template_style = pick_template_style(requested_template_style, query, topic)
        force_theme = "" if (args.theme or "auto") == "auto" else (args.theme or "").strip().lower()
        selected_theme, watchlist, mix_info = pick_watchlist_by_topic(
            watchlist_config,
            text=f"{query} {topic}",
            force_theme=force_theme,
            top_k=max(1, args.mix_top_k),
        )
        data_snapshot = fetch_real_data(topic, watchlist=watchlist, mode=mode)
        data_snapshot["theme_mix"] = mix_info
        title, md_text = generate_report_markdown(
            client,
            topic,
            model,
            data_snapshot,
            mode=mode,
            template_style=resolved_template_style,
            include_pest=include_pest,
            include_five_forces=include_five_forces,
            include_segmentation=include_segmentation,
            narrative_strength=narrative_strength,
        )

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
            "preset": args.preset,
            "narrative_strength": narrative_strength,
            "template_style": resolved_template_style,
            "template_style_requested": requested_template_style,
            "include_pest": include_pest,
            "include_five_forces": include_five_forces,
            "include_segmentation": include_segmentation,
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
