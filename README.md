# StratIndex (local)

Dark Bloomberg-style trading-strategy aggregator. Seed metrics are placeholder. A **minimal ingest pipeline** can fetch public arXiv papers into a staging table for manual review before they appear on the homepage. Admin routes use a simple password. Public pages stay open.

## Layout

One-viewport homepage matching the approved mockup:

- Status line (count, Updated timestamp HKT, sources, new-today)
- Compact filter rail (Asset / Timeframe / Style / Sort) via query params
- New-today band + dense strategy rows
- Style pills + fixed bottom Sponsored marquee with **Advertise here** → `mailto:pingrunhuang@gmail.com?subject=StratIndex%20sponsorship`

## Setup

```bash
cd /workspace/stratindex
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On first run the app creates `stratindex.db` and seeds 12 strategies + 6 sponsors.

To re-seed from scratch:

```bash
source .venv/bin/activate
python db.py
```

## Start

```bash
cd /workspace/stratindex   # or /Users/frank/code/stratindex on Mac
source .venv/bin/activate
export STRATINDEX_ADMIN_PASSWORD='choose-a-strong-password'   # human admin login
export STRATINDEX_INGEST_TOKEN='long-random-bot-token'        # Digester / curl remote trigger
# optional: export STRATINDEX_SECRET_KEY='long-random-string'
# optional: export STRATINDEX_PUBLIC_BASE_URL='https://your.domain'  # for share links
python app.py
```

Open **http://127.0.0.1:5055/**

If `STRATINDEX_SECRET_KEY` is unset, Flask writes a random key to `.flask_secret_key` in the project root (gitignored recommended) and reuses it across restarts.

| Env | Purpose |
|-----|---------|
| `STRATINDEX_ADMIN_PASSWORD` | Browser login for `/admin/*` (humans) |
| `STRATINDEX_INGEST_TOKEN` | Bearer / `X-StratIndex-Token` for `POST /admin/run-ingest` (Digester bot). Do **not** reuse the admin password. |
| `STRATINDEX_SECRET_KEY` | Flask session signing |
| `STRATINDEX_PUBLIC_BASE_URL` | Absolute URL for Copy link / Share on X |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML homepage |
| `GET /api/strategies` | JSON strategies (`?asset=&timeframe=&style=&sort=newest\|sharpe\|return`) |
| `GET /api/stats` | Counts by asset/style/timeframe |
| `GET /api/sponsors` | Active sponsors |
| `POST /admin/run-ingest` | Auth required (session or ingest token). Runs arXiv → staging once. |

## Data model

- `strategies`: id, slug, badge, title, thesis, sharpe, max_dd, ret_90d, win_rate, asset, timeframe, style, source_name, source_url, is_new, last_backtest_at, created_at, like_count, detail fields
- `sponsors`: id, logo_text, name, tagline, url, sort_order, active
- `ingest_candidates`: staging rows from ingest (see Ingest section)


## Nav & Save

**Assets**, **Styles**, and **Sponsor** in the top nav are jump links to the filter rail (`#assets`), style pills (`#styles`), and sponsor marquee (`#sponsor`) — on detail pages they go to `/#…`. **Save** stores strategy slugs in browser `localStorage` under `stratindex-saved` (no login); open **Saved** (`/?view=saved`) to see only those rows.



## Ingest pipeline (staging → review → live)

Scrapers stay separate from the Flask templates. Flow:

1. Fetch public arXiv Atom results (crypto trading strategy query) — no API key
2. AI normalize into StratIndex fields (optional `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`; otherwise deterministic **heuristic**)
3. Insert into `ingest_candidates` with `status=pending` — **never** auto-writes the live `strategies` table
4. Review at `/admin/ingest`, then Approve (copy into `strategies`) or Reject

### Run once

```bash
cd /workspace/stratindex
source .venv/bin/activate
python -m ingest          # or: python scripts/ingest_once.py
python -m ingest --max 3  # fetch up to 3 papers
python -m ingest --force  # re-stage even if source_url already exists
```

Promote / reject from CLI (optional):

```bash
python -m ingest --promote 1
python -m ingest --reject 1
```

### Remote trigger (Digester / curl)

On the **machine that holds `stratindex.db`** (Mac now; server after deploy), Digester kicks ingest via a protected endpoint. Staging only — never auto-promotes to the homepage.

```bash
# Preferred: bot token (not the admin password)
curl -sS -X POST 'http://127.0.0.1:5055/admin/run-ingest' \
  -H "Authorization: Bearer $STRATINDEX_INGEST_TOKEN"

# Same token via custom header
curl -sS -X POST 'http://127.0.0.1:5055/admin/run-ingest' \
  -H "X-StratIndex-Token: $STRATINDEX_INGEST_TOKEN"

# Optional: dry-run (fetch+normalize, no DB insert) and max papers
curl -sS -X POST 'http://127.0.0.1:5055/admin/run-ingest?dry_run=1&max=3' \
  -H "Authorization: Bearer $STRATINDEX_INGEST_TOKEN"
```

Success JSON shape:

```json
{"ok": true, "fetched": 3, "staged_new": 0, "skipped": 3, "pending": 1, "dry_run": false}
```

- No auth → `401` JSON
- Wrong / missing token when `STRATINDEX_INGEST_TOKEN` unset → `401` with a clear error
- Overlapping run → `429` (`ingest already in progress`)
- Logged-in admin session cookie also works (humans from the browser); Digester should use the token

After deploy behind nginx (`stratindex.frank.com` → `proxy_pass http://127.0.0.1:5055`), keep **`/admin` on HTTPS only**. Digester calls `https://stratindex.frank.com/admin/run-ingest` with the Bearer token; do not expose port 5055 to the public internet.

### Review in browser (password protected)

1. Set `STRATINDEX_ADMIN_PASSWORD` and restart `python app.py`
2. Open **http://127.0.0.1:5055/admin/login** (or visit `/admin/ingest` and get redirected)
3. After login, review at **http://127.0.0.1:5055/admin/ingest**
4. Logout: **http://127.0.0.1:5055/admin/logout**

If the password env var is unset, login always fails with a clear “set STRATINDEX_ADMIN_PASSWORD” message — admin is never left open.

| Action | Effect |
|--------|--------|
| Approve | Inserts into live `strategies` (unique slug), sets candidate `approved` |
| Reject | Sets candidate `rejected`; homepage unchanged |

### Staging table

`ingest_candidates`: id, source_url, source_name, raw_excerpt, status (`pending`\|`approved`\|`rejected`), ai_model, slug/title/thesis/overview/rules_json/risks/backtest_notes/paper_prompt, asset/timeframe/style/badge, metrics (nullable), created_at, reviewed_at.


## Share & Like

- **Copy link** on detail (`/s/<slug>`) and list cards copies the absolute strategy URL (`STRATINDEX_PUBLIC_BASE_URL` if set, else `request.host_url`).
- **Share on X** (detail) opens Twitter/X intent with title + thesis snippet + URL.
- **Like** increments `strategies.like_count` via `POST /api/strategies/<slug>/like`. Same browser won’t double-count (localStorage `stratindex-liked`). No login required for likes.

## Notes

- All Sharpe / MaxDD / return / win-rate figures are **fabricated** for UI preview.
- Not investment advice.
