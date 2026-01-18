#!/usr/bin/env python3
"""
StocksMania - Stock Price Tracker with Rolling Averages

Usage:
    python main.py initial              # Fetch historical data from 2025-01-01
    python main.py daily                # Update with latest day's data
    python main.py initial --symbols NVDA AAPL MSFT
    python main.py daily --symbols NVDA --display 30
    python main.py show NVDA            # Display existing data for a symbol
    python main.py chart NVDA AAPL      # Show chart with price and moving avg
    
Set ALPHA_VANTAGE_API_KEY env var or use --api-key for reliable data fetching.
Get free API key at: https://www.alphavantage.co/support/#api-key
"""

import argparse
import os
from datetime import date

from config import StockConfig
from stock_fetcher import StockFetcher


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    return date.fromisoformat(date_str)


def main():
    parser = argparse.ArgumentParser(
        description="Stock Price Tracker with Rolling Averages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py initial                    # Initial fetch for default symbols (NVDA)
  python main.py daily                      # Daily update for default symbols
  python main.py initial -s NVDA AAPL       # Initial fetch for multiple symbols
  python main.py daily -s NVDA -d 30        # Daily update, show last 30 days
  python main.py show NVDA                  # Show existing data for NVDA
  python main.py chart NVDA AAPL            # Chart with price & moving avg
  python main.py chart NVDA --save chart.png # Save chart to file
  python main.py initial --start 2024-06-01 # Custom start date
  python main.py initial --window 200       # Use 200-day rolling average

API Key:
  Set ALPHA_VANTAGE_API_KEY environment variable, or use --api-key flag
  Get free key: https://www.alphavantage.co/support/#api-key
        """
    )
    
    # Global API key argument
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='Alpha Vantage API key (or set ALPHA_VANTAGE_API_KEY env var)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Initial command
    initial_parser = subparsers.add_parser('initial', help='Fetch historical data')
    initial_parser.add_argument(
        '-s', '--symbols', 
        nargs='+', 
        default=['NVDA'],
        help='Stock symbols to fetch (default: NVDA)'
    )
    initial_parser.add_argument(
        '--start', 
        type=parse_date,
        default=date(2025, 1, 1),
        help='Start date for historical data (YYYY-MM-DD, default: 2025-01-01)'
    )
    initial_parser.add_argument(
        '--end', 
        type=parse_date,
        default=None,
        help='End date for historical data (YYYY-MM-DD, default: today)'
    )
    initial_parser.add_argument(
        '-w', '--window',
        type=int,
        default=150,
        help='Rolling average window in days (default: 150)'
    )
    initial_parser.add_argument(
        '-d', '--display',
        type=int,
        default=20,
        help='Number of rows to display (default: 20)'
    )
    
    # Daily command
    daily_parser = subparsers.add_parser('daily', help='Update with latest data')
    daily_parser.add_argument(
        '-s', '--symbols',
        nargs='+',
        default=['NVDA'],
        help='Stock symbols to update (default: NVDA)'
    )
    daily_parser.add_argument(
        '-w', '--window',
        type=int,
        default=150,
        help='Rolling average window in days (default: 150)'
    )
    daily_parser.add_argument(
        '-d', '--display',
        type=int,
        default=20,
        help='Number of rows to display (default: 20)'
    )
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Display existing data')
    show_parser.add_argument(
        'symbol',
        help='Stock symbol to display'
    )
    show_parser.add_argument(
        '-d', '--display',
        type=int,
        default=20,
        help='Number of rows to display (default: 20)'
    )
    show_parser.add_argument(
        '-w', '--window',
        type=int,
        default=150,
        help='Rolling average window in days (default: 150)'
    )
    
    # Chart command
    chart_parser = subparsers.add_parser('chart', help='Display chart with price and moving average')
    chart_parser.add_argument(
        'symbols',
        nargs='+',
        help='Stock symbols to chart'
    )
    chart_parser.add_argument(
        '-w', '--window',
        type=int,
        default=150,
        help='Rolling average window in days (default: 150)'
    )
    chart_parser.add_argument(
        '--save',
        type=str,
        default=None,
        help='Save chart to file (e.g., chart.png)'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Get API key from args or environment
    api_key = args.api_key or os.environ.get("ALPHA_VANTAGE_API_KEY")
    
    # Create config based on arguments
    if args.command == 'initial':
        config = StockConfig(
            symbols=args.symbols,
            rolling_window=args.window,
            historical_start=args.start
        )
        fetcher = StockFetcher(config, api_key=api_key)
        results = fetcher.run_initial()
        
        for symbol, df in results.items():
            fetcher.display_data(df, symbol, tail=args.display)
            
    elif args.command == 'daily':
        config = StockConfig(
            symbols=args.symbols,
            rolling_window=args.window
        )
        fetcher = StockFetcher(config, api_key=api_key)
        results = fetcher.run_daily()
        
        for symbol, df in results.items():
            fetcher.display_data(df, symbol, tail=args.display)
            
    elif args.command == 'show':
        config = StockConfig(rolling_window=args.window)
        fetcher = StockFetcher(config, api_key=api_key)
        df = fetcher.load_existing_data(args.symbol)
        
        if df.empty:
            print(f"No data found for {args.symbol}. Run 'initial' first.")
        else:
            # Recalculate rolling average with current window
            df = fetcher._add_rolling_average(df)
            fetcher.display_data(df, args.symbol, tail=args.display)
            
    elif args.command == 'chart':
        config = StockConfig(
            symbols=args.symbols,
            rolling_window=args.window
        )
        fetcher = StockFetcher(config, api_key=api_key)
        fetcher.plot_chart(symbols=args.symbols, save_path=args.save)


if __name__ == '__main__':
    main()
