"""Template context helpers for the race UI."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from race.engine import FEE, SLIPPAGE

HKT = ZoneInfo("Asia/Hong_Kong")
COLORS = ["#b46bff", "#3ddc84", "#ff8a3d", "#5aabff", "#ff5c8a", "#ffd23f", "#2ee6d6", "#c0c0c0"]
FEE_NOTE = f"Unified: OKX spot 4h · fee {FEE*100:.1f}%/side · slippage {SLIPPAGE*100:.2f}%/fill · long-only · next-bar-open fills"


def hkt(ts_ms_or_iso):
    if isinstance(ts_ms_or_iso, (int, float)):
        dt = datetime.fromtimestamp(ts_ms_or_iso / 1000, timezone.utc)
    else:
        dt = datetime.fromisoformat(ts_ms_or_iso)
    return dt.astimezone(HKT).strftime("%b %-d, %Y %H:%M HKT")


def race_context(run, racers):
    ctx = {"race_run": run, "racers": racers, "race_colors": COLORS, "fee_note": FEE_NOTE,
           "race_run_label": hkt(run["run_at"]) if run else "", "race_best": {}, "race_json": "{}"}
    if not racers:
        return ctx
    ctx["race_best"] = {"sharpe": max(r["res"]["oos"]["sharpe"] for r in racers),
                        "dd": max(r["res"]["oos"]["max_dd"] for r in racers)}
    oos_ts = racers[0]["res"]["oos_start_ts"]
    ts = [t for t, _ in racers[0]["res"]["curve"] if t >= oos_ts]
    series = []
    for i, r in enumerate(racers[:6]):
        pts = [v for t, v in r["res"]["curve"] if t >= oos_ts]
        base = pts[0]
        series.append({"name": r["name"], "short": "".join(w[0] for w in r["name"].split()[:3]).upper(),
                       "pos": r["position"], "color": COLORS[i % len(COLORS)],
                       "pts": [round(v / base * 100, 2) for v in pts]})
    n = min(len(ts), *(len(s["pts"]) for s in series))
    for s in series:
        s["pts"] = s["pts"][:n]
    ctx["race_json"] = json.dumps({"ts": ts[:n], "series": series}).replace("</", "<\\/")
    return ctx
