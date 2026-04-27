"""Tests for the signal classifier in build_site."""
from __future__ import annotations

from datetime import date, timedelta

from build_site import freshness, signal


def test_signal_buy_zone():
    assert signal(0)[0] == "BUY"
    assert signal(15)[0] == "BUY"
    assert signal(7.5)[0] == "BUY"


def test_signal_overbought_is_sell():
    assert signal(40)[0] == "SELL"
    assert signal(80)[0] == "SELL"


def test_signal_oversold_is_sell():
    assert signal(-10)[0] == "SELL"
    assert signal(-25)[0] == "SELL"


def test_signal_hold_band():
    assert signal(20)[0] == "HOLD"
    assert signal(-5)[0] == "HOLD"


def test_signal_none_is_hold():
    s, cls = signal(None)
    assert s == "HOLD"
    assert cls == "no-ma"


def test_freshness_levels():
    today = date(2026, 4, 27)
    assert freshness(today, today)[0] == "ok"
    assert freshness(today - timedelta(days=5), today)[0] == "ok"
    assert freshness(today - timedelta(days=10), today)[0] == "warn"
    assert freshness(today - timedelta(days=20), today)[0] == "stale"
    assert freshness(None, today)[0] == "missing"
