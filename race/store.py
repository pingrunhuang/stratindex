"""Race tables: submissions (review-gated), runs, results. Never auto-promotes."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

import db as dbmod
from race import data as rdata
from race.engine import SpecError, backtest, validate_spec

SCHEMA = """
CREATE TABLE IF NOT EXISTS race_strategies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  author TEXT,
  description TEXT,
  style TEXT NOT NULL DEFAULT 'Trend',
  spec_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  is_seed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS race_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_at TEXT NOT NULL,
  data_end_ts INTEGER,
  n INTEGER
);
CREATE TABLE IF NOT EXISTS race_results (
  run_id INTEGER NOT NULL REFERENCES race_runs(id) ON DELETE CASCADE,
  strategy_id INTEGER NOT NULL REFERENCES race_strategies(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  PRIMARY KEY (run_id, strategy_id)
);
"""

STYLES = ("Trend", "Mean rev", "Breakout", "Momentum")

SEEDS = [
    ("sma-20-50-cross", "SMA 20/50 Cross", "Trend",
     "Classic golden/death cross on 4h closes with a 2×ATR protective stop.",
     {"symbol": "BTC-USDT", "timeframe": "4h",
      "indicators": {"fast": {"type": "sma", "period": 20}, "slow": {"type": "sma", "period": 50}},
      "entry": {"all": [{"left": "fast", "op": "cross_above", "right": "slow"}]},
      "exit": {"any": [{"left": "fast", "op": "cross_below", "right": "slow"}]},
      "stop": {"type": "atr", "period": 14, "mult": 2}}),
    ("ema-21-50-trend", "EMA 21/50 Trend", "Trend",
     "Long while EMA21 is above EMA50 and price holds above EMA21; 8% hard stop.",
     {"symbol": "BTC-USDT", "timeframe": "4h",
      "indicators": {"fast": {"type": "ema", "period": 21}, "slow": {"type": "ema", "period": 50}},
      "entry": {"all": [{"left": "fast", "op": "cross_above", "right": "slow"}]},
      "exit": {"any": [{"left": "close", "op": "cross_below", "right": "slow"}]},
      "stop": {"type": "pct", "value": 8}}),
    ("rsi-14-mean-reversion", "RSI 14 Reversion", "Mean rev",
     "Buy RSI(14) crossing back above 30 inside an SMA200 uptrend; exit RSI > 60; 3×ATR stop.",
     {"symbol": "BTC-USDT", "timeframe": "4h",
      "indicators": {"rsi": {"type": "rsi", "period": 14}, "trend": {"type": "sma", "period": 200}},
      "entry": {"all": [{"left": "rsi", "op": "cross_above", "right": 30}, {"left": "close", "op": "gt", "right": "trend"}]},
      "exit": {"any": [{"left": "rsi", "op": "gt", "right": 60}]},
      "stop": {"type": "atr", "period": 14, "mult": 3}}),
    ("donchian-20-breakout", "Donchian 20 Breakout", "Breakout",
     "Turtle-style: buy a close above the prior 20-bar high, exit below the prior 10-bar low.",
     {"symbol": "BTC-USDT", "timeframe": "4h",
      "indicators": {"dc": {"type": "donchian", "period": 20}, "dcx": {"type": "donchian", "period": 10}},
      "entry": {"all": [{"left": "close", "op": "gt", "right": "dc.upper"}]},
      "exit": {"any": [{"left": "close", "op": "lt", "right": "dcx.lower"}]},
      "stop": {"type": "atr", "period": 20, "mult": 2.5}}),
    ("bollinger-20-reversion", "Bollinger 20/2 Reversion", "Mean rev",
     "Buy a close back above the lower band (20, 2σ); exit at the mid band; 5% stop.",
     {"symbol": "BTC-USDT", "timeframe": "4h",
      "indicators": {"bb": {"type": "bollinger", "period": 20, "k": 2}},
      "entry": {"all": [{"left": "close", "op": "cross_above", "right": "bb.lower"}]},
      "exit": {"any": [{"left": "close", "op": "gt", "right": "bb.mid"}]},
      "stop": {"type": "pct", "value": 5}}),
]


def conn() -> sqlite3.Connection:
    dbmod.init_db()
    c = dbmod.connect()
    c.executescript(SCHEMA)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(race_strategies)")}
    for col in ("email", "notified_at", "notify_error"):
        if col not in cols:
            c.execute(f"ALTER TABLE race_strategies ADD COLUMN {col} TEXT")
    return c


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "strategy"


def seed(c) -> int:
    added = 0
    for slug, name, style, desc, spec in SEEDS:
        validate_spec(spec)
        cur = c.execute(
            "INSERT OR IGNORE INTO race_strategies (slug,name,author,description,style,spec_json,status,is_seed,reviewed_at)"
            " VALUES (?,?,?,?,?,?,'approved',1,datetime('now'))",
            (slug, name, "StratIndex", desc, style, json.dumps(spec)))
        added += cur.rowcount
    c.commit()
    return added


EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


def submit(c, name, author, description, style, spec: dict, email: str = "") -> str:
    """Stage a user submission as PENDING. Raises SpecError on bad spec."""
    name = (name or "").strip()[:60]
    if len(name) < 3:
        raise SpecError("name must be at least 3 characters")
    email = (email or "").strip()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise SpecError("a valid email is required (we only use it to tell you the review result)")
    norm = validate_spec(spec)
    base = slugify(name)
    slug, i = base, 2
    while c.execute("SELECT 1 FROM race_strategies WHERE slug=?", (slug,)).fetchone():
        slug, i = f"{base}-{i}", i + 1
    c.execute(
        "INSERT INTO race_strategies (slug,name,author,description,style,spec_json,status,email) VALUES (?,?,?,?,?,?,'pending',?)",
        (slug, name, (author or "").strip()[:40] or "anonymous", (description or "").strip()[:400],
         style if style in STYLES else "Trend", json.dumps(norm), email))
    c.commit()
    return slug


def set_status(c, sid: int, status: str):
    c.execute("UPDATE race_strategies SET status=?, reviewed_at=datetime('now') WHERE id=?", (status, sid))
    c.commit()


def run_race(c, refresh=True) -> int:
    """Backtest every approved strategy on current cached data; store a new run."""
    rows = c.execute("SELECT * FROM race_strategies WHERE status='approved' ORDER BY id").fetchall()
    syms = {json.loads(r["spec_json"])["symbol"] for r in rows}
    if refresh:
        for s in syms:
            rdata.refresh(s)
    cache = {s: rdata.load(s) for s in syms}
    results = []
    for r in rows:
        spec = json.loads(r["spec_json"])
        res = backtest(spec, cache[spec["symbol"]])
        results.append((r["id"], res))
    results.sort(key=lambda x: (-x[1]["oos"]["sharpe"], -x[1]["oos"]["max_dd"]))  # dd is negative → shallower wins
    end_ts = max((x[1]["data_end_ts"] for x in results), default=None)
    cur = c.execute("INSERT INTO race_runs (run_at,data_end_ts,n) VALUES (?,?,?)",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"), end_ts, len(results)))
    run_id = cur.lastrowid
    for pos, (sid, res) in enumerate(results, 1):
        c.execute("INSERT INTO race_results VALUES (?,?,?,?)", (run_id, sid, pos, json.dumps(res)))
    c.commit()
    return run_id


def leaderboard(c):
    """Latest run with position changes vs the previous run."""
    runs = c.execute("SELECT * FROM race_runs ORDER BY id DESC LIMIT 2").fetchall()
    if not runs:
        return None, []
    prev = {}
    if len(runs) > 1:
        prev = {r["strategy_id"]: r["position"] for r in
                c.execute("SELECT strategy_id, position FROM race_results WHERE run_id=?", (runs[1]["id"],))}
    out = []
    for r in c.execute(
        "SELECT rr.position, rr.result_json, s.* FROM race_results rr JOIN race_strategies s ON s.id=rr.strategy_id"
        " WHERE rr.run_id=? AND s.status='approved' ORDER BY rr.position", (runs[0]["id"],)):
        d = dict(r)
        d["res"] = json.loads(d.pop("result_json"))
        p = prev.get(d["id"])
        d["delta"] = None if p is None else p - d["position"]
        out.append(d)
    if out:
        lead = out[0]["res"]["oos"]["sharpe"]
        best30 = max((x["res"]["ret_30d"] for x in out if x["res"]["ret_30d"] is not None), default=None)
        for x in out:
            x["gap"] = round(lead - x["res"]["oos"]["sharpe"], 3)
            x["fastest"] = best30 is not None and x["res"]["ret_30d"] == best30
    return dict(runs[0]), out


def record_notify(c, sid: int, sent: bool, status: str):
    if sent:
        c.execute("UPDATE race_strategies SET notified_at=datetime('now'), notify_error=NULL WHERE id=?", (sid,))
    else:
        c.execute("UPDATE race_strategies SET notify_error=? WHERE id=?", (status, sid))
    c.commit()
