# 📈 StocksMania

A Python-based stock tracker that monitors daily prices, calculates 150-day moving averages, and sends actionable **BUY/SELL recommendations** via Telegram.

![Example Chart](charts/semiconductors.png)

## 🎯 What It Does

- **Fetches daily stock prices** from multiple free data sources (Stooq, Yahoo Finance, Alpha Vantage)
- **Calculates 150-day moving averages** - a key technical indicator used by traders
- **Generates BUY/SELL signals** based on price position relative to the moving average
- **Sends daily Telegram reports** with actionable recommendations
- **Runs automatically** via GitHub Actions (no server needed!)

## 📊 The Strategy

The 150-day moving average is a popular technical indicator. The logic:

| Price vs 150-MA | Signal | Meaning |
|-----------------|--------|---------|
| 0% to +15% | 🟢 **BUY** | Healthy uptrend, good entry |
| +15% to +40% | 🟡 **HOLD** | Extended, wait for pullback |
| > +40% | 🔴 **SELL** | Overbought, take profits |
| < -10% | 🔴 **SELL** | Downtrend, avoid |

## 📱 Daily Telegram Report

Every day at market close, you receive:

```
📈 StocksMania - Jan 18, 2026
━━━━━━━━━━━━━━━━━━━━

🟢 ACTION: BUY
(Above MA, not overbought)
  → PLTR $170.96 (+0.8%)
  → KO $70.44 (+2.5%)
  → COST $963.61 (+3.0%)
  → JPM $312.47 (+3.1%)
  → NVDA $186.23 (+4.4%)

🔴 ACTION: SELL/AVOID
(Below -10% or overbought >40%)
  → SPOT $504.50 (-23.5%) ⚠️ downtrend
  → COIN $241.15 (-22.9%) ⚠️ downtrend
  → INTC $46.96 (+50.2%) ⚠️ overbought

━━━━━━━━━━━━━━━━━━━━
💼 YOUR HOLDINGS CHECK:

NVDA: $186.23
  vs 150-MA: +4.4%
  Today: -0.4%
  → ✅ KEEP / ADD MORE

━━━━━━━━━━━━━━━━━━━━
🚀 Top Gainer: NVO +9.1%
💥 Top Loser: PLTR -3.5%
```

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/yanivvi/stocksmania.git
cd stocksmania
```

### 2. Set up Python environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Create your `.env` file

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Fetch historical data

```bash
python main.py initial -s NVDA AAPL MSFT GOOGL
```

### 5. View charts

```bash
python main.py chart NVDA AAPL --save charts/my_stocks.png
```

## 💻 CLI Commands

### Fetch Historical Data
```bash
# Single stock
python main.py initial -s NVDA

# Multiple stocks
python main.py initial -s NVDA AAPL MSFT GOOGL AMZN

# Custom date range
python main.py initial -s NVDA --start 2024-01-01

# Custom moving average window
python main.py initial -s NVDA --window 200
```

### Daily Update
```bash
# Update all tracked stocks
python main.py daily -s NVDA AAPL MSFT
```

### View Data
```bash
# Show last 20 days
python main.py show NVDA

# Show last 50 days
python main.py show NVDA -d 50
```

### Generate Charts
```bash
# Display chart
python main.py chart NVDA AAPL

# Save to file
python main.py chart NVDA AAPL --save charts/comparison.png

# With custom MA window
python main.py chart NVDA -w 50
```

### Send Telegram Report
```bash
# Requires TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MY_HOLDINGS env vars
python telegram_notify.py
```

## 📁 Project Structure

```
stocksmania/
├── main.py              # CLI entry point
├── stock_fetcher.py     # Data fetching & processing
├── telegram_notify.py   # Telegram notifications
├── config.py            # Configuration
├── providers.py         # Data source providers
├── stocks.txt           # 📋 List of tickers to track
├── requirements.txt     # Dependencies
├── daily_update.sh      # Local cron script
├── add_stock.sh         # Helper to add new stocks locally
├── data/                # Stock price CSVs
│   ├── NVDA_prices.csv
│   ├── AAPL_prices.csv
│   └── ...
├── charts/              # Generated charts
└── .github/
    └── workflows/
        ├── daily_update.yml  # Daily stock updates
        └── add_stock.yml     # Add new stocks via browser
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | `123456:ABC...` |
| `TELEGRAM_CHAT_ID` | Your chat ID from @userinfobot | `123456789` |
| `MY_HOLDINGS` | Your stock holdings (comma-separated) | `NVDA,AAPL,GOOGL` |
| `ALPHA_VANTAGE_API_KEY` | Optional API key | `XXXXXXXXXX` |

### GitHub Secrets (for Actions)

Add these in **Settings → Secrets → Actions**:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `MY_HOLDINGS`

## 📊 Tracked Stocks

Currently tracking 23 stocks across multiple sectors:

| Sector | Stocks |
|--------|--------|
| **Big Tech** | AAPL, MSFT, GOOGL, AMZN, META, TSLA |
| **Semiconductors** | NVDA, AMD, INTC |
| **AI/Software** | PLTR, CRM |
| **Cybersecurity** | CRWD, PANW |
| **Healthcare** | LLY, NVO |
| **Financials** | JPM, V, COIN |
| **Consumer** | KO, COST, NFLX, SPOT |
| **Industrial** | BA |

## ➕ Adding New Stocks

### Option 1: From Browser (Recommended) 📱

No coding needed! Just use GitHub Actions:

1. Go to [**Actions** → **Add New Stock**](https://github.com/yanivvi/stocksmania/actions/workflows/add_stock.yml)
2. Click **"Run workflow"**
3. Enter tickers: `UBER DIS PYPL`
4. Click **"Run workflow"** ✅

The action will:
- ✅ Fetch historical data
- ✅ Add ticker to `stocks.txt`
- ✅ Commit changes to repo
- ✅ Send you a Telegram confirmation!

### Option 2: Local Script

```bash
./add_stock.sh UBER
# Or multiple:
./add_stock.sh UBER DIS PYPL
```

### Option 3: Manual Steps

```bash
# 1. Fetch historical data
python main.py initial -s UBER

# 2. Add ticker to stocks.txt
echo "UBER" >> stocks.txt

# 3. Commit and push
git add -A && git commit -m "Add UBER" && git push
```

## 🤖 GitHub Actions

Two workflows available:

### Daily Update (Automatic)
- **Schedule**: Every weekday at 6pm Israel time (4pm UTC)
- **Manual**: Can be triggered from Actions tab
- **What it does**:
  1. Fetches latest stock prices
  2. Updates CSV data files
  3. Sends Telegram report
  4. Commits updated data to repo

### Add New Stock (Manual)
- **Trigger**: Manual only (workflow_dispatch)
- **Input**: Stock tickers (space-separated)
- **What it does**:
  1. Fetches historical data for new stocks
  2. Updates the daily workflow
  3. Commits changes
  4. Sends Telegram confirmation

## 📈 Data Sources

Tries multiple providers with fallback:
1. **Stooq** - Free, full historical data
2. **Alpha Vantage** - Free tier (100 days)
3. **Yahoo Finance** - Backup

## 🛠️ Local Cron Setup (Optional)

If you prefer running locally instead of GitHub Actions:

```bash
# Make script executable
chmod +x daily_update.sh

# Add to crontab (runs at 6pm on weekdays)
crontab -e
# Add: 0 18 * * 1-5 /path/to/stocksmania/daily_update.sh
```

## 📜 License

MIT License - feel free to use and modify!

## ⚠️ Disclaimer

**This is not financial advice.** This tool is for educational and informational purposes only. Always do your own research before making investment decisions. Past performance does not guarantee future results.

---

Made with ❤️ and Python
