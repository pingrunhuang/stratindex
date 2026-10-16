"""SQLite schema + seed for StratIndex. Live rows + ingest staging."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from details import enrich

DETAIL_COLS = ("overview", "rules_json", "risks", "backtest_notes", "paper_prompt")


def resolve_db_path() -> Path:
    """SQLite file location.

    Priority:
      1. STRATINDEX_DB_PATH — full path to the .db file
      2. STRATINDEX_DATA_DIR or DATA_DIR — directory; file is <dir>/stratindex.db
      3. ./stratindex.db next to this module (local/dev default)
    """
    explicit = (os.environ.get("STRATINDEX_DB_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    data_dir = (
        os.environ.get("STRATINDEX_DATA_DIR")
        or os.environ.get("DATA_DIR")
        or ""
    ).strip()
    if data_dir:
        return (Path(data_dir).expanduser().resolve() / "stratindex.db")
    return Path(__file__).resolve().parent / "stratindex.db"


DB_PATH = resolve_db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  badge TEXT NOT NULL,
  title TEXT NOT NULL,
  thesis TEXT NOT NULL,
  sharpe REAL,
  max_dd REAL,
  ret_90d REAL,
  win_rate REAL,
  asset TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  style TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_url TEXT,
  is_new INTEGER NOT NULL DEFAULT 0,
  last_backtest_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  overview TEXT,
  rules_json TEXT,
  risks TEXT,
  backtest_notes TEXT,
  paper_prompt TEXT,
  like_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sponsors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  logo_text TEXT NOT NULL,
  name TEXT NOT NULL,
  tagline TEXT NOT NULL,
  url TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ingest_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_url TEXT NOT NULL,
  source_name TEXT NOT NULL,
  raw_excerpt TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected')),
  ai_model TEXT,
  slug TEXT,
  title TEXT,
  thesis TEXT,
  overview TEXT,
  rules_json TEXT,
  risks TEXT,
  backtest_notes TEXT,
  paper_prompt TEXT,
  asset TEXT,
  timeframe TEXT,
  style TEXT,
  badge TEXT,
  sharpe REAL,
  max_dd REAL,
  ret_90d REAL,
  win_rate REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at TEXT
);
"""

STRATEGIES = [
    {
        "slug": "funding-rate-mean-reversion-btc",
        "badge": "FR",
        "title": "Funding-rate mean reversion on BTC perps",
        "thesis": "Fade extreme 8h funding when OI is elevated; exit on normalize.",
        "sharpe": 1.42,
        "max_dd": -12.4,
        "ret_90d": 18.6,
        "win_rate": 57.0,
        "asset": "BTC",
        "timeframe": "8h",
        "style": "Carry",
        "source_name": "arXiv",
        "source_url": "https://arxiv.org",
        "is_new": 1,
        "last_backtest_at": "2026-10-15",
    },
    {
        "slug": "ema-ribbon-reclaim-eth",
        "badge": "TF",
        "title": "EMA ribbon reclaim with volume filter",
        "thesis": "Long on EMA21/50/200 reclaim when volume expands vs 20-bar median.",
        "sharpe": 1.18,
        "max_dd": -16.1,
        "ret_90d": 11.2,
        "win_rate": 49.0,
        "asset": "ETH",
        "timeframe": "1h",
        "style": "Trend",
        "source_name": "GitHub",
        "source_url": "https://github.com",
        "is_new": 1,
        "last_backtest_at": "2026-10-14",
    },
    {
        "slug": "basis-trade-spot-quarterly",
        "badge": "MR",
        "title": "Basis trade: spot vs quarterly futures",
        "thesis": "Capture contango when annualized basis exceeds costs + buffer.",
        "sharpe": 2.05,
        "max_dd": -4.8,
        "ret_90d": 6.3,
        "win_rate": 71.0,
        "asset": "BTC",
        "timeframe": "1d",
        "style": "Carry",
        "source_name": "Blog",
        "source_url": None,
        "is_new": 1,
        "last_backtest_at": "2026-10-16",
    },
    {
        "slug": "inventory-skew-mm-eth",
        "badge": "MM",
        "title": "Inventory-skew market making on ETH-USDT",
        "thesis": "Quote both sides with inventory skew; widen on vol spikes.",
        "sharpe": 1.67,
        "max_dd": -8.2,
        "ret_90d": 9.4,
        "win_rate": None,
        "asset": "ETH",
        "timeframe": "tick",
        "style": "MM",
        "source_name": "Forum",
        "source_url": None,
        "is_new": 0,
        "last_backtest_at": "2026-09-28",
    },
    {
        "slug": "perp-funding-harvest-hedge",
        "badge": "CR",
        "title": "Perp funding harvest with spot hedge",
        "thesis": "Collect positive funding while delta-neutral; rebalance daily.",
        "sharpe": 1.88,
        "max_dd": -5.5,
        "ret_90d": 5.1,
        "win_rate": 68.0,
        "asset": "BTC",
        "timeframe": "8h",
        "style": "Carry",
        "source_name": "GitHub",
        "source_url": "https://github.com",
        "is_new": 0,
        "last_backtest_at": "2026-10-01",
    },
    {
        "slug": "atr-breakout-trailing",
        "badge": "VL",
        "title": "ATR breakout with trailing stop",
        "thesis": "Enter 20-bar high + 1.5 ATR; trail at 2 ATR; skip low volume.",
        "sharpe": 1.09,
        "max_dd": -14.7,
        "ret_90d": 7.8,
        "win_rate": 41.0,
        "asset": "BTC",
        "timeframe": "4h",
        "style": "Trend",
        "source_name": "X",
        "source_url": "https://x.com",
        "is_new": 0,
        "last_backtest_at": "2026-07-03",
    },
    {
        "slug": "rsi2-mean-reversion-perps",
        "badge": "RS",
        "title": "RSI(2) mean reversion on liquid perps",
        "thesis": "Buy RSI(2) < 5 in uptrend; exit RSI(2) > 50 or 3-bar time stop.",
        "sharpe": 0.81,
        "max_dd": -19.3,
        "ret_90d": 4.2,
        "win_rate": 62.0,
        "asset": "Perps",
        "timeframe": "1h",
        "style": "Mean rev",
        "source_name": "Blog",
        "source_url": None,
        "is_new": 0,
        "last_backtest_at": "2026-06-20",
    },
    {
        "slug": "pairs-stat-arb-btc-eth",
        "badge": "SA",
        "title": "BTC–ETH residual mean reversion",
        "thesis": "Trade z-score of log-price residual; enter |z|>2, exit |z|<0.5.",
        "sharpe": 1.33,
        "max_dd": -11.0,
        "ret_90d": 8.9,
        "win_rate": 54.0,
        "asset": "BTC",
        "timeframe": "4h",
        "style": "Stat arb",
        "source_name": "arXiv",
        "source_url": "https://arxiv.org",
        "is_new": 1,
        "last_backtest_at": "2026-10-13",
    },
    {
        "slug": "vol-target-trend-eth",
        "badge": "VT",
        "title": "Vol-targeted trend on ETH",
        "thesis": "Scale trend signal to 10% annualized vol; cut when IV spikes.",
        "sharpe": 1.24,
        "max_dd": -13.2,
        "ret_90d": 10.1,
        "win_rate": 46.0,
        "asset": "ETH",
        "timeframe": "1d",
        "style": "Vol",
        "source_name": "Blog",
        "source_url": None,
        "is_new": 0,
        "last_backtest_at": "2026-08-12",
    },
    {
        "slug": "cross-exchange-funding-arb",
        "badge": "XA",
        "title": "Cross-exchange funding arb",
        "thesis": "Long low-funding venue, short high-funding; hedge basis risk.",
        "sharpe": 1.55,
        "max_dd": -6.7,
        "ret_90d": 4.8,
        "win_rate": 64.0,
        "asset": "Perps",
        "timeframe": "8h",
        "style": "Carry",
        "source_name": "GitHub",
        "source_url": "https://github.com",
        "is_new": 0,
        "last_backtest_at": "2026-09-05",
    },
    {
        "slug": "donchian-channel-breakout",
        "badge": "DC",
        "title": "Donchian channel breakout filter",
        "thesis": "Enter 55-bar high breakouts only when ADX > 25; trail mid-channel.",
        "sharpe": 0.96,
        "max_dd": -18.5,
        "ret_90d": 6.4,
        "win_rate": 38.0,
        "asset": "BTC",
        "timeframe": "4h",
        "style": "Trend",
        "source_name": "X",
        "source_url": "https://x.com",
        "is_new": 0,
        "last_backtest_at": "2026-05-18",
    },
    {
        "slug": "liquidations-cascade-fade",
        "badge": "LQ",
        "title": "Liquidation cascade fade",
        "thesis": "Fade forced liquidations after 2% cascade; tight stop above wick.",
        "sharpe": 1.11,
        "max_dd": -15.8,
        "ret_90d": 12.3,
        "win_rate": 53.0,
        "asset": "BTC",
        "timeframe": "1h",
        "style": "Mean rev",
        "source_name": "Forum",
        "source_url": None,
        "is_new": 1,
        "last_backtest_at": "2026-10-12",
    },
]

SPONSORS = [
    {"logo_text": "VC", "name": "Vibe Quant Lab", "tagline": "backtests that ship", "url": "#", "sort_order": 1},
    {"logo_text": "SI", "name": "Ship/It Weekly", "tagline": "quant newsletter", "url": "#", "sort_order": 2},
    {"logo_text": "OK", "name": "OKX Builders", "tagline": "API + perps", "url": "#", "sort_order": 3},
    {"logo_text": "BF", "name": "Backtest Forge", "tagline": "walk-forward kits", "url": "#", "sort_order": 4},
    {"logo_text": "NX", "name": "Nexus Data", "tagline": "funding & OI", "url": "#", "sort_order": 5},
    {"logo_text": "AQ", "name": "AlphaQueue", "tagline": "strategy alerts", "url": "#", "sort_order": 6},
]


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None, force_reseed: bool = False) -> Path:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(strategies)")}
        added = False
        for c in DETAIL_COLS:
            if c not in cols:
                conn.execute(f"ALTER TABLE strategies ADD COLUMN {c} TEXT")
                added = True
        if "like_count" not in cols:
            conn.execute(
                "ALTER TABLE strategies ADD COLUMN like_count INTEGER NOT NULL DEFAULT 0"
            )
            # refresh cols after alter
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(strategies)")}
        missing = conn.execute("SELECT COUNT(*) AS c FROM strategies WHERE overview IS NULL OR overview = ''").fetchone()["c"]
        if added or missing:
            force_reseed = True
        n = conn.execute("SELECT COUNT(*) AS c FROM strategies").fetchone()["c"]
        if force_reseed or n == 0:
            if force_reseed:
                conn.execute("DELETE FROM strategies")
                conn.execute("DELETE FROM sponsors")
            for s in STRATEGIES:
                s = {**s, **enrich(s)}
                conn.execute(
                    """
                    INSERT INTO strategies (
                      slug, badge, title, thesis, sharpe, max_dd, ret_90d, win_rate,
                      asset, timeframe, style, source_name, source_url, is_new, last_backtest_at,
                      overview, rules_json, risks, backtest_notes, paper_prompt
                    ) VALUES (
                      :slug, :badge, :title, :thesis, :sharpe, :max_dd, :ret_90d, :win_rate,
                      :asset, :timeframe, :style, :source_name, :source_url, :is_new, :last_backtest_at,
                      :overview, :rules_json, :risks, :backtest_notes, :paper_prompt
                    )
                    """,
                    s,
                )
            for sp in SPONSORS:
                conn.execute(
                    """
                    INSERT INTO sponsors (logo_text, name, tagline, url, sort_order, active)
                    VALUES (:logo_text, :name, :tagline, :url, :sort_order, 1)
                    """,
                    sp,
                )
            conn.commit()
    return path


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


if __name__ == "__main__":
    p = init_db(force_reseed=True)
    with connect(p) as c:
        sc = c.execute("SELECT COUNT(*) AS c FROM strategies").fetchone()["c"]
        sp = c.execute("SELECT COUNT(*) AS c FROM sponsors").fetchone()["c"]
    print(f"Seeded {p}: {sc} strategies, {sp} sponsors")
