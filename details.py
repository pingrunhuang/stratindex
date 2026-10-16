"""Rich placeholder detail content per strategy slug. Placeholder only — not investment advice."""

PH = "PLACEHOLDER — illustrative assumptions, not a real backtest."

D = {
"funding-rate-mean-reversion-btc": dict(
 overview=[
  "Perpetual futures use an 8-hour funding payment to tether the perp price to spot. When funding prints at extreme positive levels, longs are paying heavily to stay levered — a sign that positioning is crowded and one-sided.",
  "This strategy fades those extremes. When the 8h funding rate exceeds its rolling 90th percentile AND open interest is elevated versus its 30-day average, it opens a small short (or a long on extreme negative funding), betting that the crowd will be forced to de-lever and funding will normalize.",
  "The edge is part carry (you receive the funding you are fading) and part mean reversion of price as leverage unwinds. Exits are mechanical: once funding returns inside its normal band the thesis is spent and the trade closes."],
 rules=["Signal: 8h funding > rolling 90th pct (short) or < 10th pct (long), 60-day window",
  "Filter: open interest > 1.15× its 30-day mean",
  "Entry: next funding-window open, market order, 0.5× base risk unit",
  "Exit: funding back inside 25th–75th pct band, OR 3 funding windows elapsed",
  "Stop: 2.5× 8h ATR adverse from entry"],
 risks=["Funding can stay extreme for days in strong trends — fading a squeeze is painful",
  "Exchange-specific funding formulas differ; signals don't port 1:1 across venues",
  "OI data quality varies and can be delayed",
  "Small sample of true extremes; results sensitive to percentile choice"],
 backtest=dict(universe="BTC-USDT perpetual, single venue", period="2021-01 → 2026-09", costs="5 bps taker per side, funding accrued, 2 bps slippage")),
"ema-ribbon-reclaim-eth": dict(
 overview=[
  "An EMA ribbon (21/50/200) summarizes short, medium and long trend state. A 'reclaim' happens when price drops below the ribbon and then closes back above all three lines — often the moment a pullback ends and trend resumes.",
  "False reclaims are common in chop, so the strategy demands participation: the reclaim bar's volume must exceed 1.5× the 20-bar median. Volume expansion suggests real buyers rather than drift.",
  "Positions trail the EMA21 so winners can run while losers are cut fast when price slips back under the ribbon."],
 rules=["Ribbon: EMA21, EMA50, EMA200 on 1h closes",
  "Entry: close crosses above max(EMA21, EMA50, EMA200) after ≥3 bars below",
  "Volume filter: bar volume > 1.5× 20-bar median",
  "Exit: 1h close below EMA21",
  "Hard stop: low of reclaim bar minus 0.5 ATR(14)"],
 risks=["Whipsaws in range-bound regimes erode edge quickly",
  "Volume on crypto venues may include wash trading",
  "Long-only — sits out downtrends entirely",
  "Low win rate (~49%) requires discipline through losing streaks"],
 backtest=dict(universe="ETH-USDT spot, 1h bars", period="2020-06 → 2026-09", costs="10 bps round-trip, 3 bps slippage")),
"basis-trade-spot-quarterly": dict(
 overview=[
  "Quarterly futures usually trade at a premium (contango) to spot. Buying spot and shorting the quarterly locks in that premium as it converges to zero at expiry — a classic cash-and-carry.",
  "The trade only makes sense when the annualized basis comfortably exceeds funding cost of capital, fees and a safety buffer. This strategy checks daily and opens only above a hurdle.",
  "Returns are low-volatility and steady, which explains the high Sharpe, but absolute returns are modest and capital-intensive. Main dangers are operational: margin calls on the short leg and venue risk."],
 rules=["Compute annualized basis = (fut/spot − 1) × 365 / days_to_expiry",
  "Entry: basis > costs + 4% annualized buffer",
  "Position: long spot, short equal notional quarterly future",
  "Exit: hold to expiry, OR close early if basis compresses below 1% annualized",
  "Keep short-leg margin ratio ≥ 3× maintenance"],
 risks=["Counterparty / exchange failure on either leg",
  "Short-leg liquidation in violent rallies if under-margined",
  "Opportunity cost — capital locked for weeks",
  "Basis can widen before converging (mark-to-market drawdown)"],
 backtest=dict(universe="BTC spot + BTC quarterly futures", period="2020-01 → 2026-09", costs="4 bps per leg, 5% annual cost of capital")),
"inventory-skew-mm-eth": dict(
 overview=[
  "A market maker earns the spread by quoting bids and asks simultaneously. The core danger is inventory: if buyers keep lifting you, you end up short into a rally.",
  "Inventory skew shifts both quotes against current position — long inventory lowers both quotes to sell more and buy less — in the spirit of Avellaneda–Stoikov. Spreads widen automatically when short-term realized volatility spikes.",
  "Win rate is not meaningful for continuous quoting, so it is omitted. Performance is judged on spread capture minus adverse selection per unit of inventory risk."],
 rules=["Mid = microprice from top-of-book",
  "Half-spread = max(min_tick, k × σ_1m)",
  "Skew: shift quotes by −γ × inventory × σ²",
  "Max inventory: ±N contracts; stop quoting the side that would breach",
  "Pull all quotes if 1m σ > 3× its 1h average"],
 risks=["Adverse selection from informed flow / latency disadvantage",
  "Requires low-latency infra; tick-level backtests overstate fills",
  "Maker rebates/fee tiers dominate economics",
  "Gap risk on news events"],
 backtest=dict(universe="ETH-USDT order book, L2 snapshots", period="2025-01 → 2026-09", costs="−1 bp maker rebate, queue-position fill model")),
"perp-funding-harvest-hedge": dict(
 overview=[
  "When perpetual funding is positive, shorts get paid. Shorting the perp while holding equal spot makes you delta-neutral and collects funding as income.",
  "Daily rebalancing keeps hedge ratio near 1.0 as prices move and frees excess margin. The strategy turns off when the 7-day average funding falls below fees.",
  "This is a yield trade: smooth equity curve, low drawdowns, returns tied to market leverage appetite."],
 rules=["Enter when 7d avg funding (annualized) > 8%",
  "Long spot, short equal-notional perp",
  "Rebalance once per day to delta |hedge − 1| < 2%",
  "Exit when 7d avg funding < 3% annualized or turns negative",
  "Maintain perp margin ratio ≥ 4× maintenance"],
 risks=["Funding regimes flip; negative funding makes you pay",
  "Exchange risk on custodied spot and margin",
  "Liquidation of short leg during sharp squeezes",
  "Yield compresses as strategy becomes crowded"],
 backtest=dict(universe="BTC spot + BTC-USDT perp", period="2021-01 → 2026-09", costs="5 bps per leg on entry/rebalance")),
"atr-breakout-trailing": dict(
 overview=[
  "Volatility breakouts try to catch the start of directional moves. Requiring price to clear the 20-bar high by an extra 1.5 ATR filters out minor pokes above resistance.",
  "Once in, a 2 ATR trailing stop locks in gains while leaving room for normal noise. Low-volume breakouts are skipped since they fail more often.",
  "Expect a low win rate offset by large winners — the classic trend-following payoff profile."],
 rules=["Entry long: close > 20-bar high + 1.5 × ATR(14)",
  "Volume filter: volume > 20-bar average",
  "Trailing stop: highest close since entry − 2 × ATR(14)",
  "Symmetric short rules optional (disabled in base config)",
  "Risk 0.75% equity per trade, sized by ATR distance"],
 risks=["Many small losers; drawdown streaks are long",
  "Breakouts gap through stops on news",
  "Parameter sensitivity on ATR multiples",
  "Edge decays in mean-reverting regimes"],
 backtest=dict(universe="BTC-USDT, 4h bars", period="2019-01 → 2026-06", costs="10 bps round-trip, 5 bps slippage")),
"rsi2-mean-reversion-perps": dict(
 overview=[
  "RSI(2) is an ultra-short oscillator that flags sharp, short-lived oversold dips. In an uptrend, these dips tend to snap back quickly.",
  "The strategy only buys when price is above its 200-bar moving average, so it buys weakness inside strength rather than catching falling knives.",
  "Holding periods are very short, with a 3-bar time stop to avoid dead capital. High win rate, but occasional large losses produce the deepest drawdown in this list."],
 rules=["Trend filter: close > SMA(200)",
  "Entry: RSI(2) < 5 at bar close",
  "Exit: RSI(2) > 50, OR 3 bars elapsed",
  "Universe: top-10 perps by 30d volume",
  "Max 3 concurrent positions, equal weight"],
 risks=["Left-tail losses when trend breaks during a dip",
  "No stop by default — consider a 3 ATR catastrophic stop",
  "Correlated crypto positions act as one bet",
  "Fees matter a lot at this trade frequency"],
 backtest=dict(universe="Top-10 USDT perps by volume", period="2021-01 → 2026-06", costs="6 bps per side, funding accrued")),
"pairs-stat-arb-btc-eth": dict(
 overview=[
  "BTC and ETH share a strong common factor. Regressing log(ETH) on log(BTC) over a rolling window leaves a residual that tends to mean revert.",
  "When the residual's z-score stretches beyond ±2, the strategy goes long the cheap leg and short the rich leg in hedge-ratio proportion, closing when |z| falls below 0.5.",
  "This is market-neutral by construction, but the relationship can break during structural shifts (e.g. ETH-specific catalysts)."],
 rules=["Rolling OLS: log(ETH) = α + β·log(BTC) over 120 bars (4h)",
  "z = (residual − mean) / std over same window",
  "Entry: z > 2 → short ETH / long β·BTC; z < −2 → reverse",
  "Exit: |z| < 0.5; Stop: |z| > 4 or 30 bars elapsed",
  "Re-estimate β each bar; no trade if half-life > 20 bars"],
 risks=["Cointegration breakdown during regime change",
  "Hedge ratio estimation error",
  "Two-leg execution & funding costs",
  "Crowded trade among quant desks"],
 backtest=dict(universe="BTC-USDT & ETH-USDT perps, 4h", period="2020-06 → 2026-09", costs="5 bps per leg per side, funding accrued")),
"vol-target-trend-eth": dict(
 overview=[
  "Raw trend signals produce wildly varying risk because crypto volatility swings. Volatility targeting scales position size so the strategy aims for constant 10% annualized vol.",
  "The trend signal is a blend of 20/60/120-day momentum. When implied volatility spikes above its recent range, exposure is cut further to dodge crash regimes.",
  "The result trades some upside for smoother drawdowns and more consistent risk-adjusted returns."],
 rules=["Signal: avg sign of 20, 60, 120-day returns (−1..+1)",
  "Size = signal × (10% / realized 30d vol), capped at 2× leverage",
  "IV filter: if DVOL > 90th pct of 1y, halve size",
  "Rebalance daily at 00:00 UTC; skip if change < 10%",
  "Long/short allowed"],
 risks=["Vol estimates lag sudden shocks",
  "Leverage cap binds in calm regimes",
  "Implied vol data availability",
  "Trend whipsaws at turning points"],
 backtest=dict(universe="ETH-USDT perp, daily", period="2019-01 → 2026-08", costs="8 bps per rebalance, funding accrued")),
"cross-exchange-funding-arb": dict(
 overview=[
  "Funding rates for the same perpetual contract differ across exchanges because user bases and leverage appetites differ.",
  "This strategy goes long the perp on the low-funding venue and short on the high-funding venue, pocketing the spread while staying price-neutral.",
  "The residual risk is basis between venues' mark prices and the operational burden of margin on two exchanges."],
 rules=["Monitor funding for BTC, ETH, SOL perps across 3 venues",
  "Entry: annualized funding spread > 10% for 3 consecutive windows",
  "Long low-funding venue, short high-funding venue, equal notional",
  "Exit: spread < 3% annualized, or venue mark divergence > 0.5%",
  "Rebalance margin across venues weekly"],
 risks=["Venue/counterparty failure",
  "Mark-price divergence triggers one-sided liquidation",
  "Withdrawal delays when moving collateral",
  "Funding spreads compress fast once noticed"],
 backtest=dict(universe="BTC/ETH/SOL perps on 3 venues", period="2022-01 → 2026-09", costs="5 bps per leg, transfer cost 0.02%")),
"donchian-channel-breakout": dict(
 overview=[
  "Donchian breakouts — the Turtle classic — buy new 55-bar highs. On their own they whipsaw badly in sideways markets.",
  "Adding an ADX > 25 condition requires that a trend is already underway, removing many false breakouts at the cost of slightly later entries.",
  "The mid-channel trailing exit gives trades breathing room. Expect a sub-40% win rate with fat right tails."],
 rules=["Entry long: close > 55-bar high; short: close < 55-bar low",
  "Filter: ADX(14) > 25",
  "Exit: close crosses Donchian mid-line (avg of 55-bar high/low)",
  "Initial stop: 2 × ATR(20)",
  "Risk 1% equity per trade"],
 risks=["Late entries give back part of moves",
  "Long flat periods with no signals",
  "Low win rate is psychologically hard",
  "Single-asset concentration"],
 backtest=dict(universe="BTC-USDT, 4h bars", period="2018-01 → 2026-05", costs="10 bps round-trip, 5 bps slippage")),
"liquidations-cascade-fade": dict(
 overview=[
  "Cascading liquidations push price beyond fair value as forced sellers hit thin books. Once the cascade exhausts, price often rebounds sharply.",
  "This strategy detects a ≥2% move within 15 minutes accompanied by a spike in liquidation volume, then fades it with a tight stop just beyond the wick.",
  "It is opportunistic and infrequent, with high payoff when right and quick, small losses when wrong."],
 rules=["Trigger: |1h return| ≥ 2% within 15 min AND liquidations > 5× 24h hourly avg",
  "Entry: after first 1-minute bar closing back inside the wick",
  "Stop: 0.3% beyond wick extreme",
  "Target: 50% retrace of cascade, or 6 hours",
  "Max 1 trade per 24h"],
 risks=["Cascades can extend in waves — catching a falling knife",
  "Liquidation data feeds are incomplete and delayed",
  "Slippage during extreme volatility",
  "Rare events → small sample size"],
 backtest=dict(universe="BTC-USDT perp, 1m/1h data", period="2021-01 → 2026-10", costs="6 bps per side, 10 bps slippage on entry")),
}


def build_prompt(s: dict, d: dict) -> str:
    rules = "\n".join(f"  - {r}" for r in d["rules"])
    return f"""You are a PAPER-TRADING bot. Never place real orders.

Strategy: {s['title']} ({s['badge']})
Market: {s['asset']} · timeframe {s['timeframe']} · style {s['style']}
Thesis: {s['thesis']}

Rules:
{rules}

Tasks:
1. Pull {s['timeframe']} historical data for {s['asset']} and compute all indicators above.
2. Backtest {d['backtest']['period']} with costs: {d['backtest']['costs']}.
3. Report Sharpe, max drawdown, win rate, trade count, and an equity curve.
4. Run a live paper loop: log every signal, simulated fill, and PnL to a CSV.
5. Halt and alert if drawdown exceeds 1.5x the backtest MaxDD.

Output clean, commented Python. Placeholder research only — not investment advice."""


def enrich(s: dict) -> dict:
    import json
    d = D[s["slug"]]
    b = d["backtest"]
    return dict(
        overview="\n\n".join(d["overview"]),
        rules_json=json.dumps(d["rules"]),
        risks="\n".join(d["risks"]),
        backtest_notes=f"Universe: {b['universe']}\nPeriod: {b['period']}\nCosts: {b['costs']}\n{PH}",
        paper_prompt=build_prompt(s, d),
    )
