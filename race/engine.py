"""Rule-based strategy spec validation + unified long-only spot backtester (pure Python)."""
from __future__ import annotations

import math
import re

FEE = 0.001        # 0.1% per side
SLIPPAGE = 0.0005  # 0.05% per fill
OOS_DAYS = 182     # last ~6 months
BARS_PER_YEAR = {"4h": 6 * 365, "1h": 24 * 365, "1d": 365}

IND_TYPES = {
    "sma": {"period"}, "ema": {"period"}, "rsi": {"period"}, "atr": {"period"},
    "bollinger": {"period", "k"}, "donchian": {"period"},
}
MULTI_OUT = {"bollinger": ("upper", "mid", "lower"), "donchian": ("upper", "mid", "lower")}
PRICE_FIELDS = ("open", "high", "low", "close")
OPS = ("cross_above", "cross_below", "gt", "lt")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")


class SpecError(ValueError):
    pass


# ---------------------------------------------------------------- indicators
def sma(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x, n):
    out, a, prev = [None] * len(x), 2 / (n + 1), None
    for i, v in enumerate(x):
        if i == n - 1:
            prev = sum(x[:n]) / n
        elif i >= n:
            prev = a * v + (1 - a) * prev
        out[i] = prev if i >= n - 1 else None
    return out


def _wilder(x, n):
    out, prev = [None] * len(x), None
    for i in range(len(x)):
        if x[i] is None:
            continue
        if prev is None:
            window = [v for v in x[max(0, i - n + 1): i + 1] if v is not None]
            if len(window) == n:
                prev = sum(window) / n
                out[i] = prev
        else:
            prev = (prev * (n - 1) + x[i]) / n
            out[i] = prev
    return out


def rsi(close, n):
    gains = [None] + [max(close[i] - close[i - 1], 0) for i in range(1, len(close))]
    losses = [None] + [max(close[i - 1] - close[i], 0) for i in range(1, len(close))]
    ag, al = _wilder(gains, n), _wilder(losses, n)
    out = [None] * len(close)
    for i in range(len(close)):
        if ag[i] is not None and al[i] is not None:
            out[i] = 100.0 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])
    return out


def atr(h, l, c, n):
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    return _wilder(tr, n)


def bollinger(x, n, k):
    mid = sma(x, n)
    up, lo = [None] * len(x), [None] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1: i + 1]
        sd = math.sqrt(sum((v - mid[i]) ** 2 for v in w) / n)
        up[i], lo[i] = mid[i] + k * sd, mid[i] - k * sd
    return {"upper": up, "mid": mid, "lower": lo}


def donchian(h, l, n):
    """Channel of the PREVIOUS n bars (excludes current), so close > upper = breakout."""
    up, lo, mid = [None] * len(h), [None] * len(h), [None] * len(h)
    for i in range(n, len(h)):
        up[i], lo[i] = max(h[i - n: i]), min(l[i - n: i])
        mid[i] = (up[i] + lo[i]) / 2
    return {"upper": up, "mid": mid, "lower": lo}


# ---------------------------------------------------------------- spec
def _num(v, lo, hi, what):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise SpecError(f"{what} must be a number")
    if not (lo <= f <= hi):
        raise SpecError(f"{what} must be between {lo} and {hi}")
    return f


def validate_spec(spec: dict) -> dict:
    """Return a normalized spec or raise SpecError. JSON rules only — never code."""
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    from race.data import SYMBOLS
    out = {"symbol": spec.get("symbol", "BTC-USDT"), "timeframe": spec.get("timeframe", "4h"), "side": "long"}
    if out["symbol"] not in SYMBOLS:
        raise SpecError(f"symbol must be one of {', '.join(SYMBOLS)}")
    if out["timeframe"] != "4h":
        raise SpecError("timeframe must be 4h (MVP)")
    if spec.get("side", "long") != "long":
        raise SpecError("only long-only spot is supported for now")
    inds = spec.get("indicators") or {}
    if not isinstance(inds, dict) or not (1 <= len(inds) <= 6):
        raise SpecError("indicators: 1–6 named indicators required")
    names = set(PRICE_FIELDS)
    out["indicators"] = {}
    for name, d in inds.items():
        if not NAME_RE.match(str(name)) or name in PRICE_FIELDS:
            raise SpecError(f"bad indicator name '{name}' (lowercase a-z0-9_, not a price field)")
        if not isinstance(d, dict) or d.get("type") not in IND_TYPES:
            raise SpecError(f"indicator '{name}': type must be one of {', '.join(IND_TYPES)}")
        t = d["type"]
        nd = {"type": t, "period": int(_num(d.get("period"), 2, 400, f"{name}.period"))}
        if t == "bollinger":
            nd["k"] = _num(d.get("k", 2), 0.5, 5, f"{name}.k")
        if t in ("sma", "ema", "bollinger"):
            src = d.get("source", "close")
            if src not in PRICE_FIELDS:
                raise SpecError(f"{name}.source must be a price field")
            nd["source"] = src
        out["indicators"][name] = nd
        if t in MULTI_OUT:
            names.update(f"{name}.{o}" for o in MULTI_OUT[t])
        else:
            names.add(name)

    def conds(key, required):
        block = spec.get(key) or {}
        mode = "all" if "all" in block else "any" if "any" in block else None
        lst = block.get(mode) if mode else None
        if not lst:
            if required:
                raise SpecError(f"{key}: need {{\"all\": [...]}} or {{\"any\": [...]}} with ≥1 condition")
            return {"any": []}
        if len(lst) > 4:
            raise SpecError(f"{key}: max 4 conditions")
        norm = []
        for c in lst:
            if not isinstance(c, dict) or c.get("op") not in OPS:
                raise SpecError(f"{key}: op must be one of {', '.join(OPS)}")
            nc = {"op": c["op"]}
            for side in ("left", "right"):
                v = c.get(side)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nc[side] = float(v)
                elif isinstance(v, str) and v in names:
                    nc[side] = v
                else:
                    raise SpecError(f"{key}: '{v}' is not a number or a defined series ({', '.join(sorted(names))})")
            if isinstance(nc["left"], float) and isinstance(nc["right"], float):
                raise SpecError(f"{key}: a condition needs at least one series")
            norm.append(nc)
        return {mode: norm}

    out["entry"] = conds("entry", True)
    out["exit"] = conds("exit", False)
    stop = spec.get("stop")
    if stop:
        if stop.get("type") == "atr":
            out["stop"] = {"type": "atr", "period": int(_num(stop.get("period", 14), 2, 200, "stop.period")),
                           "mult": _num(stop.get("mult"), 0.5, 10, "stop.mult")}
        elif stop.get("type") == "pct":
            out["stop"] = {"type": "pct", "value": _num(stop.get("value"), 0.5, 50, "stop.value")}
        else:
            raise SpecError("stop.type must be 'atr' or 'pct'")
    if not out["exit"].get("any") and not out["exit"].get("all") and not out.get("stop"):
        raise SpecError("need an exit condition or a stop")
    return out


def compute_series(spec, data):
    s = {k: data[k] for k in PRICE_FIELDS}
    for name, d in spec["indicators"].items():
        t, n = d["type"], d["period"]
        if t == "sma":
            s[name] = sma(data[d["source"]], n)
        elif t == "ema":
            s[name] = ema(data[d["source"]], n)
        elif t == "rsi":
            s[name] = rsi(data["close"], n)
        elif t == "atr":
            s[name] = atr(data["high"], data["low"], data["close"], n)
        elif t == "bollinger":
            for k, v in bollinger(data[d["source"]], n, d["k"]).items():
                s[f"{name}.{k}"] = v
        elif t == "donchian":
            for k, v in donchian(data["high"], data["low"], n).items():
                s[f"{name}.{k}"] = v
    return s


def _val(s, x, i):
    return x if isinstance(x, float) else s[x][i]


def _cond(s, c, i):
    a, b = _val(s, c["left"], i), _val(s, c["right"], i)
    if a is None or b is None:
        return False
    if c["op"] == "gt":
        return a > b
    if c["op"] == "lt":
        return a < b
    if i == 0:
        return False
    pa, pb = _val(s, c["left"], i - 1), _val(s, c["right"], i - 1)
    if pa is None or pb is None:
        return False
    return (pa <= pb and a > b) if c["op"] == "cross_above" else (pa >= pb and a < b)


def _block(s, block, i):
    if "all" in block:
        return bool(block["all"]) and all(_cond(s, c, i) for c in block["all"])
    return any(_cond(s, c, i) for c in block.get("any", []))


# ---------------------------------------------------------------- backtest
def backtest(spec: dict, data: dict) -> dict:
    spec = validate_spec(spec)
    n = len(data["close"])
    if n < 300:
        raise SpecError("not enough data")
    s = compute_series(spec, data)
    stop = spec.get("stop")
    stop_atr = atr(data["high"], data["low"], data["close"], stop["period"]) if stop and stop["type"] == "atr" else None
    o, l, c, ts = data["open"], data["low"], data["close"], data["ts"]

    cash, qty = 1.0, 0.0
    pending, stop_px, sig_atr = None, None, None
    entry_px = entry_t = entry_eq = None
    equity, trades = [], []

    def close_pos(i, raw_px, reason):
        nonlocal cash, qty, stop_px
        px = raw_px * (1 - SLIPPAGE)
        cash = qty * px * (1 - FEE)
        trades.append({"entry_ts": entry_t, "exit_ts": ts[i], "entry_px": round(entry_px, 4),
                       "exit_px": round(px, 4), "ret_pct": round((cash / entry_eq - 1) * 100, 3), "reason": reason})
        qty, stop_px = 0.0, None

    for i in range(n):
        if pending == "buy" and qty == 0:
            entry_px = o[i] * (1 + SLIPPAGE)
            entry_eq, entry_t = cash, ts[i]
            qty, cash = cash * (1 - FEE) / entry_px, 0.0
            if stop:
                stop_px = entry_px * (1 - stop["value"] / 100) if stop["type"] == "pct" else entry_px - stop["mult"] * sig_atr
        elif pending == "sell" and qty > 0:
            close_pos(i, o[i], "exit")
        pending = None
        if qty > 0 and stop_px is not None and l[i] <= stop_px:
            close_pos(i, min(o[i], stop_px), "stop")
        equity.append(cash + qty * c[i])
        if i == n - 1:
            break
        if qty == 0 and _block(s, spec["entry"], i):
            if stop_atr is not None:
                if stop_atr[i] is None:
                    continue
                sig_atr = stop_atr[i]
            pending = "buy"
        elif qty > 0 and _block(s, spec["exit"], i):
            pending = "sell"

    open_trade = None
    if qty > 0:
        open_trade = {"entry_ts": entry_t, "entry_px": round(entry_px, 4),
                      "mark_ret_pct": round((equity[-1] / entry_eq - 1) * 100, 3)}

    bpy = BARS_PER_YEAR[spec["timeframe"]]
    full = metrics(equity, ts, trades, bpy)
    oos_start_ms = ts[-1] - OOS_DAYS * 86400_000
    k = next(i for i, t in enumerate(ts) if t >= oos_start_ms)
    oos = metrics(equity[k:], ts[k:], [t for t in trades if t["exit_ts"] >= ts[k]], bpy)
    m30 = next(i for i, t in enumerate(ts) if t >= ts[-1] - 30 * 86400_000)
    ret_30d = (equity[-1] / equity[m30 - 1] - 1) * 100 if m30 > 0 else None
    # daily-sampled curves (every 6 bars on 4h) for charts
    step = max(1, bpy // 365)
    curve = [[ts[i], round(equity[i], 5)] for i in range(0, n, step)]
    if curve[-1][0] != ts[-1]:
        curve.append([ts[-1], round(equity[-1], 5)])
    return {
        "spec": spec, "full": full, "oos": oos, "ret_30d": round(ret_30d, 3) if ret_30d is not None else None,
        "oos_start_ts": ts[k], "data_start_ts": ts[0], "data_end_ts": ts[-1], "bars": n,
        "curve": curve, "trades": trades[-50:], "trades_total": len(trades), "open_trade": open_trade,
        "fee": FEE, "slippage": SLIPPAGE,
    }


def metrics(eq, ts, trades, bpy):
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    mean = sum(rets) / len(rets) if rets else 0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    sharpe = mean / sd * math.sqrt(bpy) if sd > 0 else 0.0
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    years = (ts[-1] - ts[0]) / (365.25 * 86400_000)
    total = eq[-1] / eq[0] - 1
    cagr = (eq[-1] / eq[0]) ** (1 / years) - 1 if years > 0 and eq[-1] > 0 else None
    wins = sum(1 for t in trades if t["ret_pct"] > 0)
    return {
        "total_return": round(total * 100, 2), "cagr": round(cagr * 100, 2) if cagr is not None else None,
        "sharpe": round(sharpe, 3), "max_dd": round(mdd * 100, 2),
        "win_rate": round(wins / len(trades) * 100, 1) if trades else None, "trades": len(trades),
    }
