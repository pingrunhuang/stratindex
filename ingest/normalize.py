"""Normalize raw source text into StratIndex strategy fields.

Uses optional OpenAI / Anthropic if keys are set; otherwise a deterministic
heuristic that still fills every required site field.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any


def _slugify(text: str, max_len: int = 72) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        s = "strategy"
    return s[:max_len].rstrip("-")


def _badge_from_title(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    if not words:
        return "AX"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def _guess_asset(text: str) -> str:
    t = text.lower()
    if re.search(r"\beth(ereum)?\b", t):
        return "ETH"
    if re.search(r"\bperp(etual)?s?\b|\bfutures?\b", t) and not re.search(r"\bbtc\b|\bbitcoin\b", t):
        return "Perps"
    if re.search(r"\bbtc\b|\bbitcoin\b|\bcrypto", t):
        return "BTC"
    return "BTC"


def _guess_style(text: str) -> str:
    t = text.lower()
    rules = [
        (r"market.?mak|liquidity provid|inventory", "MM"),
        (r"stat(istical)?\s*arb|pairs?\s*trad|cointegrat|spread", "Stat arb"),
        (r"mean.?reversion|revert|z-?score|rsi", "Mean rev"),
        (r"funding|basis|carry|contango|backwardation", "Carry"),
        (r"volatil|garch|iv\b|realized vol", "Vol"),
        (r"trend|momentum|breakout|follow", "Trend"),
    ]
    for pat, style in rules:
        if re.search(pat, t):
            return style
    return "Trend"


def _guess_timeframe(text: str) -> str:
    t = text.lower()
    for pat, tf in [
        (r"\btick\b|high.?frequency|hft", "tick"),
        (r"\b1h\b|hourly", "1h"),
        (r"\b4h\b|four.?hour", "4h"),
        (r"\b8h\b|funding", "8h"),
        (r"\b1d\b|daily|day.?ahead", "1d"),
    ]:
        if re.search(pat, t):
            return tf
    return "1d"


def _thesis_from_abstract(abstract: str, max_len: int = 160) -> str:
    # First sentence-ish, trimmed
    parts = re.split(r"(?<=[.!?])\s+", abstract.strip())
    first = parts[0] if parts else abstract
    first = first.strip()
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip() + "…"
    return first or "Quant strategy extracted from public research."


def _rules_from_text(title: str, abstract: str) -> list[str]:
    return [
        f"Research basis: {title[:120]}",
        "Treat published method as a paper signal — validate on your own data before size.",
        "Define entry / exit / risk from the paper’s core mechanism (see overview).",
        "Skip live capital until out-of-sample and cost assumptions are checked.",
    ]


def heuristic_normalize(title: str, abstract: str, source_url: str, source_name: str) -> dict[str, Any]:
    blob = f"{title}\n{abstract}"
    thesis = _thesis_from_abstract(abstract)
    asset = _guess_asset(blob)
    style = _guess_style(blob)
    timeframe = _guess_timeframe(blob)
    slug = _slugify(title)
    badge = _badge_from_title(title)
    overview = (
        f"This candidate was normalized heuristically from a public {source_name} source.\n\n"
        f"{abstract[:1200]}"
    )
    rules = _rules_from_text(title, abstract)
    risks = "\n".join(
        [
            "Heuristic extraction — fields may mis-tag asset/style; review before promote.",
            "Academic / blog results often omit fees, funding, and slippage.",
            "No live metrics yet (Sharpe / MaxDD / return left null until backtested).",
            "Not investment advice.",
        ]
    )
    backtest_notes = (
        "No backtest attached at ingest. Metrics are null until you run a local walk-forward.\n"
        f"Source: {source_url}"
    )
    paper_prompt = (
        f"You are reviewing a trading-strategy candidate from {source_name}.\n"
        f"Title: {title}\n"
        f"URL: {source_url}\n\n"
        f"Abstract:\n{abstract[:2000]}\n\n"
        "Summarize the tradable rules, required data, risks, and a minimal backtest plan."
    )
    return {
        "slug": slug,
        "title": title[:200],
        "thesis": thesis,
        "overview": overview,
        "rules_json": json.dumps(rules, ensure_ascii=False),
        "risks": risks,
        "backtest_notes": backtest_notes,
        "paper_prompt": paper_prompt,
        "asset": asset,
        "timeframe": timeframe,
        "style": style,
        "badge": badge,
        "sharpe": None,
        "max_dd": None,
        "ret_90d": None,
        "win_rate": None,
        "ai_model": "heuristic",
    }


def _llm_openai(title: str, abstract: str, source_url: str, source_name: str) -> dict[str, Any] | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    prompt = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract a trading-strategy card as JSON with keys: "
                    "slug, title, thesis, overview, rules (array of strings), risks (string), "
                    "backtest_notes, paper_prompt, asset (BTC|ETH|Perps), "
                    "timeframe (tick|1h|4h|8h|1d), style (Trend|Carry|Mean rev|MM|Stat arb|Vol), badge (2 chars)."
                ),
            },
            {
                "role": "user",
                "content": f"source={source_name}\nurl={source_url}\ntitle={title}\n\n{abstract[:4000]}",
            },
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(prompt).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "StratIndexIngest/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return _coerce_llm(parsed, title, abstract, source_url, source_name, "openai")
    except Exception:
        return None


def _llm_anthropic(title: str, abstract: str, source_url: str, source_name: str) -> dict[str, Any] | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        "max_tokens": 1200,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Return ONLY JSON with keys: slug, title, thesis, overview, rules (array), "
                    "risks, backtest_notes, paper_prompt, asset (BTC|ETH|Perps), "
                    "timeframe (tick|1h|4h|8h|1d), style (Trend|Carry|Mean rev|MM|Stat arb|Vol), badge.\n\n"
                    f"source={source_name}\nurl={source_url}\ntitle={title}\n\n{abstract[:4000]}"
                ),
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": "StratIndexIngest/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        content = data["content"][0]["text"]
        # strip fences if any
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        parsed = json.loads(content)
        return _coerce_llm(parsed, title, abstract, source_url, source_name, "anthropic")
    except Exception:
        return None


def _coerce_llm(
    parsed: dict,
    title: str,
    abstract: str,
    source_url: str,
    source_name: str,
    provider: str,
) -> dict[str, Any]:
    base = heuristic_normalize(title, abstract, source_url, source_name)
    rules = parsed.get("rules") or []
    if isinstance(rules, str):
        rules = [r for r in rules.split("\n") if r.strip()]
    base.update(
        {
            "slug": _slugify(str(parsed.get("slug") or parsed.get("title") or title)),
            "title": str(parsed.get("title") or title)[:200],
            "thesis": str(parsed.get("thesis") or base["thesis"])[:200],
            "overview": str(parsed.get("overview") or base["overview"]),
            "rules_json": json.dumps(list(rules) or json.loads(base["rules_json"]), ensure_ascii=False),
            "risks": str(parsed.get("risks") or base["risks"]),
            "backtest_notes": str(parsed.get("backtest_notes") or base["backtest_notes"]),
            "paper_prompt": str(parsed.get("paper_prompt") or base["paper_prompt"]),
            "asset": str(parsed.get("asset") or base["asset"]),
            "timeframe": str(parsed.get("timeframe") or base["timeframe"]),
            "style": str(parsed.get("style") or base["style"]),
            "badge": str(parsed.get("badge") or base["badge"])[:4].upper(),
            "ai_model": f"llm:{provider}",
        }
    )
    return base


def normalize(title: str, abstract: str, source_url: str, source_name: str) -> dict[str, Any]:
    for fn in (_llm_openai, _llm_anthropic):
        out = fn(title, abstract, source_url, source_name)
        if out:
            return out
    return heuristic_normalize(title, abstract, source_url, source_name)
