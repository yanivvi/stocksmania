#!/usr/bin/env python3
"""Send daily stock report with BUY/SELL recommendations to Telegram."""

import os
import requests
import pandas as pd
from pathlib import Path
from datetime import date

# Telegram Config (from environment variables)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Your holdings (comma-separated in env var, e.g., "NVDA,AAPL,GOOGL")
MY_HOLDINGS = os.environ.get("MY_HOLDINGS", "").split(",") if os.environ.get("MY_HOLDINGS") else []

# Thresholds for recommendations
BUY_ZONE_MIN = 0      # Above MA
BUY_ZONE_MAX = 15     # But not too extended
SELL_BELOW = -10      # Sell if this far below MA
OVERBOUGHT = 40       # Sell if this far above MA (take profits)

def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
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
        print(f"Error sending Telegram: {e}")
        return False

def load_all_stocks() -> dict:
    """Load all stock data and calculate metrics."""
    data_dir = Path("data")
    stocks = {}
    
    for csv_file in data_dir.glob("*_prices.csv"):
        symbol = csv_file.stem.replace("_prices", "")
        df = pd.read_csv(csv_file)
        
        if len(df) < 2:
            continue
            
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = latest['Close']
        ma_150 = latest.get('Rolling_Avg_150d')
        
        # Calculate vs MA percentage
        if pd.notna(ma_150) and ma_150 > 0:
            vs_ma = ((price - ma_150) / ma_150) * 100
        else:
            vs_ma = None
        
        # Daily change
        daily_change = ((price - prev['Close']) / prev['Close']) * 100
        
        stocks[symbol] = {
            'price': price,
            'ma_150': ma_150,
            'vs_ma': vs_ma,
            'daily_change': daily_change
        }
    
    return stocks

def get_recommendation(vs_ma: float) -> tuple:
    """Get recommendation based on vs MA percentage."""
    if vs_ma is None:
        return ("HOLD", "⏸️")
    
    if vs_ma >= OVERBOUGHT:
        return ("SELL", "🔴")  # Take profits, overbought
    elif vs_ma <= SELL_BELOW:
        return ("SELL", "🔴")  # Below MA, downtrend
    elif BUY_ZONE_MIN <= vs_ma <= BUY_ZONE_MAX:
        return ("BUY", "🟢")   # Sweet spot
    elif vs_ma > BUY_ZONE_MAX:
        return ("HOLD", "🟡")  # Extended, wait for pullback
    else:
        return ("HOLD", "🟡")  # Slightly below MA

def generate_report(stocks: dict) -> str:
    """Generate the daily report with actionable recommendations."""
    today = date.today().strftime("%b %d, %Y")
    
    # Categorize stocks
    buy_list = []
    sell_list = []
    
    for symbol, data in stocks.items():
        if data['vs_ma'] is None:
            continue
        rec, _ = get_recommendation(data['vs_ma'])
        if rec == "BUY":
            buy_list.append((symbol, data))
        elif rec == "SELL":
            sell_list.append((symbol, data))
    
    # Sort
    buy_list.sort(key=lambda x: x[1]['vs_ma'])  # Closest to MA first (best entry)
    sell_list.sort(key=lambda x: x[1]['vs_ma'])  # Worst first
    
    # Build message
    msg = f"📈 <b>StocksMania - {today}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # ACTION: BUY
    msg += "🟢 <b>ACTION: BUY</b>\n"
    msg += "<i>(Above MA, not overbought)</i>\n"
    if buy_list:
        for symbol, data in buy_list[:5]:
            msg += f"  → <b>{symbol}</b> ${data['price']:.2f} ({data['vs_ma']:+.1f}%)\n"
    else:
        msg += "  <i>No strong buys today</i>\n"
    msg += "\n"
    
    # ACTION: SELL
    msg += "🔴 <b>ACTION: SELL/AVOID</b>\n"
    msg += "<i>(Below -10% or overbought >40%)</i>\n"
    if sell_list:
        for symbol, data in sell_list[:5]:
            reason = "overbought" if data['vs_ma'] > OVERBOUGHT else "downtrend"
            msg += f"  → <b>{symbol}</b> ${data['price']:.2f} ({data['vs_ma']:+.1f}%) ⚠️ {reason}\n"
    else:
        msg += "  <i>Nothing to sell today</i>\n"
    msg += "\n"
    
    # MY HOLDINGS CHECK
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    msg += "💼 <b>YOUR HOLDINGS CHECK:</b>\n"
    for symbol in MY_HOLDINGS:
        if symbol in stocks:
            data = stocks[symbol]
            rec, emoji = get_recommendation(data['vs_ma'])
            
            if rec == "SELL":
                action = "⚠️ CONSIDER SELLING"
            elif rec == "BUY":
                action = "✅ KEEP / ADD MORE"
            else:
                action = "⏸️ HOLD"
            
            msg += f"\n<b>{symbol}</b>: ${data['price']:.2f}\n"
            msg += f"  vs 150-MA: {data['vs_ma']:+.1f}%\n"
            msg += f"  Today: {data['daily_change']:+.1f}%\n"
            msg += f"  → <b>{action}</b>\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━\n"
    
    # Top mover of the day
    sorted_by_daily = sorted(stocks.items(), key=lambda x: x[1]['daily_change'], reverse=True)
    top_gainer = sorted_by_daily[0]
    top_loser = sorted_by_daily[-1]
    
    msg += f"🚀 Top Gainer: <b>{top_gainer[0]}</b> {top_gainer[1]['daily_change']:+.1f}%\n"
    msg += f"💥 Top Loser: <b>{top_loser[0]}</b> {top_loser[1]['daily_change']:+.1f}%\n"
    
    return msg

def main():
    # Validate environment variables
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set!")
        print("   Set them as environment variables or in GitHub Secrets")
        return
    
    if not MY_HOLDINGS:
        print("⚠️  Warning: MY_HOLDINGS not set. Set it like: MY_HOLDINGS=NVDA,AAPL")
    
    print("📱 Generating Telegram report...")
    
    # Load data
    stocks = load_all_stocks()
    
    if not stocks:
        print("No stock data found!")
        return
    
    # Generate report
    report = generate_report(stocks)
    print(report)
    
    # Send to Telegram
    print("\n📤 Sending to Telegram...")
    if send_telegram(report):
        print("✅ Message sent successfully!")
    else:
        print("❌ Failed to send message")

if __name__ == "__main__":
    main()
