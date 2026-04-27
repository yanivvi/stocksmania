"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable so tests can `from stock_fetcher import ...`.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402

from config import StockConfig  # noqa: E402
from stock_fetcher import StockFetcher  # noqa: E402


@pytest.fixture
def fetcher(tmp_path, monkeypatch):
    """A StockFetcher whose data_dir is an isolated tmp dir."""
    cfg = StockConfig(symbols=["TEST"], rolling_window=5)
    cfg.data_dir = str(tmp_path)
    return StockFetcher(cfg)
