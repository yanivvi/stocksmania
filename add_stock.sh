#!/bin/bash
# Add new stocks to StocksMania
# Usage: ./add_stock.sh UBER DIS PYPL

set -e

cd /Users/yaniv.vainer/workspace/projects/stocksmania
source venv/bin/activate

if [ $# -eq 0 ]; then
    echo "❌ Usage: ./add_stock.sh TICKER1 TICKER2 ..."
    echo "   Example: ./add_stock.sh UBER DIS PYPL"
    exit 1
fi

TICKERS="$@"
echo "📈 Adding stocks: $TICKERS"
echo "=================================="

# Step 1: Fetch historical data
echo ""
echo "1️⃣ Fetching historical data..."
python main.py initial -s $TICKERS -d 5

# Step 2: Update stocks.txt
echo ""
echo "2️⃣ Updating stocks.txt..."
for ticker in $TICKERS; do
    if ! grep -q "^$ticker$" stocks.txt; then
        echo "$ticker" >> stocks.txt
        echo "   ✅ Added $ticker to stocks.txt"
    else
        echo "   ⏭️ $ticker already in stocks.txt"
    fi
done

# Step 3: Git commit and push
echo ""
echo "3️⃣ Committing and pushing to GitHub..."
git add -A
git commit -m "➕ Add stocks: $TICKERS"
git push

echo ""
echo "=================================="
echo "✅ Done! Added: $TICKERS"
echo ""
echo "📱 These stocks will now appear in your daily Telegram reports!"
