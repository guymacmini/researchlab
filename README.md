# ResearchLab LITE 🔬

> **AI Investment Research** — Rigorous, quantified analysis in 30 seconds. No Docker, no database setup.

---

## ⚡ Quick Start

```bash
# Clone and setup
git clone https://github.com/guymacmini/researchlab.git
cd researchlab
git checkout lite

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set API keys
export ANTHROPIC_API_KEY="your-key"
export FINNHUB_API_KEY="your-key"

# Run
python run.py
```

Open http://localhost:8001 and ask: *"Should I buy NVIDIA?"*

---

## 🎯 What You Get

Every analysis includes **6 structured sections** with quantified metrics:

### 1. Executive Summary
```
HOLD recommendation with 6/10 confidence
12-month price target: $950 (8% upside from $880)
```

### 2. Quantified Business Analysis
- Revenue breakdown by segment with percentages
- Market share data with competitor comparisons
- Growth rates with YoY comparisons

### 3. Valuation Analysis
```
P/E: 65x vs sector average 25x (160% premium)
P/S: 22x vs sector average 5x (340% premium)
```

### 4. Risk Analysis (Severity Scored)
```
Risk Factor 1 (Severity 8/10): Cyclical Demand Cliff
Risk Factor 2 (Severity 7/10): Competitive Displacement
Risk Factor 3 (Severity 6/10): China Revenue Exposure
```

### 5. Contrarian Analysis (Bear Case)
- Why the investment could fail
- Key wrong assumptions the market is making
- Specific sell triggers

### 6. Actionable Recommendations
```
Entry Strategy: Buy below $750 (15% discount)
Stop Loss: $600 (25% downside protection)
Position Size: 3-4% of portfolio maximum
```

---

## 🔑 API Keys

| Service | Get Key | Purpose |
|---------|---------|---------|
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/) | AI analysis (Claude) |
| **Finnhub** | [finnhub.io](https://finnhub.io/) | Company data, financials, news |

Both have free tiers sufficient for personal use.

---

## 📁 Project Structure

```
researchlab/
├── run.py                 # Entry point
├── requirements.txt       # Dependencies
└── src/lite/
    ├── agent.py          # Research agent with analysis logic
    ├── app.py            # Flask web UI
    ├── database.py       # SQLite + in-memory cache
    ├── config.py         # Settings
    └── templates/        # Web templates
```

---

## 🛠️ Tech Stack

- **Python 3.11+** — No complex setup
- **Flask** — Simple web UI
- **SQLite** — Zero-config database (auto-created)
- **Claude Sonnet 4** — Main analysis model
- **Claude Haiku 3.5** — Fast symbol extraction
- **Finnhub API** — Real-time financial data

---

## 💡 Example Queries

- *"Should I buy Apple stock?"*
- *"NVIDIA investment analysis"*
- *"Is Tesla overvalued?"*
- *"Compare AMD vs Intel"*
- *"What are the risks of investing in Microsoft?"*

---

## 🔧 Configuration

Environment variables (or `.env` file):

```bash
ANTHROPIC_API_KEY=sk-ant-...      # Required
FINNHUB_API_KEY=...               # Required
RESEARCHLAB_PORT=8001             # Optional (default: 8001)
```

---

## 📊 Analysis Quality Philosophy

This tool follows **first-principles investing**:

1. **Numbers over adjectives** — "65x P/E vs 25x sector" not "expensive"
2. **Devil's advocate** — Every analysis includes bear case
3. **Actionable output** — Entry price, stop loss, position size
4. **Risk quantification** — Severity scores 1-10
5. **Both sides** — Bull and bear cases presented

---

## 🚀 Main Branch

Looking for the full enterprise version with Docker, PostgreSQL, Redis, and multi-agent orchestration? Check the `main` branch.

```bash
git checkout main
```

---

## 📄 License

MIT — Use freely for personal investment research.

---

Built with Claude & Finnhub 🤖📈
