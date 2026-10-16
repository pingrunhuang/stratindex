"""Ingest pipeline: arXiv fetch → normalize → staging insert; optional promote."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python -m ingest` from project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db as dbmod
from ingest.arxiv_fetch import fetch_arxiv
from ingest.normalize import normalize


def _unique_slug(conn, base: str) -> str:
    slug = base or "strategy"
    n = 1
    candidate = slug
    while conn.execute("SELECT 1 FROM strategies WHERE slug = ?", (candidate,)).fetchone():
        n += 1
        candidate = f"{slug}-{n}"
    # also avoid colliding with other pending candidates' intended slugs? not required
    return candidate


def insert_candidate(conn, paper, fields: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO ingest_candidates (
          source_url, source_name, raw_excerpt, status, ai_model,
          slug, title, thesis, overview, rules_json, risks, backtest_notes, paper_prompt,
          asset, timeframe, style, badge,
          sharpe, max_dd, ret_90d, win_rate
        ) VALUES (
          ?, ?, ?, 'pending', ?,
          ?, ?, ?, ?, ?, ?, ?, ?,
          ?, ?, ?, ?,
          ?, ?, ?, ?
        )
        """,
        (
            paper.source_url,
            paper.source_name,
            paper.raw_excerpt,
            fields.get("ai_model", "heuristic"),
            fields["slug"],
            fields["title"],
            fields["thesis"],
            fields["overview"],
            fields["rules_json"],
            fields["risks"],
            fields["backtest_notes"],
            fields["paper_prompt"],
            fields["asset"],
            fields["timeframe"],
            fields["style"],
            fields["badge"],
            fields.get("sharpe"),
            fields.get("max_dd"),
            fields.get("ret_90d"),
            fields.get("win_rate"),
        ),
    )
    return int(cur.lastrowid)


def already_staged(conn, source_url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ingest_candidates WHERE source_url = ? LIMIT 1",
        (source_url,),
    ).fetchone()
    return row is not None


def _pending_count(conn) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM ingest_candidates WHERE status = 'pending'"
    ).fetchone()
    return int(row["c"] if row else 0)


def run_once(
    max_results: int = 3,
    *,
    skip_existing: bool = True,
    dry_run: bool = False,
) -> dict:
    """Fetch → normalize → stage (unless dry_run). Never promotes to live strategies.

    Returns dict with ok, fetched, staged_new, skipped, pending, ids, errors.
    """
    dbmod.init_db()
    errors: list[dict] = []
    ids: list[int] = []
    skipped = 0
    try:
        papers = fetch_arxiv(max_results=max_results)
    except Exception as e:  # noqa: BLE001 — surface to caller/API
        with dbmod.connect() as conn:
            pending = _pending_count(conn)
        return {
            "ok": False,
            "fetched": 0,
            "staged_new": 0,
            "skipped": 0,
            "pending": pending,
            "ids": [],
            "errors": [{"error": f"fetch failed: {e}"}],
            "dry_run": dry_run,
        }

    with dbmod.connect() as conn:
        for paper in papers:
            try:
                if skip_existing and already_staged(conn, paper.source_url):
                    print(f"skip (already staged): {paper.source_url}")
                    skipped += 1
                    continue
                fields = normalize(
                    paper.title, paper.abstract, paper.source_url, paper.source_name
                )
                if dry_run:
                    print(f"dry-run would stage [{fields.get('ai_model')}] {fields['title'][:70]}")
                    print(f"  {paper.source_url}")
                    ids.append(-1)  # placeholder; not written
                    continue
                cid = insert_candidate(conn, paper, fields)
                ids.append(cid)
                print(f"staged #{cid} [{fields.get('ai_model')}] {fields['title'][:70]}")
                print(f"  {paper.source_url}")
            except Exception as e:  # noqa: BLE001
                print(f"error on {paper.source_url}: {e}")
                errors.append({"url": paper.source_url, "error": str(e)})
        if not dry_run:
            conn.commit()
        pending = _pending_count(conn)

    staged_new = 0 if dry_run else len(ids)
    would_stage = len(ids) if dry_run else None
    result = {
        "ok": len(errors) == 0,
        "fetched": len(papers),
        "staged_new": staged_new,
        "skipped": skipped,
        "pending": pending,
        "ids": [] if dry_run else ids,
        "errors": errors or None,
        "dry_run": dry_run,
    }
    if dry_run:
        result["would_stage"] = would_stage
    return result


def promote(candidate_id: int) -> str:
    """Copy a pending/approved candidate into live strategies; return slug."""
    dbmod.init_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with dbmod.connect() as conn:
        row = conn.execute(
            "SELECT * FROM ingest_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise SystemExit(f"candidate {candidate_id} not found")
        d = dict(row)
        if d["status"] == "rejected":
            raise SystemExit(f"candidate {candidate_id} is rejected")
        slug = _unique_slug(conn, d["slug"] or "strategy")
        conn.execute(
            """
            INSERT INTO strategies (
              slug, badge, title, thesis, sharpe, max_dd, ret_90d, win_rate,
              asset, timeframe, style, source_name, source_url, is_new, last_backtest_at,
              overview, rules_json, risks, backtest_notes, paper_prompt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, date('now'), ?, ?, ?, ?, ?)
            """,
            (
                slug,
                d["badge"] or "AX",
                d["title"],
                d["thesis"],
                d["sharpe"],
                d["max_dd"],
                d["ret_90d"],
                d["win_rate"],
                d["asset"] or "BTC",
                d["timeframe"] or "1d",
                d["style"] or "Trend",
                d["source_name"],
                d["source_url"],
                d["overview"],
                d["rules_json"],
                d["risks"],
                d["backtest_notes"],
                d["paper_prompt"],
            ),
        )
        conn.execute(
            "UPDATE ingest_candidates SET status = 'approved', reviewed_at = ? WHERE id = ?",
            (now, candidate_id),
        )
        conn.commit()
    return slug


def reject(candidate_id: int) -> None:
    dbmod.init_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with dbmod.connect() as conn:
        cur = conn.execute(
            "UPDATE ingest_candidates SET status = 'rejected', reviewed_at = ? WHERE id = ?",
            (now, candidate_id),
        )
        if cur.rowcount == 0:
            raise SystemExit(f"candidate {candidate_id} not found")
        conn.commit()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="StratIndex ingest (arXiv → staging)")
    p.add_argument("--max", type=int, default=3, help="max arXiv results to fetch")
    p.add_argument("--promote", type=int, metavar="ID", help="promote staging id to live strategies")
    p.add_argument("--reject", type=int, metavar="ID", help="reject staging id")
    p.add_argument("--force", action="store_true", help="re-stage even if source_url exists")
    p.add_argument("--dry-run", action="store_true", help="fetch+normalize but do not insert")
    args = p.parse_args(argv)

    if args.promote is not None:
        slug = promote(args.promote)
        print(f"promoted candidate #{args.promote} → strategies.slug={slug}")
        return
    if args.reject is not None:
        reject(args.reject)
        print(f"rejected candidate #{args.reject}")
        return

    summary = run_once(
        max_results=args.max,
        skip_existing=not args.force,
        dry_run=args.dry_run,
    )
    if summary.get("dry_run"):
        print(
            f"done (dry-run): fetched={summary['fetched']} "
            f"would_stage={summary.get('would_stage', 0)} "
            f"skipped={summary['skipped']} pending={summary['pending']}"
        )
    else:
        print(
            f"done: {summary['staged_new']} new pending candidate(s) "
            f"(fetched={summary['fetched']} skipped={summary['skipped']} "
            f"pending={summary['pending']})"
        )
    if summary.get("errors"):
        for err in summary["errors"]:
            print(f"  error: {err}")


if __name__ == "__main__":
    main()
