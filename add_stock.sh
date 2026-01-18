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

# Step 2: Update daily_update.sh
echo ""
echo "2️⃣ Updating daily_update.sh..."
for ticker in $TICKERS; do
    if ! grep -q "$ticker" daily_update.sh; then
        sed -i '' "s/STOCKS=\"/STOCKS=\"$ticker /" daily_update.sh
        echo "   ✅ Added $ticker to daily_update.sh"
    else
        echo "   ⏭️ $ticker already in daily_update.sh"
    fi
done

# Step 3: Update GitHub workflow
echo ""
echo "3️⃣ Updating GitHub Actions workflow..."
WORKFLOW=".github/workflows/daily_update.yml"
for ticker in $TICKERS; do
    if ! grep -q "$ticker" $WORKFLOW; then
        sed -i '' "s/python main.py daily -s /python main.py daily -s $ticker /" $WORKFLOW
        echo "   ✅ Added $ticker to workflow"
    else
        echo "   ⏭️ $ticker already in workflow"
    fi
done

# Step 4: Git commit and push
echo ""
echo "4️⃣ Committing and pushing to GitHub..."
git add -A
git commit -m "➕ Add stocks: $TICKERS"
git push

echo ""
echo "=================================="
echo "✅ Done! Added: $TICKERS"
echo ""
echo "📱 These stocks will now appear in your daily Telegram reports!"
