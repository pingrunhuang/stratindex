"""Public OHLCV fetch + SQLite cache (OKX public REST, no API key)."""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import db as dbmod

OKX_URL = "https://www.okx.com/api/v5/market/history-candles"
BAR_MAP = {"4h": "4H", "1h": "1H", "1d": "1Dutc"}
SYMBOLS = ("BTC-USDT", "ETH-USDT", "SOL-USDT")
HISTORY_START = "2022-01-01"


def cache_path() -> Path:
    return dbmod.DB_PATH.parent / "ohlcv.db"


def _conn() -> sqlite3.Connection:
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.execute(
        """CREATE TABLE IF NOT EXISTS ohlcv (
          symbol TEXT NOT NULL, tf TEXT NOT NULL, ts INTEGER NOT NULL,
          o REAL, h REAL, l REAL, c REAL, v REAL,
          PRIMARY KEY (symbol, tf, ts))"""
    )
    return c


def _get(params: str) -> list:
    req = urllib.request.Request(f"{OKX_URL}?{params}", headers={"User-Agent": "stratindex/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            if d.get("code") == "0":
                return d["data"]
            raise RuntimeError(d.get("msg"))
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    return []


def refresh(symbol: str, tf: str = "4h", start: str = HISTORY_START, verbose=False) -> int:
    """Fetch confirmed candles newer than cache (and backfill to start). Returns rows added."""
    bar = BAR_MAP[tf]
    start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    with _conn() as c:
        have_min, have_max = c.execute(
            "SELECT MIN(ts), MAX(ts) FROM ohlcv WHERE symbol=? AND tf=?", (symbol, tf)).fetchone()
        added = 0

        def walk(after, stop_at):
            nonlocal added
            while True:
                rows = _get(f"instId={symbol}&bar={bar}&limit=100" + (f"&after={after}" if after else ""))
                if not rows:
                    return
                batch = [(symbol, tf, int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
                         for r in rows if not (len(r) > 8 and r[8] != "1")]  # skip still-forming candle
                added += c.executemany("INSERT OR IGNORE INTO ohlcv VALUES (?,?,?,?,?,?,?,?)", batch).rowcount
                after = min(int(r[0]) for r in rows)
                if after <= stop_at:
                    return
                time.sleep(0.12)

        walk(None, have_max if have_max else start_ms)       # newest → cached max
        if not have_min or have_min > start_ms:               # backfill older history
            walk(have_min, start_ms)
        c.execute("DELETE FROM ohlcv WHERE symbol=? AND tf=? AND ts<?", (symbol, tf, start_ms))
        if verbose:
            print(f"{symbol} {tf}: +{added}")
        return added


def load(symbol: str, tf: str = "4h") -> dict:
    with _conn() as c:
        rows = c.execute(
            "SELECT ts,o,h,l,c,v FROM ohlcv WHERE symbol=? AND tf=? ORDER BY ts", (symbol, tf)
        ).fetchall()
    return {
        "ts": [r[0] for r in rows], "open": [r[1] for r in rows], "high": [r[2] for r in rows],
        "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows],
    }
