"""StratIndex — local Bloomberg-style strategy aggregator + ingest staging."""

from __future__ import annotations

import json
import threading
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import db as dbmod

BASE = Path(__file__).resolve().parent
HKT = ZoneInfo("Asia/Hong_Kong")
PORT = int(os.environ.get("PORT") or os.environ.get("STRATINDEX_PORT") or "5055")
SECRET_FILE = BASE / ".flask_secret_key"

app = Flask(__name__, template_folder=str(BASE / "templates"))


def _load_secret_key() -> str:
    env = (os.environ.get("STRATINDEX_SECRET_KEY") or "").strip()
    if env:
        return env
    if SECRET_FILE.exists():
        key = SECRET_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(32)
    SECRET_FILE.write_text(key + "\n", encoding="utf-8")
    try:
        SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return key


app.secret_key = _load_secret_key()


def get_conn() -> sqlite3.Connection:
    dbmod.init_db()
    return dbmod.connect()


def public_base_url() -> str:
    """Absolute site root for share links (no trailing slash)."""
    env = (os.environ.get("STRATINDEX_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    return (request.host_url or "http://127.0.0.1:5055/").rstrip("/")


def strategy_share_url(slug: str) -> str:
    return f"{public_base_url()}/s/{slug}"


def _filters_from_request():
    return {
        "asset": request.args.get("asset") or None,
        "timeframe": request.args.get("timeframe") or None,
        "style": request.args.get("style") or None,
        "sort": request.args.get("sort") or "newest",
        "limit": request.args.get("limit", type=int),
    }


def fetch_strategies(conn, *, asset=None, timeframe=None, style=None, sort="newest", limit=None):
    clauses = []
    params: list = []
    if asset and asset.lower() not in ("all", ""):
        clauses.append("asset = ?")
        params.append(asset)
    if timeframe and timeframe.lower() not in ("any", "all", ""):
        if timeframe in ("4h–1d", "4h-1d"):
            clauses.append("timeframe IN ('4h', '1d')")
        else:
            clauses.append("timeframe = ?")
            params.append(timeframe)
    if style and style.lower() not in ("all", ""):
        clauses.append("style = ?")
        params.append(style)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order = {
        "newest": "is_new DESC, last_backtest_at DESC, id DESC",
        "sharpe": "sharpe DESC NULLS LAST, id DESC",
        "return": "ret_90d DESC NULLS LAST, id DESC",
    }.get((sort or "newest").lower(), "is_new DESC, last_backtest_at DESC, id DESC")
    order = order.replace(" NULLS LAST", "")
    sql = f"SELECT * FROM strategies{where} ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_stats(conn):
    total = conn.execute("SELECT COUNT(*) AS c FROM strategies").fetchone()["c"]
    new_today = conn.execute("SELECT COUNT(*) AS c FROM strategies WHERE is_new = 1").fetchone()["c"]
    assets = {
        r["asset"]: r["c"]
        for r in conn.execute(
            "SELECT asset, COUNT(*) AS c FROM strategies GROUP BY asset ORDER BY c DESC"
        )
    }
    timeframes = {
        r["timeframe"]: r["c"]
        for r in conn.execute(
            "SELECT timeframe, COUNT(*) AS c FROM strategies GROUP BY timeframe ORDER BY c DESC"
        )
    }
    styles = {
        r["style"]: r["c"]
        for r in conn.execute(
            "SELECT style, COUNT(*) AS c FROM strategies GROUP BY style ORDER BY c DESC"
        )
    }
    sources = [
        r["source_name"]
        for r in conn.execute(
            "SELECT DISTINCT source_name FROM strategies ORDER BY source_name"
        )
    ]
    latest = conn.execute(
        "SELECT MAX(last_backtest_at) AS d FROM strategies"
    ).fetchone()["d"]
    return {
        "total": total,
        "new_today": new_today,
        "assets": assets,
        "timeframes": timeframes,
        "styles": styles,
        "sources": sources,
        "latest_backtest": latest,
    }


def fetch_sponsors(conn):
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM sponsors WHERE active = 1 ORDER BY sort_order, id"
        ).fetchall()
    ]


def format_backtest(d: str | None) -> str:
    if not d:
        return "—"
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d")
        return dt.strftime("%b %d")
    except ValueError:
        return d


def fmt_pct(v, signed=True):
    if v is None:
        return "—"
    if signed:
        return f"{v:+.1f}%"
    return f"{v:.0f}%"


def fmt_sharpe(v):
    if v is None:
        return "—"
    return f"{v:.2f}"


# --- Admin auth -----------------------------------------------------------------

_INGEST_LOCK = threading.Lock()


def admin_password_configured() -> bool:
    return bool((os.environ.get("STRATINDEX_ADMIN_PASSWORD") or "").strip())


def ingest_token_configured() -> bool:
    return bool((os.environ.get("STRATINDEX_INGEST_TOKEN") or "").strip())


def admin_logged_in() -> bool:
    return bool(session.get("admin_ok"))


def _token_from_request() -> str | None:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    hdr = (request.headers.get("X-StratIndex-Token") or "").strip()
    return hdr or None


def token_auth_ok() -> tuple[bool, str | None]:
    """Return (ok, error_message_if_token_attempt_failed).

    If no token header is present, returns (False, None) — caller may fall back to session.
    """
    got = _token_from_request()
    if got is None:
        return False, None
    expected = (os.environ.get("STRATINDEX_INGEST_TOKEN") or "").strip()
    if not expected:
        return False, "STRATINDEX_INGEST_TOKEN is not set on the server"
    if not secrets.compare_digest(got, expected):
        return False, "invalid token"
    return True, None


def admin_authorized() -> bool:
    """Session cookie (humans) or ingest Bearer / X-StratIndex-Token (bots)."""
    if admin_logged_in():
        return True
    ok, _ = token_auth_ok()
    return ok


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not admin_logged_in():
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def _protect_admin():
    path = request.path or ""
    if not path.startswith("/admin"):
        return None
    if path == "/admin/login" or path.startswith("/admin/login?"):
        return None
    if path == "/admin/logout":
        return None

    # Remote ingest trigger: JSON 401 (not HTML redirect) for Digester/curl
    if path == "/admin/run-ingest":
        if admin_authorized():
            return None
        tok_ok, tok_err = token_auth_ok()
        if tok_err:
            return jsonify({"ok": False, "error": tok_err}), 401
        if _token_from_request() is not None and not tok_ok:
            return jsonify({"ok": False, "error": "invalid token"}), 401
        return jsonify(
            {
                "ok": False,
                "error": "unauthorized — admin session or Bearer / X-StratIndex-Token required",
            }
        ), 401

    if admin_logged_in():
        return None
    # Token alone does not unlock HTML admin pages (ingest review UI)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        return redirect(url_for("admin_login", next="/admin/ingest"))
    nxt = path
    if request.query_string:
        nxt = f"{path}?{request.query_string.decode()}"
    return redirect(url_for("admin_login", next=nxt))


@app.get("/admin/login")
def admin_login():
    nxt = request.args.get("next") or "/admin/ingest"
    if admin_logged_in():
        return redirect(nxt if nxt.startswith("/admin") else "/admin/ingest")
    return render_template(
        "admin_login.html",
        next=nxt,
        password_configured=admin_password_configured(),
        error=None,
    )


@app.post("/admin/login")
def admin_login_post():
    nxt = request.form.get("next") or "/admin/ingest"
    if not nxt.startswith("/admin"):
        nxt = "/admin/ingest"
    expected = (os.environ.get("STRATINDEX_ADMIN_PASSWORD") or "").strip()
    if not expected:
        return render_template(
            "admin_login.html",
            next=nxt,
            password_configured=False,
            error="Set STRATINDEX_ADMIN_PASSWORD in the environment, then restart the server.",
        ), 403
    got = request.form.get("password") or ""
    if not secrets.compare_digest(got, expected):
        return render_template(
            "admin_login.html",
            next=nxt,
            password_configured=True,
            error="Wrong password.",
        ), 401
    session["admin_ok"] = True
    session.permanent = True
    return redirect(nxt)


@app.get("/admin/logout")
@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/")
def index():
    f = _filters_from_request()
    with get_conn() as conn:
        stats = fetch_stats(conn)
        strategies = fetch_strategies(conn, **{k: v for k, v in f.items() if k != "limit"})
        display = strategies
        sponsors = fetch_sponsors(conn)

    now = datetime.now(HKT)
    updated = now.strftime("%b %-d, %Y · %H:%M HKT")
    day_label = now.strftime("%a, %b %-d")
    view = (request.args.get("view") or "").lower()

    tf_any = stats["total"]
    tf_1h = stats["timeframes"].get("1h", 0)
    tf_4h1d = stats["timeframes"].get("4h", 0) + stats["timeframes"].get("1d", 0)

    return render_template(
        "index.html",
        strategies=display,
        all_count=len(strategies),
        stats=stats,
        sponsors=sponsors,
        updated=updated,
        day_label=day_label,
        filters=f,
        view=view,
        tf_any=tf_any,
        tf_1h=tf_1h,
        tf_4h1d=tf_4h1d,
        format_backtest=format_backtest,
        fmt_pct=fmt_pct,
        fmt_sharpe=fmt_sharpe,
        public_base=public_base_url(),
    )


@app.get("/api/strategies")
def api_strategies():
    f = _filters_from_request()
    with get_conn() as conn:
        rows = fetch_strategies(conn, **f)
    return jsonify({"strategies": rows, "count": len(rows)})


@app.get("/api/stats")
def api_stats():
    with get_conn() as conn:
        stats = fetch_stats(conn)
    now = datetime.now(HKT)
    stats["updated"] = now.strftime("%b %-d, %Y · %H:%M HKT")
    return jsonify(stats)


@app.get("/api/sponsors")
def api_sponsors():
    with get_conn() as conn:
        sponsors = fetch_sponsors(conn)
    return jsonify({"sponsors": sponsors})


def fetch_one(conn, slug):
    r = conn.execute("SELECT * FROM strategies WHERE slug = ?", (slug,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    try:
        d["rules"] = json.loads(d.get("rules_json") or "[]")
    except ValueError:
        d["rules"] = []
    d["risks_list"] = [x for x in (d.get("risks") or "").split("\n") if x.strip()]
    d["overview_paras"] = [x for x in (d.get("overview") or "").split("\n\n") if x.strip()]
    d["backtest_lines"] = [x for x in (d.get("backtest_notes") or "").split("\n") if x.strip()]
    d["like_count"] = int(d.get("like_count") or 0)
    return d


@app.get("/s/<slug>")
def detail(slug):
    with get_conn() as conn:
        s = fetch_one(conn, slug)
        if s is None:
            abort(404)
        sponsors = fetch_sponsors(conn)
    share_url = strategy_share_url(slug)
    thesis_snip = (s.get("thesis") or "")[:120]
    tweet_text = f"{s['title']}\n{thesis_snip}\n{share_url}"
    x_intent = "https://twitter.com/intent/tweet?text=" + quote(tweet_text, safe="")
    return render_template(
        "detail.html",
        s=s,
        sponsors=sponsors,
        updated=datetime.now(HKT).strftime("%b %-d, %Y · %H:%M HKT"),
        format_backtest=format_backtest,
        fmt_pct=fmt_pct,
        fmt_sharpe=fmt_sharpe,
        share_url=share_url,
        x_intent=x_intent,
    )


@app.get("/api/strategies/<slug>")
def api_strategy(slug):
    with get_conn() as conn:
        s = fetch_one(conn, slug)
    if s is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(s)


@app.post("/api/strategies/<slug>/like")
def api_like(slug):
    """Anonymous like; client should only call once per slug (localStorage)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, like_count FROM strategies WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404
        conn.execute(
            "UPDATE strategies SET like_count = COALESCE(like_count, 0) + 1 WHERE slug = ?",
            (slug,),
        )
        conn.commit()
        new_count = conn.execute(
            "SELECT like_count FROM strategies WHERE slug = ?", (slug,)
        ).fetchone()["like_count"]
    return jsonify({"slug": slug, "like_count": int(new_count or 0)})


# --- Ingest admin -----------------------------------------------------------------

def _ingest_counts(conn):
    rows = conn.execute(
        "SELECT status, COUNT(*) AS c FROM ingest_candidates GROUP BY status"
    ).fetchall()
    counts = {"pending": 0, "approved": 0, "rejected": 0, "all": 0}
    for r in rows:
        counts[r["status"]] = r["c"]
        counts["all"] += r["c"]
    return counts


@app.get("/admin/ingest")
def admin_ingest():
    status = (request.args.get("status") or "pending").lower()
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    with get_conn() as conn:
        counts = _ingest_counts(conn)
        if status == "all":
            rows = conn.execute(
                "SELECT * FROM ingest_candidates ORDER BY id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ingest_candidates WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
    return render_template(
        "admin_ingest.html",
        candidates=[dict(r) for r in rows],
        status=status,
        counts=counts,
    )


@app.post("/admin/ingest/<int:cid>/approve")
def admin_ingest_approve(cid):
    from ingest.pipeline import promote

    try:
        slug = promote(cid)
    except SystemExit as e:
        return str(e), 400
    return redirect(url_for("admin_ingest", status="approved"))


@app.post("/admin/ingest/<int:cid>/reject")
def admin_ingest_reject(cid):
    from ingest.pipeline import reject

    try:
        reject(cid)
    except SystemExit as e:
        return str(e), 400
    return redirect(url_for("admin_ingest", status="rejected"))


@app.post("/admin/run-ingest")
def admin_run_ingest():
    """Remote trigger for Digester / cron: fetch → stage only (never auto-promote).

    Auth: logged-in admin session OR Bearer / X-StratIndex-Token matching
    STRATINDEX_INGEST_TOKEN.
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}

    dry_run = (request.args.get("dry_run") or "").lower() in ("1", "true", "yes")
    if not dry_run and body.get("dry_run"):
        dry_run = True

    max_results = request.args.get("max", type=int)
    if max_results is None and body.get("max") is not None:
        try:
            max_results = int(body["max"])
        except (TypeError, ValueError):
            max_results = 3
    if max_results is None:
        max_results = 3
    max_results = max(1, min(int(max_results), 10))

    if not _INGEST_LOCK.acquire(blocking=False):
        return jsonify(
            {"ok": False, "error": "ingest already in progress — try again shortly"}
        ), 429

    try:
        from ingest.pipeline import run_once

        summary = run_once(max_results=max_results, dry_run=dry_run)
        # Keep response focused for Digester
        payload = {
            "ok": bool(summary.get("ok", True)),
            "fetched": summary.get("fetched", 0),
            "staged_new": summary.get("staged_new", 0),
            "skipped": summary.get("skipped", 0),
            "pending": summary.get("pending", 0),
            "dry_run": bool(summary.get("dry_run")),
        }
        if summary.get("ids"):
            payload["ids"] = summary["ids"]
        if summary.get("would_stage") is not None:
            payload["would_stage"] = summary["would_stage"]
        if summary.get("errors"):
            payload["errors"] = summary["errors"]
        status = 200 if payload["ok"] else 500
        return jsonify(payload), status
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        _INGEST_LOCK.release()


def main():
    dbmod.init_db()
    print(f"StratIndex listening on http://0.0.0.0:{PORT}")
    print("Homepage uses live strategies; review ingest at /admin/ingest (login required)")
    if not admin_password_configured():
        print("WARNING: STRATINDEX_ADMIN_PASSWORD unset — admin login will refuse until set")
    if not ingest_token_configured():
        print("NOTE: STRATINDEX_INGEST_TOKEN unset — Digester Bearer auth disabled (session login still works)")
    else:
        print("Remote ingest: POST /admin/run-ingest with Bearer / X-StratIndex-Token")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
