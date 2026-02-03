# ResearchLab LITE 🚀

**Dead simple AI investment research tool**

Get instant AI analysis of any stock or company in 3 easy steps!

## ⚡ Quick Start

### Step 1: Install Dependencies
```bash
pip install -r requirements-lite.txt
```

### Step 2: Add API Keys
1. Copy the example environment file:
   ```bash
   cp .env.lite .env
   ```

2. Edit `.env` and add your API keys:
   ```bash
   # Required
   ANTHROPIC_API_KEY=sk-ant-your_key_here
   FINNHUB_API_KEY=your_finnhub_key_here
   
   # Optional
   ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
   ```

### Step 3: Run!
```bash
python run.py
```

That's it! 🎉 Your browser will open automatically.

## 🔑 Get Your Free API Keys

### Anthropic Claude (Required)
- Go to: https://console.anthropic.com/
- Sign up for free account
- Get API key from dashboard
- Free tier: $5 credit to start

### Finnhub (Required)  
- Go to: https://finnhub.io/dashboard
- Sign up for free account
- Copy your API key
- Free tier: 60 calls/minute

### Alpha Vantage (Optional)
- Go to: https://www.alphavantage.co/support/#api-key
- Get free API key
- Free tier: 25 calls/day

## 🎯 What You Get

- **Simple Web Interface**: Just type your question and get instant analysis
- **AI-Powered Research**: Claude AI analyzes company data and provides insights  
- **Real-Time Data**: Latest stock prices, financials, and news
- **Research History**: Save and revisit your analyses
- **Zero Configuration**: SQLite database, no setup required

## 📝 Example Queries

Try these in the web interface:

- "What's the investment potential of Apple?"
- "Should I invest in Tesla right now?"
- "Analyze Microsoft's recent performance"
- "What are the risks of investing in Meta?"
- "Compare Amazon vs Google stock"

## 🏗️ What's Different from Full Version?

**LITE Version:**
- ✅ SQLite database (no PostgreSQL)
- ✅ In-memory caching (no Redis)
- ✅ Simple web UI (no complex frontend)
- ✅ One-command startup
- ✅ Essential features only

**Full Version:**
- PostgreSQL database
- Redis caching
- Docker deployment
- Advanced monitoring
- Multiple agent types
- Google Sheets integration

## 🛠️ Troubleshooting

### "API key validation failed"
- Make sure you copied the keys correctly from the provider dashboards
- Anthropic keys start with `sk-ant-`
- Don't include quotes around the keys in `.env`

### "Module not found" errors
- Make sure you ran: `pip install -r requirements-lite.txt`
- Try creating a virtual environment first:
  ```bash
  python -m venv venv
  source venv/bin/activate  # or `venv\Scripts\activate` on Windows
  pip install -r requirements-lite.txt
  python run.py
  ```

### Browser doesn't open automatically
- Manually open: http://localhost:8000
- Or set custom port: `PORT=3000 python run.py`

### Rate limit errors
- Finnhub free tier: 60 calls/minute
- Alpha Vantage free tier: 25 calls/day
- Wait a moment between requests

## 📊 Architecture

```
ResearchLab LITE
├── run.py              # Main entry point
├── requirements-lite.txt # Minimal dependencies
├── .env.lite           # Environment template
├── src/lite/
│   ├── config.py       # Simple configuration
│   ├── database.py     # SQLite + in-memory cache
│   ├── agent.py        # Core AI research agent
│   ├── app.py          # FastAPI web application
│   └── templates/      # HTML templates
└── researchlab.db      # Auto-created SQLite database
```

## 🚀 Next Steps

1. **Try different queries** - The AI can analyze any public company
2. **Check your research history** - All analyses are saved automatically
3. **Experiment with specific questions** - Ask about growth, risks, valuation, etc.
4. **Share results** - Copy the analysis text or bookmark result URLs

## 💡 Tips

- Be specific in your queries for better results
- Include company names or stock symbols (AAPL, TSLA, etc.)
- Ask about specific timeframes ("recent performance", "2024 outlook")
- The AI considers financial data, news, and market sentiment

---

**Happy researching!** 📈

Made with ❤️ by the ResearchLab team