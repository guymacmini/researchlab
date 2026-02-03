# ResearchLab LITE Setup Guide 🚀

The ultimate simple setup for AI investment research - get running in under 5 minutes!

## ✨ What is ResearchLab LITE?

A streamlined version of ResearchLab that removes all complex infrastructure:

- ❌ No Docker containers
- ❌ No PostgreSQL database  
- ❌ No Redis cache server
- ❌ No complex configuration

- ✅ SQLite database (single file)
- ✅ In-memory caching
- ✅ Simple web interface
- ✅ One command to start

## 🏃 Quick Start (3 Commands)

### 1. Install Dependencies
```bash
pip install -r requirements-lite.txt
```

### 2. Setup API Keys
```bash
cp .env.lite .env
# Edit .env with your actual API keys
```

### 3. Run!
```bash
python run.py
```

Your browser opens automatically to http://localhost:8000 🎉

## 🔑 Get Your Free API Keys

### 🤖 Anthropic Claude (Required)
1. Go to: https://console.anthropic.com/
2. Sign up for free account  
3. Get API key from dashboard
4. Free: $5 credit to start

### 📈 Finnhub (Required)
1. Go to: https://finnhub.io/dashboard
2. Sign up for free account
3. Copy your API key  
4. Free: 60 calls/minute

### 📊 Alpha Vantage (Optional)
1. Go to: https://www.alphavantage.co/support/#api-key
2. Get free API key
3. Free: 25 calls/day

## 💻 Step-by-Step Setup

### Prerequisites
- Python 3.8+ installed
- Git (to clone the repository)

### Detailed Setup

1. **Clone and switch to lite branch:**
   ```bash
   git clone https://github.com/your-username/researchlab.git
   cd researchlab
   git checkout lite
   ```

2. **Create virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements-lite.txt
   ```

4. **Setup environment file:**
   ```bash
   cp .env.lite .env
   ```

5. **Edit .env with your API keys:**
   ```bash
   # Required
   ANTHROPIC_API_KEY=sk-ant-your_actual_key_here
   FINNHUB_API_KEY=your_actual_finnhub_key_here
   
   # Optional  
   ALPHA_VANTAGE_API_KEY=your_actual_alpha_vantage_key_here
   ```

6. **Test the setup:**
   ```bash
   python test_lite.py
   ```

7. **Run the application:**
   ```bash
   python run.py
   ```

## 🎯 Using ResearchLab LITE

Once running, you can:

1. **Ask research questions:**
   - "What's the investment potential of Apple?"
   - "Should I invest in Tesla right now?"
   - "Analyze Microsoft's recent performance"

2. **Get instant AI analysis:**
   - Company overview and business model
   - Financial health and key metrics  
   - Recent news and market sentiment
   - Investment thesis and risk factors

3. **View research history:**
   - All analyses are saved automatically
   - Browse previous research queries
   - Bookmark important results

## 🔧 Configuration

The lite version has minimal configuration in `.env`:

```bash
# Required API Keys
ANTHROPIC_API_KEY=your_key_here
FINNHUB_API_KEY=your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here  # optional

# Database (auto-created)
DATABASE_FILE=researchlab.db

# App Settings (optional)  
DEBUG=true
HOST=localhost
PORT=8000
```

## 🐛 Troubleshooting

### "API key validation failed"
- Double-check your API keys are correct
- Anthropic keys start with `sk-ant-`
- Don't put quotes around keys in .env

### "Module not found" errors  
```bash
pip install -r requirements-lite.txt
```

### Port already in use
```bash
PORT=3000 python run.py
```

### Browser doesn't open
- Manually go to: http://localhost:8000
- Check firewall settings

### Rate limit errors
- Finnhub free: 60 calls/minute
- Alpha Vantage free: 25 calls/day  
- Wait between requests

## 📁 Project Structure

```
ResearchLab LITE/
├── run.py                  # Main entry point - start here!
├── test_lite.py            # Test suite
├── requirements-lite.txt   # Minimal dependencies
├── .env.lite              # Environment template
├── README-LITE.md         # Documentation
├── src/lite/
│   ├── config.py          # Simple configuration
│   ├── database.py        # SQLite + cache
│   ├── agent.py           # AI research agent
│   ├── app.py             # Web application
│   └── templates/         # HTML templates
└── researchlab.db         # Auto-created database
```

## 🚀 Next Steps

1. **Try different queries** - The AI can analyze any public company
2. **Experiment with specifics** - Ask about growth, risks, valuation
3. **Check your history** - All research is saved automatically  
4. **Share results** - Copy analysis or bookmark URLs

## 💡 Pro Tips

- **Be specific:** "Apple's growth potential in AI" vs "Apple stock"
- **Use symbols:** Include ticker symbols when known (AAPL, TSLA)
- **Ask follow-ups:** Use the clarifying questions for deeper analysis
- **Time context:** Mention timeframes ("recent", "2024 outlook")

## 🆚 LITE vs Full Version

| Feature | LITE | Full |
|---------|------|------|
| Database | SQLite | PostgreSQL |
| Caching | In-memory | Redis |
| Setup | 3 commands | Docker + complex |
| UI | Simple web | Advanced frontend |
| Agents | Core research | Multiple specialist agents |
| Deployment | Local only | Production ready |
| Dependencies | ~15 packages | 50+ packages |

## 🤝 Support

- **Documentation:** README-LITE.md (this file)
- **Test suite:** `python test_lite.py`
- **Issues:** Check GitHub issues
- **Community:** Join our Discord/Slack

---

**Happy researching!** 📈✨

*Made with ❤️ for simple, powerful investment research*