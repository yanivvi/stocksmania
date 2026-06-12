#!/usr/bin/env python3
"""Backtest: weekly buys of top BUY picks, exit when price reaches the MA or overbought.

Simulates following this repo's 150-day MA rules — not financial advice.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from build_site import signal
from config import OVERBOUGHT, ROLLING_WINDOW
from telegram_notify import calculate_buy_score

ROOT = Path(__file__).parent
DATA = ROOT / "data"

DEFAULT_MONTHLY_BUDGET = 1000.0
DEFAULT_TOP_N = 3
WEEKS_PER_MONTH = 4


@dataclass
class Trade:
    date: date
    action: str  # BUY | SELL
    symbol: str
    shares: float
    price: float
    amount: float
    vs_ma: float | None
    reason: str


@dataclass
class Snapshot:
    date: date
    cash: float
    holdings_value: float
    total: float
    invested: float
    gain: float
    gain_pct: float
    open_positions: int


@dataclass
class TickerPosition:
    """Open holding with cumulative P&L history for charting."""

    symbol: str
    shares: float
    cost: float
    market_value: float
    unrealized: float
    realized: float
    total_pnl: float
    total_pnl_pct: float
    history: list[tuple[date, float]]


@dataclass
class SimResult:
    trades: list[Trade] = field(default_factory=list)
    snapshots: list[Snapshot] = field(default_factory=list)
    monthly: list[dict] = field(default_factory=list)
    positions: dict[str, TickerPosition] = field(default_factory=dict)
    final_cash: float = 0.0
    final_holdings: dict[str, float] = field(default_factory=dict)
    total_invested: float = 0.0
    final_value: float = 0.0
    start_date: date | None = None
    end_date: date | None = None


def read_tickers(stocks_file: Path | None = None) -> list[str]:
    path = stocks_file or ROOT / "stocks.txt"
    if not path.exists():
        return []
    return [
        line.strip().upper()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def prepare_history(df: pd.DataFrame) -> pd.DataFrame:
    """Add MA, vs_ma, daily_change, and signal columns."""
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.date
    out = out.sort_values("Date").reset_index(drop=True)
    ma_col = f"Rolling_Avg_{ROLLING_WINDOW}d"
    if ma_col not in out.columns or out[ma_col].isna().all():
        out[ma_col] = out["Close"].rolling(window=ROLLING_WINDOW, min_periods=ROLLING_WINDOW).mean()
    out["vs_ma"] = ((out["Close"] - out[ma_col]) / out[ma_col] * 100).where(out[ma_col].notna())
    out["daily_change"] = out["Close"].pct_change() * 100
    out["signal"] = out["vs_ma"].apply(lambda v: signal(v)[0] if pd.notna(v) else "HOLD")
    return out


def load_histories(
    symbols: list[str],
    data_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    base = data_dir or DATA
    histories: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        csv = base / f"{sym}_prices.csv"
        if not csv.exists():
            continue
        try:
            df = pd.read_csv(csv)
        except Exception:
            continue
        if len(df) < ROLLING_WINDOW + 1:
            continue
        histories[sym.upper()] = prepare_history(df)
    return histories


def week_end_dates(histories: dict[str, pd.DataFrame]) -> list[date]:
    all_dates: set[date] = set()
    for df in histories.values():
        all_dates.update(df["Date"].tolist())
    if not all_dates:
        return []
    s = pd.Series(sorted(all_dates))
    # Last trading day in each ISO week.
    ends = s.groupby(pd.to_datetime(s).dt.to_period("W")).max()
    return [d.date() if hasattr(d, "date") else d for d in ends.tolist()]


def row_on(histories: dict[str, pd.DataFrame], sym: str, on: date) -> pd.Series | None:
    df = histories.get(sym)
    if df is None:
        return None
    rows = df[df["Date"] == on]
    if rows.empty:
        return None
    return rows.iloc[-1]


def should_exit(vs_ma: float | None) -> tuple[bool, str]:
    """Exit when price reaches MA (vs_ma <= 0) or hits overbought threshold."""
    if vs_ma is None:
        return False, ""
    if vs_ma >= OVERBOUGHT:
        return True, f"overbought (+{vs_ma:.1f}% vs MA)"
    if vs_ma <= 0:
        return True, f"reached MA ({vs_ma:+.1f}% vs MA)"
    return False, ""


def rank_buy_leaders(histories: dict[str, pd.DataFrame], on: date, top_n: int) -> list[tuple[str, float, float]]:
    """Return top-N BUY tickers by repo buy score: (symbol, score, price)."""
    candidates: list[tuple[str, float, float]] = []
    for sym in histories:
        row = row_on(histories, sym, on)
        if row is None or pd.isna(row["vs_ma"]):
            continue
        if row["signal"] != "BUY":
            continue
        chg = float(row["daily_change"]) if pd.notna(row["daily_change"]) else 0.0
        score = calculate_buy_score(float(row["vs_ma"]), chg)
        candidates.append((sym, score, float(row["Close"])))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_n]


def run_simulation(
    histories: dict[str, pd.DataFrame],
    *,
    monthly_budget: float = DEFAULT_MONTHLY_BUDGET,
    top_n: int = DEFAULT_TOP_N,
    start: date | None = None,
    end: date | None = None,
) -> SimResult:
    weekly_budget = monthly_budget / WEEKS_PER_MONTH
    weeks = week_end_dates(histories)
    if not weeks:
        return SimResult()

    if start:
        weeks = [w for w in weeks if w >= start]
    if end:
        weeks = [w for w in weeks if w <= end]
    if not weeks:
        return SimResult()

    # Skip warmup: need at least one symbol with MA on that day.
    while weeks:
        if any(
            (r := row_on(histories, sym, weeks[0])) is not None and pd.notna(r["vs_ma"])
            for sym in histories
        ):
            break
        weeks.pop(0)
    if not weeks:
        return SimResult()

    cash = 0.0
    shares: dict[str, float] = {}
    cost: dict[str, float] = {}
    realized: dict[str, float] = {}
    pnl_history: dict[str, list[tuple[date, float]]] = {}
    invested = 0.0
    trades: list[Trade] = []
    snapshots: list[Snapshot] = []

    def record_open_pnl(on: date) -> None:
        for sym, qty in shares.items():
            if qty <= 0:
                continue
            row = row_on(histories, sym, on)
            if row is None:
                continue
            price = float(row["Close"])
            unrealized = qty * price - cost.get(sym, 0.0)
            total = realized.get(sym, 0.0) + unrealized
            pnl_history.setdefault(sym, []).append((on, total))

    for week_end in weeks:
        # --- exits at week close ---
        for sym in list(shares.keys()):
            if shares[sym] <= 0:
                continue
            row = row_on(histories, sym, week_end)
            if row is None:
                continue
            vs_ma = float(row["vs_ma"]) if pd.notna(row["vs_ma"]) else None
            exit_now, reason = should_exit(vs_ma)
            if not exit_now:
                continue
            price = float(row["Close"])
            qty = shares[sym]
            proceeds = qty * price
            basis = cost.get(sym, 0.0)
            realized[sym] = realized.get(sym, 0.0) + (proceeds - basis)
            cash += proceeds
            trades.append(
                Trade(week_end, "SELL", sym, qty, price, proceeds, vs_ma, reason)
            )
            shares[sym] = 0.0
            cost[sym] = 0.0
            pnl_history.setdefault(sym, []).append((week_end, realized[sym]))

        # --- weekly deposit ---
        cash += weekly_budget
        invested += weekly_budget

        # --- buys: top leaders ---
        leaders = rank_buy_leaders(histories, week_end, top_n)
        if leaders:
            per_stock = cash / len(leaders)
            for sym, score, price in leaders:
                if price <= 0 or per_stock < 1:
                    continue
                qty = per_stock / price
                shares[sym] = shares.get(sym, 0.0) + qty
                cost[sym] = cost.get(sym, 0.0) + per_stock
                cash -= per_stock
                row = row_on(histories, sym, week_end)
                vs_ma = float(row["vs_ma"]) if row is not None and pd.notna(row["vs_ma"]) else None
                trades.append(
                    Trade(
                        week_end,
                        "BUY",
                        sym,
                        qty,
                        price,
                        per_stock,
                        vs_ma,
                        f"top BUY (score {score:.0f})",
                    )
                )

        record_open_pnl(week_end)

        holdings_value = 0.0
        open_positions = 0
        for sym, qty in shares.items():
            if qty <= 0:
                continue
            row = row_on(histories, sym, week_end)
            if row is None:
                continue
            holdings_value += qty * float(row["Close"])
            open_positions += 1

        total = cash + holdings_value
        gain = total - invested
        gain_pct = (gain / invested * 100) if invested else 0.0
        snapshots.append(
            Snapshot(
                week_end,
                cash,
                holdings_value,
                total,
                invested,
                gain,
                gain_pct,
                open_positions,
            )
        )

    # Monthly rollup from snapshots.
    monthly: list[dict] = []
    if snapshots:
        df = pd.DataFrame([s.__dict__ for s in snapshots])
        df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
        for month, grp in df.groupby("month"):
            last = grp.iloc[-1]
            first = grp.iloc[0]
            monthly.append(
                {
                    "month": month,
                    "weeks": len(grp),
                    "invested": float(last["invested"]),
                    "value": float(last["total"]),
                    "gain": float(last["gain"]),
                    "gain_pct": float(last["gain_pct"]),
                    "month_change": float(last["total"] - first["total"]),
                }
            )

    final = snapshots[-1] if snapshots else None
    positions: dict[str, TickerPosition] = {}
    end = weeks[-1]
    for sym, qty in shares.items():
        if qty <= 0:
            continue
        row = row_on(histories, sym, end)
        if row is None:
            continue
        price = float(row["Close"])
        basis = cost.get(sym, 0.0)
        mkt = qty * price
        unreal = mkt - basis
        real = realized.get(sym, 0.0)
        total = real + unreal
        pct = (total / basis * 100) if basis else 0.0
        positions[sym] = TickerPosition(
            symbol=sym,
            shares=qty,
            cost=basis,
            market_value=mkt,
            unrealized=unreal,
            realized=real,
            total_pnl=total,
            total_pnl_pct=pct,
            history=pnl_history.get(sym, []),
        )

    return SimResult(
        trades=trades,
        snapshots=snapshots,
        monthly=monthly,
        positions=positions,
        final_cash=cash,
        final_holdings={s: q for s, q in shares.items() if q > 0},
        total_invested=invested,
        final_value=final.total if final else 0.0,
        start_date=weeks[0],
        end_date=weeks[-1],
    )


def portfolio_chart_svg(snapshots: list[Snapshot], *, width: int = 800, height: int = 220) -> str:
    if len(snapshots) < 2:
        return '<p class="muted">Not enough history for chart.</p>'
    totals = [s.total for s in snapshots]
    invested = [s.invested for s in snapshots]
    lo = min(min(totals), min(invested))
    hi = max(max(totals), max(invested))
    span = (hi - lo) or 1.0
    n = len(snapshots)

    def line(vals: list[float], cls: str) -> str:
        pts = " ".join(
            f"{i * width / (n - 1):.1f},{height - (v - lo) / span * (height - 8) - 4:.1f}"
            for i, v in enumerate(vals)
        )
        return (
            f'<polyline class="{cls}" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linejoin="round" points="{pts}" />'
        )

    return f"""<svg class="whatif-chart" viewBox="0 0 {width} {height}" preserveAspectRatio="none"
      aria-label="Portfolio value over time">
      {line(invested, "line-invested")}
      {line(totals, "line-value")}
    </svg>
    <div class="chart-legend">
      <span><i class="swatch invested"></i> Cash invested</span>
      <span><i class="swatch value"></i> Portfolio value</span>
    </div>"""


def ticker_pnl_chart_svg(history: list[tuple[date, float]], *, width: int = 360, height: int = 100) -> str:
    if len(history) < 2:
        val = history[0][1] if history else 0.0
        cls = "up" if val >= 0 else "down"
        return f'<p class="muted pnl-flat {cls}">P&L: ${val:+,.2f}</p>'
    vals = [v for _, v in history]
    lo = min(min(vals), 0.0)
    hi = max(max(vals), 0.0)
    span = (hi - lo) or 1.0
    n = len(vals)
    pts = " ".join(
        f"{i * width / (n - 1):.1f},{height - (v - lo) / span * (height - 6) - 3:.1f}"
        for i, v in enumerate(vals)
    )
    zero_y = height - (0 - lo) / span * (height - 6) - 3
    end_cls = "up" if vals[-1] >= 0 else "down"
    return f"""<svg class="ticker-pnl-chart {end_cls}" viewBox="0 0 {width} {height}" preserveAspectRatio="none"
      aria-label="Cumulative P&amp;L">
      <line x1="0" y1="{zero_y:.1f}" x2="{width}" y2="{zero_y:.1f}" stroke="var(--border)" stroke-width="1"/>
      <polyline fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" points="{pts}" />
    </svg>"""


def position_cards_html(positions: dict[str, TickerPosition]) -> str:
    if not positions:
        return '<p class="muted">No open positions in the simulated portfolio.</p>'
    cards = []
    for sym in sorted(positions, key=lambda s: positions[s].total_pnl, reverse=True):
        p = positions[sym]
        pnl_cls = "up" if p.total_pnl >= 0 else "down"
        cards.append(
            f"""
      <article class="pos-card">
        <header>
          <h3><a href="t/{sym}.html">{sym}</a></h3>
          <span class="pnl-badge {pnl_cls}">${p.total_pnl:+,.0f} ({p.total_pnl_pct:+.1f}%)</span>
        </header>
        {ticker_pnl_chart_svg(p.history)}
        <div class="pos-grid">
          <div><span class="lbl">Shares</span><span class="val">{p.shares:.3f}</span></div>
          <div><span class="lbl">Cost</span><span class="val">${p.cost:,.0f}</span></div>
          <div><span class="lbl">Value</span><span class="val">${p.market_value:,.0f}</span></div>
          <div><span class="lbl">Unrealized</span><span class="val {pnl_cls}">${p.unrealized:+,.0f}</span></div>
        </div>
      </article>"""
        )
    return f'<div class="pos-grid-wrap">{"".join(cards)}</div>'


def render_html(result: SimResult, *, monthly_budget: float, top_n: int) -> str:
    weekly = monthly_budget / WEEKS_PER_MONTH
    final = result.snapshots[-1] if result.snapshots else None
    gain_cls = "up" if final and final.gain >= 0 else "down"
    gain_amt = final.gain if final else 0.0
    gain_pct = final.gain_pct if final else 0.0

    trade_rows = ""
    for t in reversed(result.trades[-80:]):
        vs = f"{t.vs_ma:+.1f}%" if t.vs_ma is not None else "—"
        action_cls = "buy" if t.action == "BUY" else "sell"
        trade_rows += (
            f"<tr><td>{t.date}</td><td class='{action_cls}'>{t.action}</td>"
            f"<td><b>{t.symbol}</b></td><td class='num'>{t.shares:.4f}</td>"
            f"<td class='num'>${t.price:.2f}</td><td class='num'>${t.amount:.2f}</td>"
            f"<td class='num'>{vs}</td><td>{t.reason}</td></tr>"
        )

    month_rows = ""
    for m in result.monthly:
        chg_cls = "up" if m["month_change"] >= 0 else "down"
        month_rows += (
            f"<tr><td>{m['month']}</td><td class='num'>{m['weeks']}</td>"
            f"<td class='num'>${m['invested']:,.0f}</td>"
            f"<td class='num'>${m['value']:,.0f}</td>"
            f"<td class='num {chg_cls}'>{m['gain_pct']:+.1f}%</td>"
            f"<td class='num {chg_cls}'>${m['month_change']:+,.0f}</td></tr>"
        )

    open_rows = ""
    if result.final_holdings and result.end_date:
        for sym, qty in sorted(result.final_holdings.items()):
            p = result.positions.get(sym)
            if p:
                cls = "up" if p.total_pnl >= 0 else "down"
                open_rows += (
                    f"<tr><td><b>{sym}</b></td><td class='num'>{qty:.4f}</td>"
                    f"<td class='num'>${p.cost:,.0f}</td><td class='num'>${p.market_value:,.0f}</td>"
                    f"<td class='num {cls}'>${p.total_pnl:+,.0f}</td></tr>"
                )
            else:
                open_rows += f"<tr><td><b>{sym}</b></td><td class='num'>{qty:.4f}</td><td colspan='3' class='muted'>—</td></tr>"

    position_cards = position_cards_html(result.positions)

    period = ""
    if result.start_date and result.end_date:
        period = f"{result.start_date} → {result.end_date}"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>StocksMania – What If</title>
  <link rel="stylesheet" href="assets/site.css">
  <style>
    .whatif-chart {{ width: 100%; max-height: 240px; color: var(--link); }}
    .line-invested {{ color: var(--muted); stroke-dasharray: 6 4; opacity: .85; }}
    .line-value {{ color: var(--green); }}
    .chart-legend {{ display: flex; gap: 16px; font-size: 12px; color: var(--muted); margin: 8px 0 20px; }}
    .swatch {{ display: inline-block; width: 14px; height: 3px; vertical-align: middle; margin-right: 4px; }}
    .swatch.invested {{ background: var(--muted); }}
    .swatch.value {{ background: var(--green); }}
    .hero {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .stat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
    .stat .lbl {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
    .stat .val {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
    .rules {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
      padding: 14px 16px; margin-bottom: 20px; font-size: 14px; line-height: 1.5; }}
    table.whatif {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    table.whatif th, table.whatif td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
    table.whatif td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    table.whatif td.buy {{ color: var(--green); font-weight: 600; }}
    table.whatif td.sell {{ color: var(--red); font-weight: 600; }}
    section.block {{ margin-bottom: 28px; }}
    section.block h2 {{ font-size: 16px; margin: 0 0 10px; }}
    .pos-grid-wrap {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }}
    .pos-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
    .pos-card header {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }}
    .pos-card h3 {{ margin: 0; font-size: 18px; }}
    .pos-card h3 a {{ color: var(--text); text-decoration: none; }}
    .pos-card h3 a:hover {{ color: var(--link); }}
    .pnl-badge {{ font-size: 13px; font-weight: 700; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }}
    .pnl-badge.up {{ background: var(--green-bg); color: var(--green); }}
    .pnl-badge.down {{ background: var(--red-bg); color: var(--red); }}
    .ticker-pnl-chart {{ width: 100%; height: 100px; display: block; margin: 4px 0 10px; }}
    .ticker-pnl-chart.up {{ color: var(--green); }}
    .ticker-pnl-chart.down {{ color: var(--red); }}
    .pos-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; }}
    .pos-grid .lbl {{ display: block; color: var(--muted); font-size: 11px; text-transform: uppercase; }}
    .pos-grid .val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
    .disclaimer {{ font-size: 12px; color: var(--muted); margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="topbar">
    <div>
      <a href="index.html" style="color:var(--link);text-decoration:none;font-size:13px">← Status dashboard</a>
      <h1 style="margin-top:6px">🔮 What If – MA Strategy Backtest</h1>
      <div class="sub">{period} · simulated weekly follow of this repo's BUY leaders</div>
    </div>
    <button class="theme-toggle" id="theme-toggle" type="button">🌗 Theme</button>
  </div>

  <div class="rules">
    <b>Simulation rules</b> (uses the same thresholds as <code>config.py</code>):<br>
    • Each week, invest <b>${weekly:,.0f}</b> (${monthly_budget:,.0f}/month) split equally among the
      top <b>{top_n}</b> tickers with a <b>BUY</b> signal (ranked by the repo's buy score).<br>
    • <b>Sell</b> when price reaches the 150-day MA (<code>vs MA ≤ 0</code>) or goes overbought
      (<code>vs MA ≥ {OVERBOUGHT}%</code>).<br>
    • Uses historical closes from tracked CSVs; no fees, slippage, or taxes.
  </div>

  <div class="hero">
    <div class="stat"><div class="lbl">Total invested</div><div class="val">${result.total_invested:,.0f}</div></div>
    <div class="stat"><div class="lbl">Portfolio value</div><div class="val">${result.final_value:,.0f}</div></div>
    <div class="stat"><div class="lbl">Gain / loss</div>
      <div class="val {gain_cls}">${gain_amt:+,.0f} ({gain_pct:+.1f}%)</div></div>
    <div class="stat"><div class="lbl">Trades</div><div class="val">{len(result.trades)}</div></div>
    <div class="stat"><div class="lbl">Open positions</div><div class="val">{len(result.final_holdings)}</div></div>
  </div>

  {portfolio_chart_svg(result.snapshots)}

  <section class="block">
    <h2>💼 Open positions – P&amp;L per ticker</h2>
    <p class="muted" style="margin:0 0 12px;font-size:13px">
      Cumulative gain/loss for each stock still held (cost basis vs current value, plus any prior realized rounds).
    </p>
    {position_cards}
  </section>

  <section class="block">
    <h2>📅 Month by month</h2>
    <div style="overflow:auto">
      <table class="whatif">
        <thead><tr>
          <th>Month</th><th>Weeks</th><th>Invested</th><th>Value</th><th>Return</th><th>MoM change</th>
        </tr></thead>
        <tbody>{month_rows or '<tr><td colspan="6" class="muted">No data</td></tr>'}</tbody>
      </table>
    </div>
  </section>

  <section class="block">
    <h2>📋 Recent trades (last 80)</h2>
    <div style="overflow:auto;max-height:420px">
      <table class="whatif">
        <thead><tr>
          <th>Date</th><th>Action</th><th>Ticker</th><th>Shares</th><th>Price</th>
          <th>Amount</th><th>vs MA</th><th>Reason</th>
        </tr></thead>
        <tbody>{trade_rows or '<tr><td colspan="8" class="muted">No trades</td></tr>'}</tbody>
      </table>
    </div>
  </section>

  {"<section class='block'><h2>📊 Holdings summary</h2><table class='whatif'><thead><tr><th>Ticker</th><th>Shares</th><th>Cost</th><th>Value</th><th>P&amp;L</th></tr></thead><tbody>" + open_rows + "</tbody></table></section>" if open_rows else ""}

  <p class="disclaimer">
    ⚠️ Historical simulation only — not financial advice. Past backtests do not guarantee future results.
    Intended to show whether this repo's moving-average rules would have grown a fixed monthly budget over time.
  </p>

  <footer>StocksMania · <a href="https://github.com/yanivvi/stocksmania" style="color:var(--link)">source</a></footer>
  <script>
    (function () {{
      const KEY = 'stocksmania-theme';
      const saved = localStorage.getItem(KEY);
      const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
      document.documentElement.setAttribute('data-theme', saved || (prefersLight ? 'light' : 'dark'));
      document.getElementById('theme-toggle').addEventListener('click', () => {{
        const cur = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem(KEY, next);
      }});
    }})();
  </script>
</body>
</html>"""


def print_summary(result: SimResult) -> None:
    if not result.snapshots:
        print("No simulation data (need CSV history with 150+ trading days).")
        return
    last = result.snapshots[-1]
    print(f"Period: {result.start_date} → {result.end_date}")
    print(f"Invested: ${result.total_invested:,.2f}")
    print(f"Value:    ${result.final_value:,.2f}")
    print(f"Gain:     ${last.gain:+,.2f} ({last.gain_pct:+.1f}%)")
    print(f"Trades:   {len(result.trades)}")
    if result.monthly:
        print("\nMonthly:")
        for m in result.monthly[-6:]:
            print(
                f"  {m['month']}: ${m['value']:,.0f} "
                f"({m['gain_pct']:+.1f}% vs invested, MoM ${m['month_change']:+,.0f})"
            )


def build_whatif_page(
    out_path: Path | None = None,
    *,
    monthly_budget: float = DEFAULT_MONTHLY_BUDGET,
    top_n: int = DEFAULT_TOP_N,
    data_dir: Path | None = None,
    stocks_file: Path | None = None,
) -> SimResult:
    symbols = read_tickers(stocks_file)
    histories = load_histories(symbols, data_dir)
    result = run_simulation(histories, monthly_budget=monthly_budget, top_n=top_n)
    html = render_html(result, monthly_budget=monthly_budget, top_n=top_n)
    dest = out_path or ROOT / "site" / "what-if.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html)
    print(f"✅ Wrote {dest} ({len(result.snapshots)} weeks, {len(result.trades)} trades)")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="What-if backtest for StocksMania MA strategy")
    parser.add_argument("--monthly", type=float, default=DEFAULT_MONTHLY_BUDGET, help="Monthly $ budget")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Top N BUY picks each week")
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    parser.add_argument("--site", action="store_true", help="Write site/what-if.html")
    args = parser.parse_args()

    symbols = read_tickers()
    histories = load_histories(symbols)
    result = run_simulation(histories, monthly_budget=args.monthly, top_n=args.top)

    if args.site:
        build_whatif_page(monthly_budget=args.monthly, top_n=args.top)
    elif args.json:
        print(
            json.dumps(
                {
                    "total_invested": result.total_invested,
                    "final_value": result.final_value,
                    "gain_pct": result.snapshots[-1].gain_pct if result.snapshots else 0,
                    "trades": len(result.trades),
                    "weeks": len(result.snapshots),
                },
                indent=2,
            )
        )
    else:
        print_summary(result)


if __name__ == "__main__":
    main()
