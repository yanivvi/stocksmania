#!/usr/bin/env python3
"""Send daily stock report with charts and BUY/SELL recommendations to Telegram."""

import os
import requests
import pandas as pd
from pathlib import Path
from datetime import date

from config import StockConfig, DEFAULT_CONFIG
from stock_fetcher import StockFetcher

# Telegram Config (from environment variables)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Your holdings (comma-separated in env var, e.g., "NVDA,AAPL,GOOGL")
MY_HOLDINGS = [h.strip() for h in os.environ.get("MY_HOLDINGS", "").split(",") if h.strip()]

# Thresholds for recommendations
ROLLING_WINDOW = 150
BUY_ZONE_MIN = 0      # Above MA
BUY_ZONE_MAX = 15     # But not too extended
SELL_BELOW = -10      # Sell if this far below MA
OVERBOUGHT = 40       # Sell if this far above MA (take profits)


def send_telegram_message(message: str) -> bool:
    """Send text message to Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False


def send_telegram_photo(photo_path: str, caption: str) -> bool:
    """Send photo with caption to Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            data = {
                "chat_id": CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML"
            }
            files = {"photo": photo}
            response = requests.post(url, data=data, files=files, timeout=60)
            return response.status_code == 200
    except Exception as e:
        print(f"Error sending Telegram photo: {e}")
        return False


def load_stock_data(symbol: str) -> dict | None:
    """Load stock data and calculate metrics."""
    csv_path = Path("data") / f"{symbol}_prices.csv"
    if not csv_path.exists():
        return None
    
    df = pd.read_csv(csv_path)
    if len(df) < 2:
        return None
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    price = latest['Close']
    ma_col = f'Rolling_Avg_{ROLLING_WINDOW}d'
    ma_150 = latest.get(ma_col) if ma_col in df.columns else None
    
    # Calculate vs MA percentage
    if pd.notna(ma_150) and ma_150 > 0:
        vs_ma = ((price - ma_150) / ma_150) * 100
    else:
        vs_ma = None
    
    # Daily change
    daily_change = ((price - prev['Close']) / prev['Close']) * 100
    
    return {
        'price': price,
        'ma_150': ma_150,
        'vs_ma': vs_ma,
        'daily_change': daily_change
    }


def get_signal_and_reason(vs_ma: float | None) -> tuple[str, str, str]:
    """
    Get signal, emoji, and detailed reason based on vs MA percentage.
    Returns: (signal, emoji, reason)
    """
    if vs_ma is None:
        return ("HOLD", "⏸️", "Not enough data for 150-day MA")
    
    if vs_ma >= OVERBOUGHT:
        return ("SELL", "🔴", f"Overbought at +{vs_ma:.1f}% above MA. Consider taking profits - extended move may reverse.")
    elif vs_ma <= SELL_BELOW:
        return ("SELL", "🔴", f"Downtrend at {vs_ma:.1f}% below MA. Price losing momentum - avoid or exit position.")
    elif BUY_ZONE_MIN <= vs_ma <= BUY_ZONE_MAX:
        return ("BUY", "🟢", f"Healthy uptrend at +{vs_ma:.1f}% above MA. Good entry point - riding the trend with room to grow.")
    elif vs_ma > BUY_ZONE_MAX:
        return ("HOLD", "🟡", f"Extended at +{vs_ma:.1f}% above MA. Wait for pullback to MA for better entry.")
    else:
        return ("HOLD", "🟡", f"Slightly below MA at {vs_ma:.1f}%. Wait for confirmation of trend reversal.")


def generate_all_charts(fetcher: StockFetcher, symbols: list[str]) -> dict[str, str]:
    """Generate charts for all symbols and return paths."""
    charts = {}
    for symbol in symbols:
        chart_path = fetcher.generate_stock_chart(symbol, save_dir="charts")
        if chart_path:
            charts[symbol] = chart_path
            print(f"   📊 Generated chart for {symbol}")
    return charts


def main():
    # Validate environment variables
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set!")
        return
    
    print("📱 Generating daily report with charts...")
    
    # Load tickers from stocks.txt
    stocks_file = Path("stocks.txt")
    if stocks_file.exists():
        symbols = [line.strip() for line in stocks_file.read_text().splitlines() 
                   if line.strip() and not line.startswith('#')]
    else:
        print("❌ stocks.txt not found!")
        return
    
    # Initialize fetcher for chart generation
    config = StockConfig(rolling_window=ROLLING_WINDOW)
    fetcher = StockFetcher(config)
    
    # Generate charts for all stocks
    print("\n📊 Generating charts...")
    charts = generate_all_charts(fetcher, symbols)
    
    # Load data and categorize
    buy_stocks = []
    sell_stocks = []
    hold_stocks = []
    all_stocks = {}
    
    for symbol in symbols:
        data = load_stock_data(symbol)
        if data:
            all_stocks[symbol] = data
            signal, _, reason = get_signal_and_reason(data['vs_ma'])
            if signal == "BUY":
                buy_stocks.append((symbol, data, reason))
            elif signal == "SELL":
                sell_stocks.append((symbol, data, reason))
            else:
                hold_stocks.append((symbol, data, reason))
    
    # Sort by vs_ma
    buy_stocks.sort(key=lambda x: x[1]['vs_ma'] if x[1]['vs_ma'] else 0)  # Best entries first
    sell_stocks.sort(key=lambda x: x[1]['vs_ma'] if x[1]['vs_ma'] else 0)  # Worst first
    
    today = date.today().strftime("%b %d, %Y")
    
    # === Send Header Message ===
    header = f"📈 <b>StocksMania Daily Report</b>\n"
    header += f"📅 {today}\n"
    header += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Summary counts
    header += f"🟢 BUY signals: {len(buy_stocks)}\n"
    header += f"🔴 SELL signals: {len(sell_stocks)}\n"
    header += f"🟡 HOLD signals: {len(hold_stocks)}\n"
    
    print("\n📤 Sending header...")
    send_telegram_message(header)
    
    # === Send BUY Charts with Reasoning ===
    if buy_stocks:
        print(f"\n📤 Sending {len(buy_stocks)} BUY recommendations...")
        send_telegram_message("🟢 <b>═══ BUY SIGNALS ═══</b>")
        
        for symbol, data, reason in buy_stocks[:5]:  # Top 5 buys
            caption = f"🟢 <b>BUY: {symbol}</b>\n\n"
            caption += f"💰 Price: ${data['price']:.2f}\n"
            caption += f"📊 150-Day MA: ${data['ma_150']:.2f}\n"
            caption += f"📈 vs MA: {data['vs_ma']:+.1f}%\n"
            caption += f"📉 Today: {data['daily_change']:+.1f}%\n\n"
            caption += f"💡 <i>{reason}</i>"
            
            if symbol in charts:
                send_telegram_photo(charts[symbol], caption)
            else:
                send_telegram_message(caption)
    
    # === Send SELL Charts with Reasoning ===
    if sell_stocks:
        print(f"\n📤 Sending {len(sell_stocks)} SELL warnings...")
        send_telegram_message("🔴 <b>═══ SELL/AVOID ═══</b>")
        
        for symbol, data, reason in sell_stocks[:5]:  # Top 5 sells
            caption = f"🔴 <b>SELL: {symbol}</b>\n\n"
            caption += f"💰 Price: ${data['price']:.2f}\n"
            if data['ma_150']:
                caption += f"📊 150-Day MA: ${data['ma_150']:.2f}\n"
                caption += f"📈 vs MA: {data['vs_ma']:+.1f}%\n"
            caption += f"📉 Today: {data['daily_change']:+.1f}%\n\n"
            caption += f"⚠️ <i>{reason}</i>"
            
            if symbol in charts:
                send_telegram_photo(charts[symbol], caption)
            else:
                send_telegram_message(caption)
    
    # === MY HOLDINGS Check ===
    if MY_HOLDINGS:
        print(f"\n📤 Sending holdings check...")
        holdings_msg = "💼 <b>═══ YOUR HOLDINGS ═══</b>\n\n"
        
        for symbol in MY_HOLDINGS:
            if symbol in all_stocks:
                data = all_stocks[symbol]
                signal, emoji, reason = get_signal_and_reason(data['vs_ma'])
                
                holdings_msg += f"{emoji} <b>{symbol}</b>: ${data['price']:.2f}\n"
                if data['vs_ma']:
                    holdings_msg += f"   vs MA: {data['vs_ma']:+.1f}% | Today: {data['daily_change']:+.1f}%\n"
                holdings_msg += f"   → <i>{signal}</i>\n\n"
        
        send_telegram_message(holdings_msg)
        
        # Send charts for holdings that need attention
        for symbol in MY_HOLDINGS:
            if symbol in all_stocks:
                data = all_stocks[symbol]
                signal, _, reason = get_signal_and_reason(data['vs_ma'])
                
                if signal == "SELL" and symbol in charts:
                    caption = f"⚠️ <b>HOLDING ALERT: {symbol}</b>\n\n"
                    caption += f"💰 Price: ${data['price']:.2f}\n"
                    caption += f"📈 vs MA: {data['vs_ma']:+.1f}%\n\n"
                    caption += f"<i>{reason}</i>"
                    send_telegram_photo(charts[symbol], caption)
    
    # === Top Movers ===
    sorted_by_daily = sorted(all_stocks.items(), key=lambda x: x[1]['daily_change'], reverse=True)
    if sorted_by_daily:
        top_gainer = sorted_by_daily[0]
        top_loser = sorted_by_daily[-1]
        
        movers_msg = "📊 <b>═══ TOP MOVERS ═══</b>\n\n"
        movers_msg += f"🚀 <b>{top_gainer[0]}</b>: {top_gainer[1]['daily_change']:+.1f}%\n"
        movers_msg += f"💥 <b>{top_loser[0]}</b>: {top_loser[1]['daily_change']:+.1f}%"
        
        send_telegram_message(movers_msg)
    
    print("\n✅ Report sent successfully!")


if __name__ == "__main__":
    main()
