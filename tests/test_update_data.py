"""Tests for update_data gap detection / backfill."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd


def _write_csv(fetcher, symbol: str, dates: list[date], closes: list[float]) -> None:
    df = pd.DataFrame({"Date": dates, "Close": closes, "Symbol": symbol})
    df["Rolling_Avg_5d"] = df["Close"].rolling(5, min_periods=5).mean()
    df.to_csv(fetcher._get_data_path(symbol), index=False)


def test_internal_gap_triggers_backfill_from_gap_start(fetcher):
    today = date.today()
    dates = [today - timedelta(days=40), today - timedelta(days=39),
             today - timedelta(days=2), today - timedelta(days=1)]
    closes = [10.0, 11.0, 20.0, 21.0]
    _write_csv(fetcher, "AAA", dates, closes)

    captured = {}

    def fake_download(symbol, start, end, max_retries=2):
        captured["start"] = start
        captured["end"] = end
        # Return one row inside the gap.
        return pd.DataFrame({"Date": [today - timedelta(days=20)], "Close": [15.0]})

    with patch.object(fetcher, "_download_with_retry", side_effect=fake_download):
        out = fetcher.update_data("AAA")

    # Backfill should start the day after the row preceding the gap (today-39).
    assert captured["start"] == today - timedelta(days=38)
    assert captured["end"] == today
    # New row was appended.
    assert (today - timedelta(days=20)) in set(out["Date"])


def test_no_gap_uses_fetch_latest(fetcher):
    today = date.today()
    # Daily contiguous data (skipping weekends) up through yesterday.
    dates = [today - timedelta(days=i) for i in range(5, 0, -1)]
    closes = [100.0 + i for i in range(5)]
    _write_csv(fetcher, "BBB", dates, closes)

    with patch.object(fetcher, "fetch_latest") as latest, \
         patch.object(fetcher, "_download_with_retry") as bulk:
        latest.return_value = pd.DataFrame({"Date": [today], "Close": [200.0], "Symbol": ["BBB"]})
        bulk.return_value = pd.DataFrame()
        out = fetcher.update_data("BBB")

    bulk.assert_not_called()
    latest.assert_called_once()
    assert today in set(out["Date"])


def test_empty_existing_does_full_initial(fetcher):
    """No CSV → falls back to fetch_historical."""
    with patch.object(fetcher, "fetch_historical") as fh:
        fh.return_value = pd.DataFrame()
        out = fetcher.update_data("CCC")
    fh.assert_called_once()
    assert out.empty
