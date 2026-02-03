# ResearchLab: AI-Led Investment Research Platform

## Product Requirements Document

**Version:** 1.0  
**Last Updated:** February 2026

---

## Executive Summary

ResearchLab is an advanced AI-led investment research platform that mimics the analytical work of multiple hedge fund analysts. The platform enables users to define investment theses or research questions, then orchestrates specialized AI agents to conduct comprehensive, multi-dimensional analysis across global markets.

---

## Core Architecture

### Multi-Agent System

The platform operates through specialized AI agents, each representing a domain expert:

| Agent Role | Responsibility |
|------------|----------------|
| **Research Director** | Interprets user queries, asks clarifying questions, defines research scope, coordinates other agents |
| **Fundamental Analyst** | Extracts and normalizes financial metrics from earnings reports, SEC filings, and financial APIs |
| **Supply Chain Analyst** | Maps upstream/downstream dependencies, identifies second and third-order effects |
| **Sentiment Analyst** | Monitors news sources, social media, and analyst reports for sentiment shifts |
| **Quantitative Analyst** | Performs statistical analysis, correlation studies, and backtesting |
| **Risk Analyst** | Identifies potential risks, contrarian viewpoints, and thesis-breaking scenarios |

### Agent Orchestration Flow

```
User Query → Research Director → Clarifying Questions → Scope Definition
                                        ↓
                    ┌──────────────────────────────────────┐
                    │     Parallel Agent Execution          │
                    │  [Fundamental] [Supply] [Sentiment]   │
                    │     [Quantitative] [Risk]             │
                    └──────────────────────────────────────┘
                                        ↓
                            Synthesis & Human Review
                                        ↓
                              Final Output Generation
```

---

## Functional Requirements

### FR-1: Research Initialization

**FR-1.1: Intelligent Query Clarification**

Before initiating research, the system must engage in a structured dialogue to refine the research scope:

- **Investment Horizon:** Short-term (< 6 months), Medium (6-24 months), Long-term (> 2 years)
- **Geographic Scope:** US-only, Developed Markets, Emerging Markets, Global
- **Market Cap Preferences:** Micro-cap, Small-cap, Mid-cap, Large-cap, or any combination
- **Sector Constraints:** Include/exclude specific sectors
- **Risk Tolerance:** Conservative, Moderate, Aggressive
- **Analysis Depth:** Quick scan (10-15 companies), Standard (25-50), Deep dive (100+)
- **Thesis Clarity:** Ask follow-up questions to understand the causal chain the user expects

Example clarification flow:
```
User: "What US companies will be impacted most if the Fed drops rates and keeps them low for two years?"

System Questions:
1. Are you looking for companies that will benefit or be harmed (or both)?
2. Should we focus on rate-sensitive sectors (REITs, banks, utilities) or look for non-obvious plays?
3. What's your investment horizon—are you looking for immediate movers or long-term compounders?
4. Should we include non-US companies with significant US exposure?
5. Any market cap preferences? We can find alpha in small/mid-caps often overlooked by institutional research.
```

**FR-1.2: Research Plan Generation**

After clarification, generate a visible research plan including:

- List of sectors and sub-sectors to analyze
- Second and third-order effect chains to investigate
- Data sources to be queried
- Estimated completion time
- Human approval checkpoint before execution

### FR-2: Company Discovery & Screening

**FR-2.1: Universe Expansion**

The system must search beyond S&P 500 to include:

- Russell 3000 (full US market coverage)
- Russell 2000 (small-cap focus for alpha generation)
- International markets when relevant (ADRs, foreign exchanges)
- Recently IPO'd companies (past 24 months)
- Pre-IPO companies with available data (when relevant)

**FR-2.2: Multi-Factor Screening**

Screen companies using configurable criteria:

- Fundamental metrics (P/E, P/B, EV/EBITDA, Revenue Growth, FCF Yield)
- Exposure metrics (% revenue from affected segment, geographic exposure)
- Quality metrics (ROIC, debt/equity, interest coverage)
- Momentum signals (price momentum, earnings revisions, insider activity)

**FR-2.3: Second and Third-Order Effect Mapping**

For any primary thesis, automatically identify:

**Second-Order Effects:**
- Direct suppliers to affected companies
- Direct customers of affected companies
- Competitors who may gain/lose share
- Adjacent service providers

**Third-Order Effects:**
- Suppliers to the suppliers
- Infrastructure dependencies (data centers, logistics, utilities)
- Raw material and commodity exposures
- Labor market implications

Example for "AI/LLM investment thesis":
```
Primary: AI software companies (OpenAI ecosystem, enterprise AI)
Second-Order: GPU manufacturers, cloud providers, data centers
Third-Order: Electricity producers, cooling systems, copper/rare earth miners, 
             chip fabrication equipment, commercial real estate (data center REITs)
```

### FR-3: Data Extraction & Normalization

**FR-3.1: Financial Data APIs**

Integrate with free and premium financial data sources:

| Source | Data Type | Priority |
|--------|-----------|----------|
| Finnhub.io | Real-time quotes, fundamentals, news | Primary (Free tier) |
| Alpha Vantage | Historical data, technical indicators | Primary (Free tier) |
| SEC EDGAR | 10-K, 10-Q, 8-K filings | Primary (Free) |
| Yahoo Finance | Broad market data, international | Secondary (Free) |
| Financial Modeling Prep | Detailed financials, ratios | Secondary (Freemium) |
| Polygon.io | Market data, options flow | Premium |
| Refinitiv/Bloomberg | Institutional-grade data | Premium (optional) |

**FR-3.2: Earnings Report Extraction**

Automatically extract from quarterly earnings:

- Revenue (total and by segment)
- Gross margin, operating margin, net margin
- EPS (GAAP and adjusted)
- Forward guidance (if provided)
- Key metrics specific to industry (e.g., ARR for SaaS, same-store sales for retail)
- Management commentary sentiment
- Analyst Q&A key themes

**FR-3.3: Data Normalization**

Ensure cross-company comparability:

- Standardize fiscal year-ends
- Convert currencies to USD (or user-specified base)
- Adjust for stock splits and dividends
- Flag one-time items and non-recurring charges
- Normalize accounting differences (GAAP vs IFRS where applicable)

### FR-4: Google Sheets Output

**FR-4.1: Automated Spreadsheet Generation**

Create structured Google Sheets with:

**Tab 1: Executive Summary**
- Research thesis statement
- Key findings (3-5 bullet points)
- Top picks with conviction ratings
- Risk summary

**Tab 2: Company Comparison Matrix**
| Column | Description |
|--------|-------------|
| Ticker | Stock symbol |
| Company Name | Full company name |
| Market Cap | Current market capitalization |
| Sector/Industry | GICS classification |
| Thesis Relevance Score | 1-10 rating with explanation |
| Investment Thesis | 2-3 sentence explanation of why this company is relevant |
| Primary Exposure | % of business exposed to thesis |
| [Dynamic Metrics] | Relevant KPIs based on analysis type |
| Bull Case | Brief upside scenario |
| Bear Case | Brief downside scenario |
| Catalyst Timeline | Expected timing of thesis realization |

**Tab 3: Financial Deep Dive**
- Detailed financials for top 10-20 companies
- Historical trends (5-year where available)
- Peer comparison charts

**Tab 4: Supply Chain Map**
- Visual representation of company interconnections
- Dependency risk ratings

**Tab 5: News & Sentiment Tracker**
- Recent news items with sentiment scores
- Links to source articles

**FR-4.2: Sheets API Integration**

Technical requirements:

- OAuth 2.0 authentication with Google Workspace
- Real-time data refresh capability
- Conditional formatting for key thresholds
- Named ranges for easy navigation
- Version history preservation
- Shareable links with configurable permissions

### FR-5: News Monitoring System

**FR-5.1: Configurable Source Whitelist**

Default credible sources (user-configurable):

**Tier 1 - Primary Financial News:**
- Bloomberg
- Reuters
- Financial Times
- Wall Street Journal
- CNBC

**Tier 2 - Business & Market Analysis:**
- Barron's
- Investor's Business Daily
- MarketWatch
- Seeking Alpha (verified contributors only)
- The Economist

**Tier 3 - Specialized/Sector Blogs:**
- Stratechery (tech analysis)
- Byrne Hobart's The Diff
- Matt Levine's Money Stuff
- Calculated Risk (housing/economics)
- Wolf Street (contrarian macro)

**Tier 4 - Primary Sources:**
- Company investor relations pages
- SEC EDGAR filings
- Federal Reserve publications
- Industry association reports

**FR-5.2: News Processing Pipeline**

```
Source Scan (hourly) → Relevance Filter → Entity Extraction → Sentiment Analysis
                                                    ↓
                              Impact Assessment → Alert Generation → User Notification
                                                    ↓
                                         Analysis Update Trigger
```

**FR-5.3: Alert System**

Generate alerts when:

- Material news affects a tracked company (earnings, M&A, management changes)
- Macro events impact the thesis (policy changes, economic data)
- Sentiment shifts significantly (> 2 standard deviations from baseline)
- New companies emerge as relevant to the thesis
- Contrarian viewpoints gain traction

### FR-6: Human-in-the-Loop (HITL) Framework

**Critical design principle:** AI augments human judgment, never replaces it for investment decisions.

**FR-6.1: HITL Checkpoints**

| Checkpoint | Trigger | Human Action Required |
|------------|---------|----------------------|
| **Research Scope Approval** | After clarifying questions | Approve/modify research parameters before agent execution |
| **Company Shortlist Review** | After initial screening | Add/remove companies, adjust relevance scores |
| **Thesis Validation** | After draft analysis | Confirm or challenge AI-generated investment theses |
| **Data Verification** | When anomalies detected | Verify unusual data points, confirm accuracy |
| **Final Output Review** | Before spreadsheet publication | Approve final recommendations, add personal notes |
| **Ongoing Monitoring** | On significant alerts | Decide whether to update analysis or dismiss |

**FR-6.2: Confidence Scoring**

Every AI-generated insight must include:

- **Confidence Level:** High (>80%), Medium (50-80%), Low (<50%)
- **Data Quality Rating:** Based on source reliability and recency
- **Consensus Alignment:** Whether the view aligns with or contradicts market consensus
- **Uncertainty Flags:** Specific areas where human judgment is especially needed

**FR-6.3: Collaborative Annotation**

Enable users to:

- Add notes and commentary to any data point
- Override AI-generated scores with explanations
- Mark items for follow-up research
- Share analyses with team members for collaborative review
- Track decision audit trail (who changed what, when)

**FR-6.4: Feedback Loop**

Capture user corrections to improve future analyses:

- Log all human overrides with reasoning
- Track which AI predictions were accurate vs inaccurate
- Use feedback to fine-tune relevance scoring
- Generate periodic accuracy reports

**FR-6.5: Explainability Requirements**

All AI outputs must include:

- Source attribution (which data sources informed the conclusion)
- Reasoning chain (step-by-step logic)
- Alternative interpretations considered
- Key assumptions that could invalidate the analysis

---

## Non-Functional Requirements

### NFR-1: Performance

- Initial research results within 5 minutes for standard scope
- Full analysis completion within 30 minutes for comprehensive research
- News monitoring latency < 15 minutes from publication
- API rate limiting compliance with all data sources
- Graceful degradation when data sources unavailable

### NFR-2: Scalability

- Support concurrent research projects (minimum 10 per user)
- Handle company universes up to 5,000 securities
- Store historical analyses for backtesting and comparison

### NFR-3: Security & Compliance

- SOC 2 Type II compliance pathway
- Encryption at rest and in transit
- No storage of trading signals or recommendations that constitute investment advice
- Clear disclaimers that outputs are for research purposes only
- Audit logging for all user actions and AI decisions

### NFR-4: Data Freshness

| Data Type | Refresh Frequency |
|-----------|-------------------|
| Stock prices | Real-time during market hours |
| Financial statements | Within 24 hours of filing |
| News articles | Hourly scan |
| Analyst estimates | Daily |
| Economic indicators | As released |

---

## Technical Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend Layer                            │
│   [Web App - React/Next.js]  [Mobile - React Native (future)]   │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway Layer                           │
│         [Authentication]  [Rate Limiting]  [Routing]            │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                           │
│   [Research Director Agent]  [Task Queue]  [State Management]   │
└─────────────────────────────────────────────────────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│  Specialist       │ │  Data Integration │ │  Output           │
│  Agents           │ │  Layer            │ │  Generation       │
│                   │ │                   │ │                   │
│ • Fundamental     │ │ • Finnhub         │ │ • Google Sheets   │
│ • Supply Chain    │ │ • Alpha Vantage   │ │ • PDF Reports     │
│ • Sentiment       │ │ • SEC EDGAR       │ │ • Alert System    │
│ • Quantitative    │ │ • News APIs       │ │ • Webhooks        │
│ • Risk            │ │ • Web Scraping    │ │                   │
└───────────────────┘ └───────────────────┘ └───────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data Persistence Layer                      │
│  [PostgreSQL - Core Data]  [Redis - Cache]  [S3 - Documents]   │
│  [Vector DB - Semantic Search]  [TimescaleDB - Time Series]    │
└─────────────────────────────────────────────────────────────────┘
```

### LLM Integration

- **Primary Model:** Claude (via Anthropic API) for complex reasoning and analysis
- **Supporting Models:** GPT-4 for redundancy, specialized financial models where available
- **Context Management:** Intelligent chunking of financial documents, semantic caching
- **Prompt Engineering:** Version-controlled prompt templates per agent type

### API Integrations

```python
# Required API integrations
FINANCIAL_APIS = {
    "finnhub": {
        "base_url": "https://finnhub.io/api/v1",
        "endpoints": ["quote", "company-profile2", "company-news", "financials-reported"],
        "rate_limit": "60/minute (free tier)"
    },
    "alpha_vantage": {
        "base_url": "https://www.alphavantage.co/query",
        "endpoints": ["TIME_SERIES_DAILY", "OVERVIEW", "INCOME_STATEMENT"],
        "rate_limit": "5/minute (free tier)"
    },
    "sec_edgar": {
        "base_url": "https://data.sec.gov",
        "endpoints": ["submissions", "company-facts"],
        "rate_limit": "10/second"
    },
    "google_sheets": {
        "scopes": ["spreadsheets", "drive"],
        "auth": "OAuth 2.0"
    }
}
```

---

## User Interface Requirements

### UI-1: Research Dashboard

- Active research projects overview
- Quick-start templates for common research types
- Recent analyses with one-click refresh
- Portfolio watchlist integration

### UI-2: Research Configuration

- Interactive scope definition wizard
- Visual sector/geography selector
- Drag-and-drop priority ordering
- Save/load research templates

### UI-3: Analysis Viewer

- Split view: AI summary + detailed data
- Interactive charts with drill-down
- Side-by-side company comparison
- Export options (Sheets, PDF, CSV)

### UI-4: Alert Center

- Prioritized alert feed
- Snooze and dismiss functionality
- Alert rule configuration
- Integration with Slack/Email/SMS

### UI-5: HITL Interaction

- Clear visual indicators for checkpoints requiring human input
- Inline annotation and commenting
- Approval workflows with audit trail
- Confidence calibration interface (was AI right?)

---

## Success Metrics

### Primary KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Research completion rate | >95% | % of initiated research that completes successfully |
| Time to first insight | <5 min | Time from query to initial results |
| Data accuracy | >98% | Spot-check validation of extracted financials |
| User override rate | 10-20% | Human corrections (too low = not engaged, too high = poor AI) |
| Alpha generation* | Outperform benchmark | Tracked paper portfolios based on research (with disclaimers) |

*Tracked for internal validation only, not marketed as performance claims

### Secondary KPIs

- User engagement (sessions per week, time in platform)
- Research depth (companies analyzed per session)
- Alert response rate
- Feature adoption rates
- User feedback scores

---

## Phased Rollout

### Phase 1: Foundation (Months 1-3)

- Core multi-agent architecture
- Finnhub + Alpha Vantage integration
- Basic Google Sheets output
- Single-user research workflow
- Manual news source integration

### Phase 2: Enhancement (Months 4-6)

- SEC EDGAR parsing
- Automated news monitoring
- Supply chain mapping
- Full HITL framework
- Team collaboration features

### Phase 3: Scale (Months 7-9)

- International market coverage
- Premium data source integrations
- Advanced backtesting
- API for external integrations
- Mobile application

### Phase 4: Intelligence (Months 10-12)

- Predictive analytics
- Cross-research pattern detection
- Personalized research recommendations
- Automated thesis evolution tracking

---

## Risk Considerations

### Technical Risks

- API rate limits constraining real-time analysis
- LLM hallucination in financial data (mitigated by verification against source APIs)
- Data source reliability and uptime

### Business Risks

- Regulatory scrutiny around "investment advice" characterization
- Competition from established financial data providers
- User trust in AI-generated financial analysis

### Mitigation Strategies

- Clear disclaimers on all outputs
- Robust HITL framework emphasizing human decision-making
- Multi-source data validation
- Comprehensive audit trails

---

## Appendix A: Example Research Flow

**User Query:** "Which companies will benefit most from increased infrastructure spending in the US over the next 3 years?"

**Clarification Questions:**
1. Should we focus on direct beneficiaries (construction, materials) or include indirect plays (equipment financing, software)?
2. Any preference between established large-caps and higher-growth small/mid-caps?
3. Should we include companies with international infrastructure exposure or US-only?
4. Are there specific infrastructure categories of interest (roads, bridges, broadband, energy grid)?

**Research Plan Generated:**
- Primary: Construction & engineering firms, building materials
- Second-order: Heavy equipment manufacturers, equipment rental, construction software
- Third-order: Steel/cement producers, aggregate miners, trucking/logistics
- Monitoring: Government spending announcements, project awards, material price indices

**Output:** Google Sheet with 47 companies across 8 sub-sectors, ranked by infrastructure revenue exposure and growth potential.

---

## Appendix B: News Source Configuration Schema

```json
{
  "news_sources": {
    "tier_1": {
      "sources": ["bloomberg.com", "reuters.com", "ft.com", "wsj.com"],
      "trust_weight": 1.0,
      "scan_frequency": "hourly"
    },
    "tier_2": {
      "sources": ["barrons.com", "investors.com", "marketwatch.com"],
      "trust_weight": 0.8,
      "scan_frequency": "hourly"
    },
    "tier_3": {
      "sources": ["stratechery.com", "thediff.co"],
      "trust_weight": 0.7,
      "scan_frequency": "daily"
    },
    "user_custom": {
      "sources": [],
      "trust_weight": 0.5,
      "scan_frequency": "configurable"
    }
  },
  "excluded_sources": ["unreliable-site.com"],
  "keyword_filters": {
    "required": [],
    "excluded": ["sponsored", "advertisement"]
  }
}
```

---

## Appendix C: Financial Metrics Library

### Universal Metrics (all companies)
- Market Cap, Enterprise Value
- P/E, Forward P/E, PEG
- P/B, P/S, EV/EBITDA
- Revenue, Revenue Growth (YoY, QoQ)
- Gross Margin, Operating Margin, Net Margin
- ROE, ROA, ROIC
- Debt/Equity, Interest Coverage
- Free Cash Flow, FCF Yield
- Dividend Yield, Payout Ratio

### Sector-Specific Metrics
- **SaaS:** ARR, NRR, CAC Payback, Rule of 40
- **Banks:** NIM, Efficiency Ratio, NPL Ratio, CET1
- **Retail:** Same-Store Sales, Inventory Turnover, Sales/Sq Ft
- **REITs:** FFO, AFFO, Cap Rate, Occupancy
- **Insurance:** Combined Ratio, Loss Ratio, Premium Growth

---

*Document maintained by: Product Team*  
*For questions: [internal contact]*
