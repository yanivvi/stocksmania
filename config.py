"""Configuration for stock tracker."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class StockConfig:
    """Configuration for stock tracking."""
    
    # List of stock symbols to track
    symbols: list[str] = field(default_factory=lambda: ["NVDA"])
    
    # Rolling average window in days
    rolling_window: int = 150
    
    # Default start date for historical data
    historical_start: date = field(default_factory=lambda: date(2025, 1, 1))
    
    # Data storage path
    data_dir: str = "data"


# Default configuration
DEFAULT_CONFIG = StockConfig()
