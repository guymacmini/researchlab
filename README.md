# ResearchLab

AI-Led Investment Research Platform - Multi-agent system that mimics hedge fund analyst workflows.

## Overview

ResearchLab orchestrates specialized AI agents to conduct comprehensive investment research:

- **Research Director** - Query interpretation, scope definition, agent coordination
- **Fundamental Analyst** - Financial metrics extraction from earnings/filings
- **Supply Chain Analyst** - Upstream/downstream dependency mapping
- **Sentiment Analyst** - News and social media monitoring
- **Quantitative Analyst** - Statistical analysis and backtesting
- **Risk Analyst** - Contrarian views and thesis-breaking scenarios

## Features

- Intelligent query clarification (horizon, geography, market cap, sectors)
- Multi-factor company screening across Russell 3000+
- Second and third-order effect mapping
- Automated Google Sheets output with analysis tabs
- News monitoring with tiered source credibility
- Human-in-the-loop checkpoints for all major decisions

## Tech Stack

- **Backend**: Python (FastAPI)
- **Frontend**: React/Next.js
- **Database**: PostgreSQL + Redis + TimescaleDB
- **LLM**: Claude (Anthropic) primary, GPT-4 fallback
- **Data Sources**: Finnhub, Alpha Vantage, SEC EDGAR, Yahoo Finance

## Project Status

🚧 **Phase 1: Foundation** (In Progress)

See [docs/PRD.md](docs/PRD.md) for full requirements.

## Development

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
python -m src.main
```

## License

Private - All rights reserved.
