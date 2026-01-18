"""Stock data providers - supports multiple APIs."""

import time
from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Optional
import requests
import pandas as pd


class DataProvider(ABC):
    """Abstract base class for stock data providers."""
    
    @abstractmethod
    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch stock data for a symbol."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass


class YahooFinanceProvider(DataProvider):
    """Yahoo Finance provider using yfinance."""
    
    @property
    def name(self) -> str:
        return "Yahoo Finance"
    
    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf
        
        try:
            df = yf.download(
                symbol,
                start=start,
                end=end + timedelta(days=1),
                progress=False,
                timeout=30
            )
            if df.empty:
                return pd.DataFrame()
            
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
            df = df[['Date', 'Close']].copy()
            df['Date'] = pd.to_datetime(df['Date']).dt.date
            return df
        except Exception as e:
            print(f"Yahoo Finance error: {e}")
            return pd.DataFrame()


class AlphaVantageProvider(DataProvider):
    """Alpha Vantage provider - more reliable, requires free API key."""
    
    def __init__(self, api_key: str = "demo"):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
    
    @property
    def name(self) -> str:
        return "Alpha Vantage"
    
    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": self.api_key,
            "outputsize": "full",  # Get all available data
            "datatype": "json"
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            data = response.json()
            
            if "Time Series (Daily)" not in data:
                error = data.get("Note", data.get("Error Message", "Unknown error"))
                print(f"Alpha Vantage error: {error}")
                return pd.DataFrame()
            
            time_series = data["Time Series (Daily)"]
            
            records = []
            for date_str, values in time_series.items():
                record_date = date.fromisoformat(date_str)
                if start <= record_date <= end:
                    records.append({
                        "Date": record_date,
                        "Close": float(values["4. close"])
                    })
            
            if not records:
                return pd.DataFrame()
            
            df = pd.DataFrame(records)
            df = df.sort_values("Date").reset_index(drop=True)
            return df
            
        except Exception as e:
            print(f"Alpha Vantage error: {e}")
            return pd.DataFrame()


class FMPProvider(DataProvider):
    """Financial Modeling Prep - free tier available."""
    
    def __init__(self, api_key: str = "demo"):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/api/v3"
    
    @property
    def name(self) -> str:
        return "Financial Modeling Prep"
    
    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        url = f"{self.base_url}/historical-price-full/{symbol}"
        params = {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "apikey": self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if "historical" not in data:
                print(f"FMP error: No data returned")
                return pd.DataFrame()
            
            records = []
            for item in data["historical"]:
                records.append({
                    "Date": date.fromisoformat(item["date"]),
                    "Close": float(item["close"])
                })
            
            if not records:
                return pd.DataFrame()
            
            df = pd.DataFrame(records)
            df = df.sort_values("Date").reset_index(drop=True)
            return df
            
        except Exception as e:
            print(f"FMP error: {e}")
            return pd.DataFrame()


class MultiProvider:
    """Tries multiple providers with fallback."""
    
    def __init__(self, providers: list[DataProvider]):
        self.providers = providers
    
    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        for provider in self.providers:
            print(f"   Trying {provider.name}...")
            df = provider.fetch(symbol, start, end)
            if not df.empty:
                print(f"   ✅ Success with {provider.name}")
                return df
            time.sleep(1)  # Be nice to APIs
        
        print(f"   ❌ All providers failed")
        return pd.DataFrame()


def get_default_provider(api_key: Optional[str] = None) -> DataProvider:
    """Get the default provider based on available API keys."""
    if api_key:
        return AlphaVantageProvider(api_key)
    return YahooFinanceProvider()


def get_multi_provider(alpha_vantage_key: Optional[str] = None) -> MultiProvider:
    """Get a multi-provider that tries multiple sources."""
    providers = [YahooFinanceProvider()]
    
    if alpha_vantage_key:
        # Alpha Vantage first if we have a key
        providers.insert(0, AlphaVantageProvider(alpha_vantage_key))
    
    return MultiProvider(providers)
