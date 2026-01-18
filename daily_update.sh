#!/bin/bash
# StocksMania Daily Update Script

cd /Users/yaniv.vainer/workspace/projects/stocksmania
source venv/bin/activate

# Load secrets from .env file if it exists
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# All your stocks
STOCKS="NVDA AAPL MSFT GOOGL AMZN META TSLA AMD INTC BA KO PLTR CRM CRWD PANW LLY NVO JPM V NFLX COST COIN SPOT"

echo "=========================================="
echo "📈 StocksMania Daily Update - $(date)"
echo "=========================================="

# Fetch latest data
python main.py daily -s $STOCKS

# Send Telegram report
echo ""
echo "📱 Sending Telegram report..."
python telegram_notify.py

echo ""
echo "✅ Update complete!"
