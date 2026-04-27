#!/usr/bin/env python3
"""Data-quality validator + watchdog.

Walks every CSV in data/ and the ticker list in stocks.txt, and reports:
  - tickers missing a CSV ("ghosts")
  - CSVs with stale latest row (> MAX_AGE_DAYS calendar days)
  - CSVs with internal gaps (> 5 calendar days between consecutive rows)
  - CSVs that lost rows compared to the last commit
  - CSVs with NaN in Close

Exit codes:
  0 - all clean
  1 - issues found (workflow should fail)

Usage:
  python validate_data.py                # report + exit non-zero on issues
  python validate_data.py --warn-only    # report only, exit 0
  python validate_data.py --notify       # additionally post to Telegram
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
STOCKS_FILE = ROOT / "stocks.txt"

MAX_AGE_DAYS = 5
INTERNAL_GAP_DAYS = 5
# How many tickers can fail each check before we consider the run unhealthy.
ALERT_GHOST_THRESHOLD = 1
ALERT_STALE_THRESHOLD = 3
ALERT_GAP_THRESHOLD = 1


def read_tickers() -> list[str]:
    return [
        line.strip()
        for line in STOCKS_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def previous_row_count(symbol: str) -> int | None:
    """Row count of this CSV at HEAD~1 (so we can detect data-loss). None if N/A."""
    rel = f"data/{symbol}_prices.csv"
    try:
        out = subprocess.check_output(
            ["git", "show", f"HEAD:{rel}"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        )
    except subprocess.CalledProcessError:
        return None
    # subtract header
    return max(0, len(out.splitlines()) - 1)


def check_one(symbol: str, today: date) -> dict:
    csv = DATA / f"{symbol}_prices.csv"
    if not csv.exists():
        return {"symbol": symbol, "status": "missing"}

    df = pd.read_csv(csv, parse_dates=["Date"])
    issues: list[str] = []

    if df["Close"].isna().any():
        issues.append("nan-close")

    if len(df) < 2:
        issues.append("too-few-rows")
        return {"symbol": symbol, "status": "issue", "issues": issues, "rows": len(df)}

    df = df.sort_values("Date").reset_index(drop=True)
    latest = df["Date"].iloc[-1].date()
    age = (today - latest).days
    if age > MAX_AGE_DAYS:
        issues.append(f"stale:{age}d")

    diffs = df["Date"].diff().dt.days
    big_gaps = diffs[diffs > INTERNAL_GAP_DAYS]
    if not big_gaps.empty:
        issues.append(f"gap:{int(big_gaps.max())}d")

    prev_count = previous_row_count(symbol)
    if prev_count is not None and len(df) < prev_count:
        issues.append(f"shrunk:{prev_count}->{len(df)}")

    return {
        "symbol": symbol,
        "status": "issue" if issues else "ok",
        "issues": issues,
        "rows": len(df),
        "latest": str(latest),
        "age": age,
    }


def summarize(results: list[dict]) -> dict:
    ghosts = [r["symbol"] for r in results if r["status"] == "missing"]
    issues = [r for r in results if r["status"] == "issue"]
    stale = [r for r in issues if any(i.startswith("stale:") for i in r["issues"])]
    gaps = [r for r in issues if any(i.startswith("gap:") for i in r["issues"])]
    shrunk = [r for r in issues if any(i.startswith("shrunk:") for i in r["issues"])]
    nan = [r for r in issues if "nan-close" in r["issues"]]
    return {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "ghosts": ghosts,
        "stale": stale,
        "gaps": gaps,
        "shrunk": shrunk,
        "nan": nan,
    }


def healthy(s: dict) -> bool:
    return (
        len(s["ghosts"]) < ALERT_GHOST_THRESHOLD
        and len(s["stale"]) < ALERT_STALE_THRESHOLD
        and len(s["gaps"]) < ALERT_GAP_THRESHOLD
        and not s["shrunk"]
        and not s["nan"]
    )


def format_message(s: dict) -> str:
    lines = [f"⚠️ <b>StocksMania data validator</b> – {s['ok']}/{s['total']} clean"]
    if s["ghosts"]:
        lines.append(f"❌ No data: {', '.join(s['ghosts'][:10])}")
    if s["stale"]:
        names = ", ".join(f"{r['symbol']}({r['age']}d)" for r in s["stale"][:8])
        lines.append(f"🕒 Stale: {names}")
    if s["gaps"]:
        names = ", ".join(r["symbol"] for r in s["gaps"][:8])
        lines.append(f"🕳️ Gaps: {names}")
    if s["shrunk"]:
        names = ", ".join(r["symbol"] for r in s["shrunk"][:8])
        lines.append(f"📉 Lost rows: {names}")
    if s["nan"]:
        names = ", ".join(r["symbol"] for r in s["nan"][:8])
        lines.append(f"🧨 NaN close: {names}")
    return "\n".join(lines)


def notify_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("(no telegram creds, skipping notify)")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"telegram notify failed: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn-only", action="store_true", help="never exit non-zero")
    ap.add_argument("--notify", action="store_true", help="also post issues to Telegram")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    today = date.today()
    results = [check_one(t, today) for t in read_tickers()]
    summary = summarize(results)

    if args.json:
        print(json.dumps({"summary": summary, "results": results}, default=str, indent=2))
    else:
        print(f"validated {summary['total']} tickers — {summary['ok']} clean")
        for r in results:
            if r["status"] != "ok":
                print(f"  {r['symbol']:<6} {r['status']:<7} {r.get('issues', [])}")

    is_healthy = healthy(summary)
    if not is_healthy:
        msg = format_message(summary)
        print("\n" + msg)
        if args.notify:
            notify_telegram(msg)

    if is_healthy or args.warn_only:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
