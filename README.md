# ResearchLab 🔬

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](https://github.com/user/researchlab/actions)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://docker.com)

> **AI-Led Investment Research Platform** - A sophisticated multi-agent system that replicates hedge fund analyst workflows with enterprise-grade reliability.

---

## 🎯 Overview

ResearchLab transforms investment research through intelligent AI orchestration. Our multi-agent architecture mirrors the specialized roles found in top-tier hedge funds, delivering comprehensive analysis with human oversight and validation.

### 🤖 Agent Architecture

| Agent | Role | Capabilities |
|-------|------|-------------|
| **Research Director** | 🎯 Strategy & Coordination | Query interpretation, scope definition, agent orchestration |
| **Fundamental Analyst** | 📊 Financial Analysis | SEC filings parsing, ratio analysis, earnings modeling |
| **Sentiment Analyst** | 📰 Market Sentiment | News aggregation, social media monitoring, sentiment scoring |
| **Supply Chain Analyst** | 🔗 Dependencies | Upstream/downstream mapping, supplier risk assessment |
| **Quantitative Analyst** | 📈 Statistical Analysis | Backtesting, correlation analysis, risk modeling |
| **Risk Analyst** | ⚠️ Contrarian Views | Thesis challenges, scenario analysis, risk quantification |

### ✨ Key Features

- **🧠 Intelligent Query Processing** - Natural language to structured research requests
- **📋 Multi-Factor Screening** - Russell 3000+ universe with custom filters  
- **🔄 Second-Order Analysis** - Comprehensive dependency and ripple effect mapping
- **📊 Automated Reporting** - Google Sheets integration with professional formatting
- **📡 Real-time Monitoring** - News alerts, price movements, SEC filings
- **👥 Human-in-the-Loop** - Approval checkpoints for critical decisions
- **🚀 Production Ready** - Enterprise monitoring, alerting, and rate limiting

---

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI Web  │    │   Agent Engine   │    │  External APIs  │
│     Server      │◄──►│   Multi-Agent    │◄──►│   Financial     │
│                 │    │   Orchestration  │    │   Data Sources  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │     Redis        │    │   Monitoring    │
│   Primary DB    │    │     Cache        │    │   & Alerting    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 🛠️ Tech Stack

**Backend & APIs**
- **FastAPI** - High-performance async web framework
- **Pydantic V2** - Data validation and serialization
- **SQLAlchemy 2.0** - Modern async ORM
- **Redis** - Caching and rate limiting backend

**Data & Storage**  
- **PostgreSQL** - Primary database with advanced features
- **TimescaleDB** - Time-series data for market history
- **Async I/O** - Non-blocking database and API operations

**AI & Analysis**
- **Anthropic Claude** - Primary LLM for analysis
- **OpenAI GPT-4** - Fallback and specialized tasks
- **Custom Agents** - Domain-specific analysis engines

**Data Sources**
- **SEC EDGAR** - Official filings and reports
- **Finnhub** - Real-time market data
- **Alpha Vantage** - Historical data and fundamentals
- **Yahoo Finance** - Market data and news

**DevOps & Production**
- **Docker** - Containerized deployment
- **Prometheus** - Metrics collection
- **Structured Logging** - JSON logs with correlation IDs
- **Rate Limiting** - Multi-tier protection

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 14+
- Redis 7+

### 1. Clone & Setup

```bash
git clone https://github.com/user/researchlab.git
cd researchlab

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit configuration (required API keys)
nano .env
```

**Required API Keys:**
- `ANTHROPIC_API_KEY` - Claude API access
- `FINNHUB_API_KEY` - Market data
- `ALPHA_VANTAGE_API_KEY` - Historical data
- `GOOGLE_CREDENTIALS_FILE` - Google Sheets integration

### 3. Database Setup

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Run migrations
alembic upgrade head

# Load initial data (optional)
python scripts/seed_database.py
```

### 4. Run Development Server

```bash
# Start the application
uvicorn src.core.app:app --reload --port 8000

# API documentation available at:
# http://localhost:8000/docs
```

### 5. Production Deployment

```bash
# Build and deploy with Docker
docker-compose -f docker-compose.production.yml up -d

# Monitor logs
docker-compose logs -f
```

---

## 📚 Usage

### REST API

Start a research project via API:

```python
import httpx

# Start research request
response = httpx.post("http://localhost:8000/api/v1/research/", json={
    "query": "Is Apple a good long-term investment given AI trends?",
    "investment_thesis": "Apple will benefit from AI integration across its ecosystem",
    "companies": [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology"
        }
    ],
    "time_horizon": 24,  # months
    "risk_tolerance": "moderate"
})

project_id = response.json()["project_id"]

# Check status
status = httpx.get(f"http://localhost:8000/api/v1/research/{project_id}/status")
print(f"Progress: {status.json()['progress_percentage']}%")

# Get results (when complete)
results = httpx.get(f"http://localhost:8000/api/v1/research/{project_id}/results")
```

### Command Line Interface

```bash
# Start interactive research session
python -m src.cli research interactive

# Run batch analysis
python -m src.cli research batch --companies AAPL,MSFT,GOOGL

# Monitor system health
python -m src.cli monitor status

# Export results to Google Sheets  
python -m src.cli export --project-id proj_123 --format sheets
```

### Configuration

ResearchLab supports both environment variables and YAML configuration:

```yaml
# config/settings.yaml
app:
  environment: production
  debug: false
  log_level: INFO

agents:
  max_concurrent: 5
  timeout_seconds: 300
  confidence_threshold: 0.7

monitoring:
  metrics_enabled: true
  health_checks: true
  alerts_enabled: true
```

---

## 🧪 Development

### Project Structure

```
researchlab/
├── src/
│   ├── agents/           # Multi-agent system
│   ├── api/             # FastAPI routes and schemas  
│   ├── core/            # Configuration, database, logging
│   ├── data/            # Data clients and models
│   ├── hitl/            # Human-in-the-loop system
│   ├── monitoring/      # Metrics and health checks
│   ├── news/            # News monitoring and alerts
│   ├── output/          # Report generation
│   ├── rate_limiting/   # API rate limiting
│   └── workflows/       # Research orchestration
├── tests/               # Comprehensive test suite
├── config/             # YAML configuration
├── scripts/            # Utility scripts
├── docker/             # Docker configurations
└── docs/               # Documentation
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest tests/test_agents.py -v
pytest tests/test_api_research.py -v
pytest tests/test_integration.py -v

# Performance tests
pytest tests/test_performance.py --benchmark-only
```

### Code Quality

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint
flake8 src/ tests/
mypy src/

# Security scan
bandit -r src/
```

### Docker Development

```bash
# Build development image
docker build -t researchlab:dev .

# Run with hot reload
docker-compose -f docker-compose.dev.yml up

# Run tests in container
docker-compose run --rm api pytest
```

---

## 📊 Monitoring & Operations

### Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Detailed status
curl http://localhost:8000/health/detailed
```

### Metrics (Prometheus)

Key metrics exposed at `/metrics`:

- `http_requests_total` - API request counts
- `agent_execution_duration_seconds` - Agent performance
- `database_operation_duration_seconds` - DB query performance
- `external_api_calls_total` - Third-party API usage
- `workflow_duration_seconds` - End-to-end research time

### Logging

Structured JSON logging with correlation IDs:

```json
{
  "timestamp": "2024-02-03T10:15:30Z",
  "level": "INFO", 
  "request_id": "req_abc123",
  "message": "Research workflow started",
  "project_id": "proj_456",
  "agent": "research_director",
  "companies": ["AAPL"]
}
```

### Rate Limiting

Multi-tier rate limiting protects against abuse:

- **Global**: 100 requests/minute per IP
- **API Key**: 1000 requests/minute per key
- **Research Endpoint**: 30 requests/hour per user
- **Workflow Execution**: 10 concurrent per account

---

## 🤝 Contributing

### Development Workflow

1. **Fork** the repository
2. **Create** feature branch (`git checkout -b feature/amazing-feature`)
3. **Write** tests for new functionality
4. **Ensure** all tests pass (`pytest`)
5. **Commit** changes (`git commit -m 'Add amazing feature'`)
6. **Push** to branch (`git push origin feature/amazing-feature`)
7. **Open** Pull Request

### Coding Standards

- **PEP 8** code style with Black formatting
- **Type hints** for all public APIs  
- **Docstrings** for modules, classes, and functions
- **100%** test coverage for new features
- **Security** review for external API integration

### Agent Development

Creating new analysis agents:

```python
from src.agents.base import BaseAgent, AgentRole

class MyCustomAgent(BaseAgent):
    role = AgentRole.CUSTOM
    
    async def analyze(self, context: ResearchContext) -> AnalysisResult:
        # Your analysis logic here
        return AnalysisResult(
            agent=self.role,
            confidence=0.85,
            findings=["Key insight 1", "Key insight 2"],
            data={"custom_metric": 42}
        )
```

---

## 📄 License & Legal

**Private & Confidential** - All rights reserved.

This software is proprietary and confidential. Unauthorized copying, distribution, or use is strictly prohibited.

---

## 📞 Support

- **Documentation**: [docs/](docs/)
- **Issues**: GitHub Issues  
- **Security**: security@researchlab.com
- **Enterprise**: enterprise@researchlab.com

---

## 🎉 Acknowledgments

Built with ❤️ using:
- [FastAPI](https://fastapi.tiangolo.com/) - The web framework
- [Anthropic](https://anthropic.com/) - AI capabilities  
- [PostgreSQL](https://postgresql.org/) - Robust data storage
- [Redis](https://redis.io/) - High-performance caching

**ResearchLab** - Democratizing institutional-grade investment research through AI.