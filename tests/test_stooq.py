"""Tests for StockFetcher._fetch_stooq response handling."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd


class _Resp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status


def test_stooq_html_response_returns_empty(fetcher):
    """Stooq sometimes returns an HTML error page; we must not feed it to pandas."""
    with patch("stock_fetcher.requests.get", return_value=_Resp("<html>nope</html>")):
        df = fetcher._fetch_stooq("FAKE", date(2025, 1, 1), date(2025, 1, 5))
    assert df.empty


def test_stooq_no_data_body_returns_empty(fetcher):
    with patch("stock_fetcher.requests.get", return_value=_Resp("No data\n")):
        df = fetcher._fetch_stooq("FAKE", date(2025, 1, 1), date(2025, 1, 5))
    assert df.empty


def test_stooq_non_200_returns_empty(fetcher):
    with patch("stock_fetcher.requests.get", return_value=_Resp("whatever", status=503)):
        df = fetcher._fetch_stooq("FAKE", date(2025, 1, 1), date(2025, 1, 5))
    assert df.empty


def test_stooq_valid_csv_parsed(fetcher):
    csv = (
        "Date,Open,High,Low,Close,Volume\n"
        "2025-01-02,100,101,99,100.5,1000\n"
        "2025-01-03,101,103,100,102.0,2000\n"
    )
    with patch("stock_fetcher.requests.get", return_value=_Resp(csv)):
        df = fetcher._fetch_stooq("AAA", date(2025, 1, 1), date(2025, 1, 5))
    assert list(df.columns) == ["Date", "Close"]
    assert len(df) == 2
    assert df["Close"].tolist() == [100.5, 102.0]
    assert isinstance(df["Date"].iloc[0], pd.Timestamp.__base__) or hasattr(df["Date"].iloc[0], "year")
