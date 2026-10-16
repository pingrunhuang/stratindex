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

On first run the app creates the SQLite DB (default `./stratindex.db`, or `STRATINDEX_DB_PATH` / `STRATINDEX_DATA_DIR`) and seeds 12 strategies + 6 sponsors.

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
| `PORT` | Listen port (default `5055`; also used by Docker Compose publish) |
| `STRATINDEX_DB_PATH` | Full path to SQLite file (Docker default `/data/stratindex.db`) |
| `STRATINDEX_DATA_DIR` / `DATA_DIR` | Directory for `stratindex.db` if `STRATINDEX_DB_PATH` unset |
| `STRATINDEX_ADMIN_PASSWORD` | Browser login for `/admin/*` (humans) |
| `STRATINDEX_INGEST_TOKEN` | Bearer / `X-StratIndex-Token` for `POST /admin/run-ingest` (Digester bot). Do **not** reuse the admin password. |
| `STRATINDEX_SECRET_KEY` | Flask session signing (set this in Docker — do not rely on ephemeral `.flask_secret_key`) |
| `STRATINDEX_PUBLIC_BASE_URL` | Absolute URL for Copy link / Share on X |


## Docker

SQLite lives **outside** the image via a bind mount on `/data`. The app reads `STRATINDEX_DB_PATH` (default in the image: `/data/stratindex.db`).

### Build

```bash
cd /path/to/stratindex
docker build -t stratindex:local .
```

### Run (one-off)

```bash
mkdir -p data
docker run --rm -p 5055:5055 \
  -e PORT=5055 \
  -e STRATINDEX_DB_PATH=/data/stratindex.db \
  -e STRATINDEX_ADMIN_PASSWORD='choose-a-strong-password' \
  -e STRATINDEX_SECRET_KEY='long-random-string' \
  -e STRATINDEX_INGEST_TOKEN='long-random-bot-token' \
  -e STRATINDEX_PUBLIC_BASE_URL='https://stratindex.frank.com' \
  -v "$(pwd)/data:/data" \
  stratindex:local
```

Custom host port (same `PORT` for publish and listen):

```bash
docker run --rm -p 8080:8080 -e PORT=8080 \
  -e STRATINDEX_ADMIN_PASSWORD='...' -e STRATINDEX_SECRET_KEY='...' \
  -v "$(pwd)/data:/data" \
  stratindex:local
```

### Compose

```bash
cp .env.example .env   # fill secrets; never commit .env
mkdir -p data
docker compose up -d --build
# open http://127.0.0.1:${PORT:-5055}/
docker compose logs -f
docker compose down
```

Compose maps `"${PORT:-5055}:${PORT:-5055}"` and passes the same `PORT` into the container so listen and publish stay aligned. Host SQLite dir defaults to `./data` → `/data` (`STRATINDEX_DATA_HOST` overrides the host side).

Behind nginx, keep publishing only on localhost if desired (`ports: ["127.0.0.1:${PORT:-5055}:${PORT:-5055}"]`) and point `proxy_pass` at that port. Sample vhosts stay under `deploy/`.

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

## Strategy Grand Prix (race leaderboard)

Rule-based strategies (JSON only, no code) are backtested on the same public data and costs, then ranked on the homepage like an F1 timing tower.

- **Spec**: `race/engine.py::validate_spec` — indicators `sma`, `ema`, `rsi`, `atr`, `bollinger`, `donchian`; conditions `cross_above|cross_below|gt|lt`; `entry`/`exit` as `{"all":[…]}`/`{"any":[…]}`; stop `atr` or `pct`. Long-only spot, BTC/ETH/SOL-USDT, 4h.
- **Data**: OKX public `history-candles` (Binance is geo-blocked from the box), confirmed 4h candles since 2022-01-01, cached in `ohlcv.db` next to the main DB (i.e. `/data/ohlcv.db` in Docker).
- **Engine**: signal on close, fill next open, fee 0.1%/side + 0.05% slippage per fill, intrabar stops. Reports total return, CAGR, Sharpe (√2190), max DD, win rate, trades, equity curve; OOS = last 182 days. Rank = OOS Sharpe, tie → shallower OOS DD.
- **Pages**: `/` (timing tower + race replay), `/race/<slug>` (metrics, spec, reproduction steps), `/submit` (staging, `pending`), `/admin/race` (approve → joins grid + re-run; reject), `/api/race`.
- **Never auto-promotes**: submissions stay `pending` until an admin approves.

```bash
python -m race seed      # tables + 5 house strategies
python -m race fetch     # backfill OHLCV (~3 min first time, then incremental)
python -m race run       # refresh data, backtest all approved, store a new run, print table
python tests/test_race.py
# cron every 4h (after candle close), or: curl -XPOST -H "Authorization: Bearer $STRATINDEX_INGEST_TOKEN" $BASE/admin/race/run
```

### Submitter emails

`/submit` requires an email (validated, stored on the row, shown only in `/admin/race`). On **Approve** the submitter gets an email with their position after the re-run and a link to `$STRATINDEX_PUBLIC_BASE_URL/race/<slug>`; on **Reject** a short polite note. Sent with stdlib `smtplib` *after* the DB commit; the result is written to `notified_at` / `notify_error` and shown in the admin flash. If `SMTP_HOST`/`SMTP_FROM` are unset, sending is skipped and logged — approve/reject never fail because of email.

| Env | Meaning |
|---|---|
| `SMTP_HOST` | SMTP server (empty = don't send) |
| `SMTP_PORT` | default 587 (starttls) / 465 (ssl) |
| `SMTP_USER`, `SMTP_PASSWORD` | login (optional) |
| `SMTP_FROM` | e.g. `StratIndex <noreply@yourdomain>` |
| `SMTP_TLS` | `starttls` (default), `ssl`, or `none` |

No new Python dependencies (pure-stdlib engine + smtplib).
