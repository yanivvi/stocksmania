"""Tests for the what-if backtest simulator."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from what_if import (
    load_histories,
    prepare_history,
    rank_buy_leaders,
    run_simulation,
    should_exit,
    week_end_dates,
)


def _make_csv(tmp_path, sym: str, closes: list[float], start: date) -> None:
    rows = []
    for i, c in enumerate(closes):
        d = start + timedelta(days=i)
        rows.append({"Date": d.isoformat(), "Close": c, "Symbol": sym})
    df = pd.DataFrame(rows)
    df.to_csv(tmp_path / f"{sym}_prices.csv", index=False)


def test_should_exit_at_ma_and_overbought():
    ok, _ = should_exit(0.0)
    assert ok
    ok, _ = should_exit(-5.0)
    assert ok
    ok, reason = should_exit(40.0)
    assert ok
    assert "overbought" in reason
    ok, _ = should_exit(10.0)
    assert not ok


def test_rank_buy_leaders_picks_highest_score(tmp_path):
    start = date(2024, 1, 1)
    # 200 flat days then uptrend — last rows should be BUY zone.
    flat = [100.0] * 200
    trend = [105.0, 106.0, 107.0, 108.0]
    _make_csv(tmp_path, "AAA", flat + trend, start)
    trend2 = [102.0, 103.0, 104.0, 105.0]
    _make_csv(tmp_path, "BBB", flat + trend2, start)
    histories = load_histories(["AAA", "BBB"], tmp_path)
    on = start + timedelta(days=len(flat + trend) - 1)
    leaders = rank_buy_leaders(histories, on, top_n=2)
    assert leaders
    assert all(sym in ("AAA", "BBB") for sym, _, _ in leaders)


def test_run_simulation_invests_and_grows(tmp_path):
    start = date(2024, 1, 1)
    # Long flat warmup, then steady climb so BUY entries profit before MA exit.
    closes = [50.0] * 200 + [50 + i * 0.5 for i in range(1, 41)]
    _make_csv(tmp_path, "WIN", closes, start)
    histories = load_histories(["WIN"], tmp_path)
    weeks = week_end_dates(histories)
    assert len(weeks) >= 4

    result = run_simulation(
        histories,
        monthly_budget=400.0,
        top_n=1,
        start=weeks[5],
        end=weeks[-1],
    )
    assert result.total_invested > 0
    assert result.trades
    assert any(t.action == "BUY" for t in result.trades)
    assert result.snapshots
    assert result.final_value > 0


def test_prepare_history_adds_signal_column():
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=160, freq="B"),
            "Close": [100.0] * 160,
        }
    )
    out = prepare_history(df)
    assert "vs_ma" in out.columns
    assert "signal" in out.columns
    assert out["signal"].iloc[-1] in ("BUY", "HOLD", "SELL")
