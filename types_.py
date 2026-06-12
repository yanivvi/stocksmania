"""Shared TypedDicts so the per-ticker structures aren't bare dicts."""
from __future__ import annotations

from datetime import date
from typing import Literal, TypedDict

SignalLabel = Literal["BUY", "SELL", "HOLD", "NO DATA"]
SignalCls = Literal["buy", "sell", "hold", "no-ma"]


class StockMetrics(TypedDict):
    """Computed metrics from a single ticker's CSV."""

    price: float
    prev: float
    ma: float | None
    vs_ma: float | None
    daily_change: float
    latest_date: date
    rows: int


class TickerRow(TypedDict, total=False):
    """One entry per ticker for the status site."""

    sym: str
    m: StockMetrics | None
    sig: SignalLabel
    sig_cls: SignalCls
    fresh: tuple[str, str]


class FetchMetric(TypedDict):
    """One row written to logs/fetch_metrics.jsonl per provider call."""

    ts: str
    symbol: str
    provider: str
    ok: bool
    ms: int
