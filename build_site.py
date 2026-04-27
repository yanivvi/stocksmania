#!/usr/bin/env python3
"""Build the static GitHub Pages site under ./site.

Generates index.html showing every ticker in stocks.txt with:
  - latest price, daily change, vs 150-day MA, BUY/SELL/HOLD signal
  - data-freshness badge (green <=5d, yellow <=14d, red >14d, gray missing)
  - embedded chart and link to CSV
  - clearly highlighted "ghost tickers" (in stocks.txt, no data)
  - top 3 / bottom 3 recap, multi-select filters by ticker and status
  - buttons that deep-link to the GitHub Actions run pages
"""
from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

ROLLING_WINDOW = 150
BUY_ZONE_MIN, BUY_ZONE_MAX = 0, 15
SELL_BELOW = -10
OVERBOUGHT = 40

REPO_URL = "https://github.com/yanivvi/stocksmania"
DAILY_WF_URL = f"{REPO_URL}/actions/workflows/daily_update.yml"
ADD_WF_URL = f"{REPO_URL}/actions/workflows/add_stock.yml"
BACKFILL_WF_URL = f"{REPO_URL}/actions/workflows/backfill.yml"

ROOT = Path(__file__).parent
SITE = ROOT / "site"
DATA = ROOT / "data"
CHARTS = ROOT / "charts"


SITE_CSS = """\
:root {
  --bg: #0d1117; --surface: #161b22; --surface-2: #0d1117;
  --border: #30363d; --text: #e6edf3; --muted: #8b949e;
  --green: #56d364; --green-bg: #103a1d;
  --red: #ff7b72; --red-bg: #3a1416;
  --amber: #d29922; --amber-bg: #2a2410;
  --link: #58a6ff;
  color-scheme: dark;
}
[data-theme="light"] {
  --bg: #f6f8fa; --surface: #ffffff; --surface-2: #f0f3f6;
  --border: #d0d7de; --text: #1f2328; --muted: #57606a;
  --green: #1a7f37; --green-bg: #dafbe1;
  --red: #cf222e; --red-bg: #ffebe9;
  --amber: #9a6700; --amber-bg: #fff8c5;
  --link: #0969da;
  color-scheme: light;
}
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text); margin: 0; padding: 24px;
  transition: background .2s, color .2s; }
@media (max-width: 600px) { body { padding: 14px; } }
h1 { margin: 0 0 4px; font-size: 28px; }
.sub { color: var(--muted); margin-bottom: 16px; }
.topbar { display: flex; align-items: flex-start; gap: 12px;
  justify-content: space-between; flex-wrap: wrap; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.btn { display: inline-flex; align-items: center; gap: 6px;
  background: #238636; color: #fff; border: 1px solid #2ea043;
  padding: 8px 14px; border-radius: 6px; font-weight: 600;
  text-decoration: none; font-size: 13px; cursor: pointer; }
.btn:hover { background: #2ea043; }
.btn.secondary { background: var(--surface); border-color: var(--border); color: var(--text); }
.btn.secondary:hover { background: var(--surface-2); }
.theme-toggle { background: var(--surface); border: 1px solid var(--border);
  color: var(--text); padding: 6px 10px; border-radius: 6px;
  font-size: 13px; cursor: pointer; }
.summary { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
.pill { background: var(--surface); border: 1px solid var(--border); border-radius: 999px;
  padding: 6px 14px; font-size: 13px; }
.pill b { color: var(--text); }
.pill.bad { border-color: var(--red); background: var(--red-bg); }
.pill.warn { border-color: var(--amber); background: var(--amber-bg); }
.recap { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
@media (max-width: 700px) { .recap { grid-template-columns: 1fr; } }
.recap-box { background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px; }
.recap-box h3 { margin: 0 0 8px; font-size: 14px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .06em; }
.recap-box.up { border-color: var(--green); }
.recap-box.down { border-color: var(--red); }
.mini { display: inline-flex; align-items: center; gap: 8px; margin: 0 6px 6px 0;
  padding: 4px 10px; background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 999px; font-size: 13px; text-decoration: none; color: var(--text); }
.mini b { color: var(--text); }
.mini .up { color: var(--green); } .mini .down { color: var(--red); }
.mini:hover { border-color: var(--link); }
.filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 14px; margin-bottom: 20px; }
.filters label { display: flex; flex-direction: column; gap: 4px; font-size: 12px;
  color: var(--muted); }
.filters select { background: var(--surface-2); color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 8px; min-width: 180px;
  font-size: 13px; }
.filters select[multiple] { height: 90px; }
.filters .hint { font-size: 11px; color: var(--muted); }
#count { color: var(--muted); font-size: 13px; margin-left: auto; }
.grid-cards { display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fill,minmax(320px,1fr)); }
@media (max-width: 600px) { .grid-cards { grid-template-columns: 1fr; } }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; }
.card.no-ma { border-color: var(--border); }
.card.buy { border-color: var(--green); }
.card.sell { border-color: var(--red); }
.card.hidden { display: none; }
.card header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.card h2 { margin: 0; font-size: 18px; flex: 1; }
.card h2 a { color: inherit; text-decoration: none; }
.card h2 a:hover { color: var(--link); }
.signal { font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px;
  letter-spacing: .04em; }
.signal.buy { background: var(--green-bg); color: var(--green); }
.signal.sell { background: var(--red-bg); color: var(--red); }
.signal.hold { background: var(--amber-bg); color: var(--amber); }
.signal.no-ma { background: var(--surface-2); color: var(--muted); }
.fresh { font-size: 11px; padding: 3px 8px; border-radius: 4px; }
.fresh.ok { background: var(--green-bg); color: var(--green); }
.fresh.warn { background: var(--amber-bg); color: var(--amber); }
.fresh.stale, .fresh.missing { background: var(--red-bg); color: var(--red); }
.card img { width: 100%; border-radius: 6px; background: #fff; margin-bottom: 10px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; font-size: 13px; }
.lbl { color: var(--muted); margin-right: 6px; }
.val { color: var(--text); font-weight: 600; }
.val.up { color: var(--green); } .val.down { color: var(--red); }
.warn-msg { color: var(--red); padding: 8px 0; }
.links { margin-top: 8px; font-size: 12px; }
.links a { color: var(--link); text-decoration: none; }
.muted { color: var(--muted); }
footer { margin-top: 32px; color: var(--muted); font-size: 12px; }
"""


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


def render_detail_page(symbol: str, df: pd.DataFrame | None, m: dict | None,
                        sig: str, sig_cls: str) -> str:
    """A per-ticker page at site/t/<SYMBOL>.html."""
    title = f"{symbol} – StocksMania"
    if df is None or m is None:
        body = '<p class="warn-msg">⚠️ No data available for this ticker yet.</p>'
        head_extra = ""
    else:
        ma_col = f"Rolling_Avg_{ROLLING_WINDOW}d"
        # Last 60 rows in reverse chronological order.
        recent = df.tail(60).iloc[::-1]
        rows_html = "".join(
            f"<tr><td>{r['Date'].date() if hasattr(r['Date'],'date') else r['Date']}</td>"
            f"<td>${float(r['Close']):.2f}</td>"
            f"<td>{('$' + format(float(r[ma_col]), '.2f')) if ma_col in r and pd.notna(r[ma_col]) else '—'}</td></tr>"
            for _, r in recent.iterrows()
        )
        # Stats
        all_high = float(df['Close'].max())
        all_low = float(df['Close'].min())
        drawdown = (m["price"] - all_high) / all_high * 100 if all_high else 0
        ytd_start = df[df['Close'].notna()].iloc[0]['Close']
        ytd_pct = (m["price"] - float(ytd_start)) / float(ytd_start) * 100
        head_extra = ""
        body = f"""
        <section class="card {sig_cls}" style="margin-bottom:16px">
          <header>
            <h2>{symbol}</h2>
            <span class="signal {sig_cls}">{sig}</span>
          </header>
          <img src="../charts/{symbol}.png" alt="{symbol} chart">
          <div class="grid">
            <div><span class="lbl">Price</span><span class="val">${m['price']:.2f}</span></div>
            <div><span class="lbl">Today</span><span class="val {'up' if m['daily_change']>=0 else 'down'}">{m['daily_change']:+.2f}%</span></div>
            <div><span class="lbl">150d MA</span><span class="val">{('$' + format(m['ma'], '.2f')) if m['ma'] else '—'}</span></div>
            <div><span class="lbl">vs MA</span><span class="val">{(format(m['vs_ma'], '+.1f') + '%') if m['vs_ma'] is not None else '—'}</span></div>
            <div><span class="lbl">Last</span><span class="val">{m['latest_date']}</span></div>
            <div><span class="lbl">Rows</span><span class="val">{m['rows']}</span></div>
            <div><span class="lbl">All-time high</span><span class="val">${all_high:.2f}</span></div>
            <div><span class="lbl">All-time low</span><span class="val">${all_low:.2f}</span></div>
            <div><span class="lbl">From ATH</span><span class="val {'up' if drawdown>=0 else 'down'}">{drawdown:+.1f}%</span></div>
            <div><span class="lbl">Since start</span><span class="val {'up' if ytd_pct>=0 else 'down'}">{ytd_pct:+.1f}%</span></div>
          </div>
          <div class="links" style="margin-top:12px">
            <a href="../data/{symbol}_prices.csv">CSV</a>
          </div>
        </section>

        <section class="card">
          <header><h2 style="font-size:15px">Recent prices (last 60)</h2></header>
          <div style="overflow:auto;max-height:520px">
            <table style="width:100%;border-collapse:collapse;font-size:13px">
              <thead>
                <tr style="text-align:left;color:var(--muted)">
                  <th style="padding:6px 8px">Date</th>
                  <th style="padding:6px 8px">Close</th>
                  <th style="padding:6px 8px">150d MA</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </section>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  {head_extra}
  <link rel="stylesheet" href="../assets/site.css">
</head>
<body>
  <div class="topbar">
    <div>
      <a href="../" style="color:var(--link);text-decoration:none;font-size:13px">← All tickers</a>
      <h1 style="margin-top:6px">{symbol}</h1>
    </div>
    <button class="theme-toggle" id="theme-toggle" type="button" title="Toggle light/dark">🌗 Theme</button>
  </div>
  {body}
  <footer>StocksMania · <a href="{REPO_URL}" style="color:var(--link)">source</a></footer>
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
</html>
"""


def card_html(r: dict) -> str:
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
            if chart_path.exists() else ""
        )
    return f"""
      <article class="card {sig_cls}" data-symbol="{sym}" data-status="{sig}" id="{sym}">
        <header>
          <h2><a href="t/{sym}.html">{sym}</a></h2>
          <span class="signal {sig_cls}">{sig}</span>
          <span class="fresh {fresh_cls}" title="data freshness">{fresh_lbl}</span>
        </header>
        {chart}
        {body}
      </article>"""


def mini_row(r: dict) -> str:
    """Compact row for the top/bottom recap."""
    sym = r["sym"]
    m = r["m"]
    if not m:
        return f'<a class="mini" href="#{sym}"><b>{sym}</b><span class="muted">no data</span></a>'
    vs = m["vs_ma"]
    vs_str = f"{vs:+.1f}%" if vs is not None else "—"
    cls = "up" if (vs is not None and vs >= 0) else "down"
    return (
        f'<a class="mini" href="#{sym}">'
        f'<b>{sym}</b>'
        f'<span>${m["price"]:.2f}</span>'
        f'<span class="{cls}">{vs_str}</span>'
        f'</a>'
    )


def render(rows: list[dict], today: date) -> str:
    total = len(rows)
    ghosts = sum(1 for r in rows if r["m"] is None)
    stale = sum(1 for r in rows if r["m"] and (today - r["m"]["latest_date"]).days > 5)
    buy = sum(1 for r in rows if r["sig"] == "BUY")
    sell = sum(1 for r in rows if r["sig"] == "SELL")

    # Top/Bottom 3 by vs_ma (only rows with metrics).
    with_ma = [r for r in rows if r["m"] and r["m"]["vs_ma"] is not None]
    top3 = sorted(with_ma, key=lambda r: r["m"]["vs_ma"], reverse=True)[:3]
    bot3 = sorted(with_ma, key=lambda r: r["m"]["vs_ma"])[:3]

    cards_html = "\n".join(card_html(r) for r in rows)
    top_html = "".join(mini_row(r) for r in top3) or '<span class="muted">—</span>'
    bot_html = "".join(mini_row(r) for r in bot3) or '<span class="muted">—</span>'

    all_symbols = sorted({r["sym"] for r in rows})
    statuses = ["BUY", "SELL", "HOLD", "NO DATA"]

    sym_options = "".join(f'<option value="{s}">{s}</option>' for s in all_symbols)
    status_options = "".join(f'<option value="{s}">{s}</option>' for s in statuses)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>StocksMania – Status</title>
  <link rel="stylesheet" href="assets/site.css">
</head>
<body>
  <div class="topbar">
    <div>
      <h1>📈 StocksMania – Status</h1>
      <div class="sub">Built {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC · {today}</div>
    </div>
    <button class="theme-toggle" id="theme-toggle" type="button" title="Toggle light/dark">🌗 Theme</button>
  </div>

  <div class="toolbar">
    <a class="btn" href="{DAILY_WF_URL}" target="_blank" rel="noopener" title="Opens GitHub – click 'Run workflow'">
      🔄 Refresh data
    </a>
    <a class="btn secondary" href="{ADD_WF_URL}" target="_blank" rel="noopener" title="Opens GitHub – fill in ticker(s) and click 'Run workflow'">
      ➕ Add ticker
    </a>
    <a class="btn secondary" href="{BACKFILL_WF_URL}" target="_blank" rel="noopener" title="Refetch full history (overwrites CSVs). Use 'all' or specific tickers.">
      🩹 Backfill
    </a>
  </div>

  <div class="summary">
    <span class="pill">Tickers <b>{total}</b></span>
    <span class="pill">🟢 BUY <b>{buy}</b></span>
    <span class="pill">🔴 SELL <b>{sell}</b></span>
    <span class="pill {'warn' if stale else ''}">Stale (&gt;5d) <b>{stale}</b></span>
    <span class="pill {'bad' if ghosts else ''}">No data <b>{ghosts}</b></span>
  </div>

  <div class="recap">
    <div class="recap-box up">
      <h3>🚀 Top 3 (highest vs MA)</h3>
      {top_html}
    </div>
    <div class="recap-box down">
      <h3>📉 Bottom 3 (lowest vs MA)</h3>
      {bot_html}
    </div>
  </div>

  <div class="filters">
    <label>
      Ticker <span class="hint">(Ctrl/Cmd-click for multi)</span>
      <select id="f-ticker" multiple size="4">{sym_options}</select>
    </label>
    <label>
      Status <span class="hint">(Ctrl/Cmd-click for multi)</span>
      <select id="f-status" multiple size="4">{status_options}</select>
    </label>
    <button class="btn secondary" id="f-clear" type="button">Clear filters</button>
    <span id="count"></span>
  </div>

  <section class="grid-cards" id="cards">
    {cards_html}
  </section>

  <footer>
    StocksMania · <a href="{REPO_URL}" style="color:#58a6ff">source</a>
  </footer>

  <script>
    // Theme toggle: persisted in localStorage, defaults to OS preference.
    (function () {{
      const KEY = 'stocksmania-theme';
      const saved = localStorage.getItem(KEY);
      const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
      const initial = saved || (prefersLight ? 'light' : 'dark');
      document.documentElement.setAttribute('data-theme', initial);
      document.getElementById('theme-toggle').addEventListener('click', () => {{
        const cur = document.documentElement.getAttribute('data-theme') || 'dark';
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem(KEY, next);
      }});
    }})();

    (function () {{
      const tickerSel = document.getElementById('f-ticker');
      const statusSel = document.getElementById('f-status');
      const clearBtn  = document.getElementById('f-clear');
      const countEl   = document.getElementById('count');
      const cards     = Array.from(document.querySelectorAll('#cards .card'));

      function selected(sel) {{
        return Array.from(sel.selectedOptions).map(o => o.value);
      }}
      function apply() {{
        const ts = selected(tickerSel);
        const ss = selected(statusSel);
        let visible = 0;
        for (const c of cards) {{
          const ok = (ts.length === 0 || ts.includes(c.dataset.symbol)) &&
                     (ss.length === 0 || ss.includes(c.dataset.status));
          c.classList.toggle('hidden', !ok);
          if (ok) visible++;
        }}
        countEl.textContent = `Showing ${{visible}} of ${{cards.length}}`;
      }}
      tickerSel.addEventListener('change', apply);
      statusSel.addEventListener('change', apply);
      clearBtn.addEventListener('click', () => {{
        for (const o of tickerSel.options) o.selected = false;
        for (const o of statusSel.options) o.selected = false;
        apply();
      }});
      apply();
    }})();
  </script>
</body>
</html>
"""


def main() -> None:
    today = date.today()
    SITE.mkdir(exist_ok=True)
    for sub in ("data", "charts"):
        src = ROOT / sub
        dst = SITE / sub
        if dst.exists():
            shutil.rmtree(dst)
        if src.exists():
            shutil.copytree(src, dst)

    # Shared stylesheet for index + detail pages.
    (SITE / "assets").mkdir(exist_ok=True)
    (SITE / "assets" / "site.css").write_text(SITE_CSS)

    # Per-ticker detail pages.
    detail_dir = SITE / "t"
    detail_dir.mkdir(exist_ok=True)

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

        # Generate detail page.
        df = None
        csv = DATA / f"{sym}_prices.csv"
        if csv.exists():
            try:
                df = pd.read_csv(csv, parse_dates=["Date"])
            except Exception as e:
                print(f"⚠️  detail page: failed to load {sym}: {e}")
        (detail_dir / f"{sym}.html").write_text(render_detail_page(sym, df, m, sig, sig_cls))

    # Order: BUY first, SELL next, then HOLD, then NO DATA. Within group: by symbol.
    order = {"BUY": 0, "SELL": 1, "HOLD": 2, "NO DATA": 3}
    rows.sort(key=lambda r: (order.get(r["sig"], 9), r["sym"]))

    (SITE / "index.html").write_text(render(rows, today))
    print(f"✅ Wrote {SITE / 'index.html'} + {len(rows)} detail pages")


if __name__ == "__main__":
    main()
