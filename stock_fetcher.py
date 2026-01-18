"""Stock data fetcher using multiple providers."""

import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from config import StockConfig, DEFAULT_CONFIG


class StockFetcher:
    """Fetches and manages stock price data with rolling averages."""
    
    def __init__(self, config: StockConfig = DEFAULT_CONFIG, api_key: Optional[str] = None):
        self.config = config
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.api_key = api_key or os.environ.get("ALPHA_VANTAGE_API_KEY")
    
    def _get_data_path(self, symbol: str) -> Path:
        """Get the CSV path for a stock symbol."""
        return self.data_dir / f"{symbol.upper()}_prices.csv"
    
    def _fetch_stooq(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch data from Stooq - free, full history."""
        # Stooq uses .US suffix for US stocks
        stooq_symbol = f"{symbol}.US"
        url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&d1={start.strftime('%Y%m%d')}&d2={end.strftime('%Y%m%d')}&i=d"
        
        try:
            df = pd.read_csv(url)
            if df.empty or 'Close' not in df.columns:
                return pd.DataFrame()
            
            df = df[['Date', 'Close']].copy()
            df['Date'] = pd.to_datetime(df['Date']).dt.date
            df = df.sort_values('Date').reset_index(drop=True)
            return df
        except Exception as e:
            print(f"⚠️  Stooq error: {e}")
            return pd.DataFrame()
    
    def _fetch_alpha_vantage(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch data from Alpha Vantage API."""
        if not self.api_key:
            return pd.DataFrame()
        
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": self.api_key,
            "outputsize": "compact",  # Free tier: last 100 days
            "datatype": "json"
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            data = response.json()
            
            if "Time Series (Daily)" not in data:
                error = data.get("Note", data.get("Information", data.get("Error Message", "Unknown error")))
                if "rate limit" in str(error).lower() or "25 requests" in str(error).lower():
                    print(f"⚠️  Alpha Vantage rate limit reached (25/day free)")
                else:
                    print(f"⚠️  Alpha Vantage: {error[:80]}...")
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
            print(f"⚠️  Alpha Vantage error: {e}")
            return pd.DataFrame()
    
    def _fetch_yahoo(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch data from Yahoo Finance."""
        try:
            import yfinance as yf
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
            print(f"⚠️  Yahoo Finance error: {str(e)[:60]}...")
            return pd.DataFrame()
    
    def _download_with_retry(self, symbol: str, start: date, end: date, 
                              max_retries: int = 2) -> pd.DataFrame:
        """Download stock data trying multiple providers."""
        # Try Stooq first - free and has full history
        print(f"   Trying Stooq...")
        df = self._fetch_stooq(symbol, start, end)
        if not df.empty:
            print(f"   ✅ Got {len(df)} days from Stooq")
            return df
        
        # Try Alpha Vantage if we have an API key
        if self.api_key:
            print(f"   Trying Alpha Vantage...")
            df = self._fetch_alpha_vantage(symbol, start, end)
            if not df.empty:
                print(f"   ✅ Got data from Alpha Vantage")
                return df
            time.sleep(1)  # Rate limiting
        
        # Fall back to Yahoo Finance
        print(f"   Trying Yahoo Finance...")
        for attempt in range(max_retries):
            df = self._fetch_yahoo(symbol, start, end)
            if not df.empty:
                print(f"   ✅ Got data from Yahoo Finance")
                return df
            if attempt < max_retries - 1:
                time.sleep(2)
        
        return pd.DataFrame()
    
    def fetch_historical(self, symbol: str, start_date: date | None = None, 
                         end_date: date | None = None) -> pd.DataFrame:
        """
        Fetch historical stock data from start_date to end_date.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'NVDA')
            start_date: Start date for data (defaults to config.historical_start)
            end_date: End date for data (defaults to today)
            
        Returns:
            DataFrame with Date, Close, and Rolling_Avg columns
        """
        start = start_date or self.config.historical_start
        end = end_date or date.today()
        
        print(f"📈 Fetching {symbol} data from {start} to {end}...")
        
        df = self._download_with_retry(symbol, start, end)
        
        if df.empty:
            print(f"⚠️  No data found for {symbol}")
            return pd.DataFrame()
        
        # Clean up the dataframe
        df = df.reset_index()
        # Handle multi-level columns from yf.download
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df = df[['Date', 'Close']].copy()
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        df['Symbol'] = symbol.upper()
        
        # Calculate rolling average
        df = self._add_rolling_average(df)
        
        return df
    
    def fetch_latest(self, symbol: str) -> pd.DataFrame:
        """
        Fetch the latest day's data for a stock.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            DataFrame with the latest day's data
        """
        # Fetch last 7 days to ensure we get the most recent trading day
        end = date.today()
        start = end - timedelta(days=7)
        
        print(f"📊 Fetching latest {symbol} data...")
        
        df = self._download_with_retry(symbol, start, end, max_retries=2)
        
        if df.empty:
            print(f"⚠️  No recent data found for {symbol}")
            return pd.DataFrame()
        
        # Clean up and get only the last row (most recent day)
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
        df = df.tail(1)
        df = df[['Date', 'Close']].copy()
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        df['Symbol'] = symbol.upper()
        
        return df
    
    def _add_rolling_average(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling average column to dataframe."""
        window = self.config.rolling_window
        df[f'Rolling_Avg_{window}d'] = df['Close'].rolling(window=window, min_periods=window).mean()
        return df
    
    def load_existing_data(self, symbol: str) -> pd.DataFrame:
        """Load existing data from CSV if available."""
        path = self._get_data_path(symbol)
        if path.exists():
            df = pd.read_csv(path, parse_dates=['Date'])
            df['Date'] = pd.to_datetime(df['Date']).dt.date
            return df
        return pd.DataFrame()
    
    def save_data(self, df: pd.DataFrame, symbol: str) -> None:
        """Save data to CSV."""
        path = self._get_data_path(symbol)
        df.to_csv(path, index=False)
        print(f"💾 Saved {len(df)} records to {path}")
    
    def update_data(self, symbol: str) -> pd.DataFrame:
        """
        Update existing data with the latest day's data.
        
        If no existing data, performs a full historical fetch.
        """
        existing = self.load_existing_data(symbol)
        
        if existing.empty:
            print(f"No existing data for {symbol}, performing full historical fetch...")
            df = self.fetch_historical(symbol)
            if not df.empty:
                self.save_data(df, symbol)
            return df
        
        # Get the latest data
        latest = self.fetch_latest(symbol)
        if latest.empty:
            return existing
        
        latest_date = latest['Date'].iloc[0]
        
        # Check if we already have this date
        if latest_date in existing['Date'].values:
            print(f"✅ Data for {latest_date} already exists")
            return existing
        
        # Append new data
        combined = pd.concat([existing, latest], ignore_index=True)
        combined = combined.sort_values('Date').reset_index(drop=True)
        
        # Recalculate rolling average for the entire dataset
        combined = self._add_rolling_average(combined)
        
        self.save_data(combined, symbol)
        print(f"✅ Added data for {latest_date}")
        
        return combined
    
    def run_initial(self, symbols: list[str] | None = None) -> dict[str, pd.DataFrame]:
        """
        Run initial historical data fetch for all configured symbols.
        
        Args:
            symbols: List of symbols to fetch (defaults to config.symbols)
            
        Returns:
            Dictionary mapping symbols to their DataFrames
        """
        symbols = symbols or self.config.symbols
        results = {}
        
        print("=" * 60)
        print("🚀 INITIAL HISTORICAL DATA FETCH")
        print("=" * 60)
        
        for symbol in symbols:
            df = self.fetch_historical(symbol)
            if not df.empty:
                self.save_data(df, symbol)
                results[symbol] = df
            print()
        
        return results
    
    def run_daily(self, symbols: list[str] | None = None) -> dict[str, pd.DataFrame]:
        """
        Run daily update for all configured symbols.
        
        Args:
            symbols: List of symbols to update (defaults to config.symbols)
            
        Returns:
            Dictionary mapping symbols to their DataFrames
        """
        symbols = symbols or self.config.symbols
        results = {}
        
        print("=" * 60)
        print("📅 DAILY DATA UPDATE")
        print("=" * 60)
        
        for symbol in symbols:
            df = self.update_data(symbol)
            if not df.empty:
                results[symbol] = df
            print()
        
        return results
    
    def display_data(self, df: pd.DataFrame, symbol: str, tail: int = 20) -> None:
        """Display the most recent data in a formatted table."""
        from tabulate import tabulate
        
        if df.empty:
            print(f"No data to display for {symbol}")
            return
        
        print(f"\n{'='*60}")
        print(f"📊 {symbol} - Last {tail} Trading Days")
        print(f"{'='*60}")
        
        # Get the last N rows
        display_df = df.tail(tail).copy()
        
        # Format the columns
        display_df['Close'] = display_df['Close'].apply(lambda x: f"${x:.2f}")
        
        rolling_col = f'Rolling_Avg_{self.config.rolling_window}d'
        if rolling_col in display_df.columns:
            display_df[rolling_col] = display_df[rolling_col].apply(
                lambda x: f"${x:.2f}" if pd.notna(x) else "N/A"
            )
        
        print(tabulate(display_df, headers='keys', tablefmt='pretty', showindex=False))
        
        # Summary statistics
        print(f"\n📈 Summary:")
        latest_close = df['Close'].iloc[-1]
        if rolling_col in df.columns and pd.notna(df[rolling_col].iloc[-1]):
            latest_avg = df[rolling_col].iloc[-1]
            diff = latest_close - latest_avg
            diff_pct = (diff / latest_avg) * 100
            trend = "above" if diff > 0 else "below"
            print(f"   Latest Close: ${latest_close:.2f}")
            print(f"   {self.config.rolling_window}-day Avg: ${latest_avg:.2f}")
            print(f"   Current price is {abs(diff_pct):.2f}% {trend} the rolling average")
        else:
            print(f"   Latest Close: ${latest_close:.2f}")
            print(f"   Rolling average requires {self.config.rolling_window} days of data")
    
    def plot_chart(self, symbols: list[str] | None = None, save_path: str | None = None) -> None:
        """
        Plot stock prices and rolling averages for given symbols.
        
        Args:
            symbols: List of stock symbols to plot (defaults to config.symbols)
            save_path: Optional path to save the chart image
        """
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        symbols = symbols or self.config.symbols
        rolling_col = f'Rolling_Avg_{self.config.rolling_window}d'
        
        # Load data for all symbols
        data = {}
        for symbol in symbols:
            df = self.load_existing_data(symbol)
            if not df.empty:
                # Recalculate rolling average with current window
                df = self._add_rolling_average(df)
                data[symbol] = df
            else:
                print(f"⚠️  No data found for {symbol}. Run 'initial' first.")
        
        if not data:
            print("No data to plot.")
            return
        
        # Set up the plot style
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # Create figure with subplots - one per stock
        n_stocks = len(data)
        fig, axes = plt.subplots(n_stocks, 1, figsize=(14, 6 * n_stocks), squeeze=False)
        
        # Color palette
        colors = {
            'price': '#2563eb',      # Blue
            'avg': '#dc2626',        # Red
        }
        
        for idx, (symbol, df) in enumerate(data.items()):
            ax = axes[idx, 0]
            
            # Convert dates for plotting
            dates = pd.to_datetime(df['Date'])
            
            # Plot daily close price
            ax.plot(dates, df['Close'], 
                   color=colors['price'], 
                   linewidth=1.5, 
                   label=f'{symbol} Daily Close',
                   alpha=0.9)
            
            # Plot rolling average (only where it exists)
            if rolling_col in df.columns:
                valid_avg = df[rolling_col].notna()
                ax.plot(dates[valid_avg], df.loc[valid_avg, rolling_col],
                       color=colors['avg'],
                       linewidth=2,
                       label=f'{self.config.rolling_window}-Day Moving Avg',
                       linestyle='--')
            
            # Styling
            ax.set_title(f'{symbol} Stock Price with {self.config.rolling_window}-Day Moving Average',
                        fontsize=14, fontweight='bold', pad=15)
            ax.set_xlabel('Date', fontsize=11)
            ax.set_ylabel('Price ($)', fontsize=11)
            ax.legend(loc='upper left', fontsize=10)
            
            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.MonthLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
            
            # Add grid
            ax.grid(True, alpha=0.3)
            
            # Add current price annotation
            latest_price = df['Close'].iloc[-1]
            latest_date = dates.iloc[-1]
            ax.annotate(f'${latest_price:.2f}',
                       xy=(latest_date, latest_price),
                       xytext=(10, 10),
                       textcoords='offset points',
                       fontsize=10,
                       fontweight='bold',
                       color=colors['price'],
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=colors['price'], alpha=0.8))
            
            # Add moving avg annotation if available
            if rolling_col in df.columns and pd.notna(df[rolling_col].iloc[-1]):
                latest_avg = df[rolling_col].iloc[-1]
                ax.annotate(f'${latest_avg:.2f}',
                           xy=(latest_date, latest_avg),
                           xytext=(10, -15),
                           textcoords='offset points',
                           fontsize=10,
                           fontweight='bold',
                           color=colors['avg'],
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=colors['avg'], alpha=0.8))
        
        plt.tight_layout()
        
        if save_path:
            # Create directory if it doesn't exist
            save_dir = Path(save_path).parent
            if save_dir and not save_dir.exists():
                save_dir.mkdir(parents=True, exist_ok=True)
            plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
            print(f"📊 Chart saved to {save_path}")
        
        plt.show()
        print("📊 Chart displayed!")
