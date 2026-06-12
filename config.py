"""Configuration for stock tracker."""

from dataclasses import dataclass, field
from datetime import date

# === Signal thresholds (single source of truth) ============================
# Used by telegram_notify.py, build_site.py, validate_data.py.
ROLLING_WINDOW = 150          # days; the moving average window
BUY_ZONE_MIN = 0              # vs-MA % lower bound for BUY
BUY_ZONE_MAX = 15             # vs-MA % upper bound for BUY
SELL_BELOW = -10              # vs-MA % at or below which we SELL (downtrend)
OVERBOUGHT = 40               # vs-MA % at or above which we SELL (take profits)

# === Data freshness thresholds ============================================
FRESH_OK_DAYS = 5             # <=5d old: green
FRESH_WARN_DAYS = 14          # <=14d old: yellow; otherwise red
INTERNAL_GAP_DAYS = 5         # >5d between consecutive rows = a gap


@dataclass
class StockConfig:
    """Configuration for stock tracking."""

    symbols: list[str] = field(default_factory=lambda: ["NVDA"])
    rolling_window: int = ROLLING_WINDOW
    historical_start: date = field(default_factory=lambda: date(2025, 1, 1))
    data_dir: str = "data"


DEFAULT_CONFIG = StockConfig()
