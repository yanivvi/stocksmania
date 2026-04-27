#!/usr/bin/env python3
"""Build the static GitHub Pages site under ./site.

Generates index.html showing every ticker in stocks.txt with:
  - latest price, daily change, vs 150-day MA, BUY/SELL/HOLD signal
  - data-freshness badge (green <=5d, yellow <=14d, red >14d, gray missing)
  - embedded chart and link to CSV
  - clearly highlighted "ghost tickers" (in stocks.txt, no data)
"""
from __future__ import annotations

import html
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROLLING_WINDOW = 150
BUY_ZONE_MIN, BUY_ZONE_MAX = 0, 15
SELL_BELOW = -10
OVERBOUGHT = 40

ROOT = Path(__file__).parent
SITE = ROOT / "site"
DATA = ROOT / "data"
CHARTS = ROOT / "charts"


def read_tickers() -> list[str]:
    return [
        line.strip()
        for line in (ROOT / "stocks.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def load_metrics(symbol: str) -> dict | None:
    csv = DATA / f"{symbol}_prices.csv"
    if not csv.exists():
        return None
    df = pd.read_csv(csv)
    if len(df) < 2:
        return None
    latest, prev = df.iloc[-1], df.iloc[-2]
    ma_col = f"Rolling_Avg_{ROLLING_WINDOW}d"
    ma = latest.get(ma_col) if ma_col in df.columns else None
    price = float(latest["Close"])
    vs_ma = ((price - ma) / ma * 100) if pd.notna(ma) and ma else None
    return {
        "price": price,
        "prev": float(prev["Close"]),
        "ma": float(ma) if pd.notna(ma) else None,
        "vs_ma": vs_ma,
        "daily_change": (price - float(prev["Close"])) / float(prev["Close"]) * 100,
        "latest_date": pd.to_datetime(latest["Date"]).date(),
        "rows": len(df),
    }


def signal(vs_ma: float | None) -> tuple[str, str]:
    if vs_ma is None:
        return ("HOLD", "no-ma")
    if vs_ma >= OVERBOUGHT or vs_ma <= SELL_BELOW:
        return ("SELL", "sell")
    if BUY_ZONE_MIN <= vs_ma <= BUY_ZONE_MAX:
        return ("BUY", "buy")
    return ("HOLD", "hold")


def freshness(latest: date | None, today: date) -> tuple[str, str]:
    if latest is None:
        return ("missing", "no data")
    age = (today - latest).days
    if age <= 5:
        return ("ok", f"{age}d old")
    if age <= 14:
        return ("warn", f"{age}d old")
    return ("stale", f"{age}d old")


def render(rows: list[dict], today: date) -> str:
    total = len(rows)
    ghosts = sum(1 for r in rows if r["m"] is None)
    stale = sum(1 for r in rows if r["m"] and (today - r["m"]["latest_date"]).days > 5)
    buy = sum(1 for r in rows if r["sig"] == "BUY")
    sell = sum(1 for r in rows if r["sig"] == "SELL")

    cards = []
    for r in rows:
        sym = r["sym"]
        m = r["m"]
        fresh_cls, fresh_lbl = r["fresh"]
        sig_cls = r["sig_cls"]
        sig = r["sig"]
        if m is None:
            body = '<div class="warn-msg">⚠️ No data file. Re-run "Add New Stock" workflow.</div>'
            chart = ""
        else:
            ma_str = f"${m['ma']:.2f}" if m["ma"] else "—"
            vs_ma_str = f"{m['vs_ma']:+.1f}%" if m["vs_ma"] is not None else "—"
            body = f"""
              <div class="grid">
                <div><span class="lbl">Price</span><span class="val">${m['price']:.2f}</span></div>
                <div><span class="lbl">Today</span><span class="val {'up' if m['daily_change']>=0 else 'down'}">{m['daily_change']:+.2f}%</span></div>
                <div><span class="lbl">150d MA</span><span class="val">{ma_str}</span></div>
                <div><span class="lbl">vs MA</span><span class="val">{vs_ma_str}</span></div>
                <div><span class="lbl">Last</span><span class="val">{m['latest_date']}</span></div>
                <div><span class="lbl">Rows</span><span class="val">{m['rows']}</span></div>
              </div>
              <div class="links">
                <a href="data/{sym}_prices.csv">CSV</a>
              </div>
            """
            chart_path = CHARTS / f"{sym}.png"
            chart = (
                f'<img loading="lazy" src="charts/{sym}.png" alt="{sym} chart">'
                if chart_path.exists()
                else ""
            )
        cards.append(f"""
          <article class="card {sig_cls}" id="{sym}">
            <header>
              <h2>{sym}</h2>
              <span class="signal {sig_cls}">{sig}</span>
              <span class="fresh {fresh_cls}" title="data freshness">{fresh_lbl}</span>
            </header>
            {chart}
            {body}
          </article>
        """)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>StocksMania – Status</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
           background: #0d1117; color: #e6edf3; margin: 0; padding: 24px; }}
    h1 {{ margin: 0 0 4px; font-size: 28px; }}
    .sub {{ color: #8b949e; margin-bottom: 16px; }}
    .summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }}
    .pill {{ background: #161b22; border: 1px solid #30363d; border-radius: 999px;
            padding: 6px 14px; font-size: 13px; }}
    .pill b {{ color: #fff; }}
    .pill.bad {{ border-color: #6e2230; background: #2b1418; }}
    .pill.warn {{ border-color: #6b5a1d; background: #2a2410; }}
    .grid-cards {{ display: grid; gap: 16px;
                   grid-template-columns: repeat(auto-fill,minmax(320px,1fr)); }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px;
             padding: 14px; box-shadow: 0 1px 0 rgba(255,255,255,.02); }}
    .card.no-ma {{ border-color: #444; }}
    .card.buy {{ border-color: #2ea043; }}
    .card.sell {{ border-color: #f85149; }}
    .card header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }}
    .card h2 {{ margin: 0; font-size: 18px; flex: 1; }}
    .signal {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px;
               letter-spacing: .04em; }}
    .signal.buy {{ background: #103a1d; color: #56d364; }}
    .signal.sell {{ background: #3a1416; color: #ff7b72; }}
    .signal.hold {{ background: #2a2410; color: #d29922; }}
    .signal.no-ma {{ background: #21262d; color: #8b949e; }}
    .fresh {{ font-size: 11px; padding: 3px 8px; border-radius: 4px; }}
    .fresh.ok {{ background: #103a1d; color: #56d364; }}
    .fresh.warn {{ background: #2a2410; color: #d29922; }}
    .fresh.stale, .fresh.missing {{ background: #3a1416; color: #ff7b72; }}
    .card img {{ width: 100%; border-radius: 6px; background: #fff; margin-bottom: 10px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; font-size: 13px; }}
    .lbl {{ color: #8b949e; margin-right: 6px; }}
    .val {{ color: #e6edf3; font-weight: 600; }}
    .val.up {{ color: #56d364; }} .val.down {{ color: #ff7b72; }}
    .warn-msg {{ color: #ff7b72; padding: 8px 0; }}
    .links {{ margin-top: 8px; font-size: 12px; }}
    .links a {{ color: #58a6ff; text-decoration: none; }}
    footer {{ margin-top: 32px; color: #8b949e; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>📈 StocksMania – Status</h1>
  <div class="sub">Built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC · {today}</div>
  <div class="summary">
    <span class="pill">Tickers <b>{total}</b></span>
    <span class="pill">🟢 BUY <b>{buy}</b></span>
    <span class="pill">🔴 SELL <b>{sell}</b></span>
    <span class="pill {'warn' if stale else ''}">Stale (&gt;5d) <b>{stale}</b></span>
    <span class="pill {'bad' if ghosts else ''}">No data <b>{ghosts}</b></span>
  </div>
  <section class="grid-cards">
    {''.join(cards)}
  </section>
  <footer>
    StocksMania · <a href="https://github.com/yanivvi/stocksmania" style="color:#58a6ff">source</a>
  </footer>
</body>
</html>
"""


def main() -> None:
    today = date.today()
    SITE.mkdir(exist_ok=True)
    # Copy data + charts so the page can link to them.
    for sub in ("data", "charts"):
        src = ROOT / sub
        dst = SITE / sub
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst)

    rows = []
    for sym in read_tickers():
        m = load_metrics(sym)
        sig, sig_cls = signal(m["vs_ma"] if m else None)
        if m is None:
            sig, sig_cls = "NO DATA", "no-ma"
        rows.append({
            "sym": sym,
            "m": m,
            "sig": sig,
            "sig_cls": sig_cls,
            "fresh": freshness(m["latest_date"] if m else None, today),
        })

    # Sort: missing first (most attention), then SELL, then BUY, then by symbol.
    order = {"NO DATA": 0, "SELL": 1, "BUY": 2, "HOLD": 3}
    rows.sort(key=lambda r: (order.get(r["sig"], 9), r["sym"]))

    (SITE / "index.html").write_text(render(rows, today))
    print(f"✅ Wrote {SITE / 'index.html'} with {len(rows)} tickers")


if __name__ == "__main__":
    main()
