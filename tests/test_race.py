"""Smoke tests for the race feature. Run: python -m pytest tests/ or python tests/test_race.py"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_tmp = tempfile.mkdtemp()
os.environ["STRATINDEX_DB_PATH"] = str(Path(_tmp) / "t.db")

from race import engine  # noqa: E402
from race.engine import SpecError, backtest, validate_spec  # noqa: E402


def synthetic(n=2000):
    ts0, close = 1_640_995_200_000, []
    for i in range(n):
        close.append(100 * (1 + 0.3 * math.sin(i / 60)) * (1 + i / 4000))
    return {"ts": [ts0 + i * 4 * 3600_000 for i in range(n)], "open": [close[0]] + close[:-1],
            "high": [c * 1.01 for c in close], "low": [c * 0.99 for c in close], "close": close, "volume": [1] * n}


SPEC = {"symbol": "BTC-USDT", "timeframe": "4h",
        "indicators": {"f": {"type": "sma", "period": 10}, "s": {"type": "sma", "period": 30}},
        "entry": {"all": [{"left": "f", "op": "cross_above", "right": "s"}]},
        "exit": {"any": [{"left": "f", "op": "cross_below", "right": "s"}]},
        "stop": {"type": "pct", "value": 5}}


def test_indicators():
    assert engine.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert engine.rsi([float(i) for i in range(30)], 14)[-1] == 100.0
    dc = engine.donchian([1, 2, 3, 4, 5], [0, 1, 2, 3, 4], 2)
    assert dc["upper"][4] == 4  # previous bars only


def test_validation_rejects_bad():
    for bad in [{}, {**SPEC, "side": "short"}, {**SPEC, "symbol": "DOGE-USDT"},
                {**SPEC, "entry": {"all": [{"left": "__import__", "op": "gt", "right": 1}]}},
                {**SPEC, "indicators": {"x": {"type": "eval", "period": 3}}}]:
        try:
            validate_spec(bad)
        except SpecError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_backtest_runs_and_costs_apply():
    d = synthetic()
    r = backtest(SPEC, d)
    assert r["full"]["trades"] > 3 and r["oos"]["trades"] >= 0
    assert -100 < r["full"]["max_dd"] <= 0
    # zero-cost run must beat the costed run
    old = engine.FEE, engine.SLIPPAGE
    engine.FEE = engine.SLIPPAGE = 0
    try:
        r0 = backtest(SPEC, d)
    finally:
        engine.FEE, engine.SLIPPAGE = old
    assert r0["full"]["total_return"] > r["full"]["total_return"]


def test_seeds_valid():
    from race.store import SEEDS
    for s in SEEDS:
        validate_spec(s[4])


def test_submit_is_pending_and_routes():
    import app as appmod
    from race import store
    c = appmod.app.test_client()
    r = c.post("/submit", data={"name": "My test strat", "author": "t", "email": "t@example.com", "style": "Trend", "spec_json": json.dumps(SPEC)})
    assert r.status_code == 200 and b"pending review" in r.data
    with store.conn() as rc:
        row = rc.execute("SELECT status FROM race_strategies WHERE name='My test strat'").fetchone()
    assert row["status"] == "pending"
    assert c.post("/submit", data={"name": "bad", "spec_json": "{"}).status_code == 400
    assert c.get("/").status_code == 200
    assert c.get("/admin/race").status_code == 302  # admin-gated
    assert c.post("/admin/race/1/approve").status_code == 302
    with store.conn() as rc:
        assert rc.execute("SELECT status FROM race_strategies WHERE id=1").fetchone()["status"] == "pending"


def test_submit_requires_email():
    import app as appmod
    c = appmod.app.test_client()
    r = c.post("/submit", data={"name": "No email strat", "spec_json": json.dumps(SPEC), "email": "nope"})
    assert r.status_code == 400 and b"valid email" in r.data


def _admin_client():
    import app as appmod
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["admin_ok"] = True
    return c


def _pending(name, email="racer@example.com"):
    from race import store
    with store.conn() as rc:
        slug = store.submit(rc, name, "racer", "", "Trend", SPEC, email=email)
        return rc.execute("SELECT id FROM race_strategies WHERE slug=?", (slug,)).fetchone()["id"], slug


def test_approve_and_reject_send_mocked_email():
    from unittest import mock
    from race import store
    os.environ.update(SMTP_HOST="smtp.test", SMTP_PORT="587", SMTP_USER="u", SMTP_PASSWORD="p",
                      SMTP_FROM="StratIndex <noreply@test>", SMTP_TLS="starttls",
                      STRATINDEX_PUBLIC_BASE_URL="https://stratindex.example")
    sid, slug = _pending("Mock mail strat")
    fake_run = mock.patch("race.store.run_race", return_value=99)
    fake_lb = mock.patch("race.store.leaderboard", return_value=({"id": 99}, [{"id": sid, "position": 2}, {"id": -1, "position": 1}]))
    with mock.patch("smtplib.SMTP") as smtp, fake_run, fake_lb:
        r = _admin_client().post(f"/admin/race/{sid}/approve")
        assert r.status_code == 302
        inst = smtp.return_value
        inst.starttls.assert_called_once()
        inst.login.assert_called_once_with("u", "p")
        msg = inst.send_message.call_args[0][0]
        assert msg["To"] == "racer@example.com"
        body = msg.get_content()
        assert "P2 of 2" in body and f"https://stratindex.example/race/{slug}" in body
    with store.conn() as rc:
        row = rc.execute("SELECT * FROM race_strategies WHERE id=?", (sid,)).fetchone()
    assert row["status"] == "approved" and row["notified_at"] and row["notify_error"] is None

    sid2, _ = _pending("Mock reject strat")
    with mock.patch("smtplib.SMTP") as smtp:
        _admin_client().post(f"/admin/race/{sid2}/reject")
        msg = smtp.return_value.send_message.call_args[0][0]
        assert "won't be adding it" in msg.get_content()

    # SMTP failure → approve still succeeds, error recorded
    sid3, _ = _pending("Mock fail strat")
    with mock.patch("smtplib.SMTP", side_effect=OSError("conn refused")), fake_run, fake_lb:
        r = _admin_client().post(f"/admin/race/{sid3}/approve", follow_redirects=True)
        assert r.status_code == 200 and b"conn refused" in r.data
    with store.conn() as rc:
        row = rc.execute("SELECT * FROM race_strategies WHERE id=?", (sid3,)).fetchone()
    assert row["status"] == "approved" and "conn refused" in row["notify_error"]


def test_unconfigured_smtp_skips():
    from unittest import mock
    for k in ("SMTP_HOST", "SMTP_FROM"):
        os.environ.pop(k, None)
    sid, _ = _pending("Mock skip strat")
    with mock.patch("smtplib.SMTP") as smtp:
        r = _admin_client().post(f"/admin/race/{sid}/reject", follow_redirects=True)
        smtp.assert_not_called()
    assert b"skipped: SMTP not configured" in r.data


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
