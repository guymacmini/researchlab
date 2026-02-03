"""News analysis and relevance scoring."""

import re
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

import structlog
from textblob import TextBlob

from .monitor import NewsArticle, SourceTier

logger = structlog.get_logger()


class NewsRelevance(Enum):
    """News relevance categories."""
    CRITICAL = "critical"      # Breaking news affecting company directly
    HIGH = "high"             # Significant company/sector news
    MEDIUM = "medium"         # Related industry news
    LOW = "low"               # General market news
    IRRELEVANT = "irrelevant" # Not relevant to investment thesis


class NewsCategory(Enum):
    """News categories for classification."""
    EARNINGS = "earnings"
    ACQUISITION = "acquisition"
    MANAGEMENT = "management"
    REGULATORY = "regulatory"
    PRODUCT = "product"
    MARKET = "market"
    ANALYST = "analyst"
    LEGAL = "legal"
    OTHER = "other"


@dataclass
class CompanyMention:
    """Company mention in article."""
    company_name: str
    ticker: Optional[str]
    mention_count: int
    context_sentiment: float  # -1.0 to 1.0
    mention_positions: List[int]  # Character positions in text


@dataclass
class NewsAnalysis:
    """Comprehensive news analysis result."""
    article_id: str
    relevance: NewsRelevance
    category: NewsCategory
    confidence: float  # 0.0 - 1.0
    
    # Sentiment analysis
    overall_sentiment: float  # -1.0 to 1.0
    sentiment_confidence: float
    
    # Company analysis
    company_mentions: List[CompanyMention]
    primary_company: Optional[str]
    impact_assessment: str
    
    # Content analysis
    key_phrases: List[str]
    financial_metrics: Dict[str, Any]
    urgency_score: float
    
    # Analysis metadata
    analyzed_at: datetime
    analysis_version: str = "1.0"


class NewsAnalyzer:
    """Advanced news analysis and relevance scoring."""
    
    def __init__(self):
        self.logger = logger.bind(component="news_analyzer")
        
        # Company/ticker mappings
        self.company_ticker_map: Dict[str, str] = {}
        self.ticker_company_map: Dict[str, str] = {}
        
        # Analysis patterns
        self._initialize_patterns()
        
        # Financial keywords and phrases
        self._initialize_financial_vocabulary()
    
    def _initialize_patterns(self):
        """Initialize regex patterns for content analysis."""
        
        # Company/ticker patterns
        self.ticker_pattern = re.compile(r'\b([A-Z]{1,5})\b')
        self.company_pattern = re.compile(r'\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)*(?:\s+(?:Inc|Corp|Ltd|LLC|Co)))\b')
        
        # Financial metrics patterns
        self.revenue_pattern = re.compile(r'revenue[s]?[\s\w]*\$?([\d,]+\.?\d*)\s*(?:million|billion|M|B)', re.IGNORECASE)
        self.profit_pattern = re.compile(r'profit[s]?[\s\w]*\$?([\d,]+\.?\d*)\s*(?:million|billion|M|B)', re.IGNORECASE)
        self.eps_pattern = re.compile(r'(?:earnings per share|EPS)[\s\w]*\$?([\d,]+\.?\d*)', re.IGNORECASE)
        self.price_target_pattern = re.compile(r'price target[\s\w]*\$?([\d,]+\.?\d*)', re.IGNORECASE)
        
        # Date patterns
        self.date_pattern = re.compile(r'\b(Q[1-4]|quarter|fiscal year|FY)\s*(\d{4})?\b', re.IGNORECASE)
        
    def _initialize_financial_vocabulary(self):
        """Initialize financial vocabulary for analysis."""
        
        self.earnings_keywords = {
            'earnings', 'revenue', 'profit', 'loss', 'EPS', 'guidance',
            'forecast', 'outlook', 'quarter', 'fiscal', 'beat', 'miss',
            'consensus', 'estimates', 'analyst'
        }
        
        self.acquisition_keywords = {
            'acquisition', 'merger', 'buyout', 'takeover', 'deal',
            'acquire', 'merge', 'purchase', 'bid', 'offer'
        }
        
        self.management_keywords = {
            'CEO', 'CFO', 'CTO', 'president', 'chairman', 'board',
            'executive', 'management', 'leadership', 'appointment',
            'resignation', 'hire', 'departure'
        }
        
        self.regulatory_keywords = {
            'FDA', 'SEC', 'FTC', 'approval', 'regulation', 'compliance',
            'investigation', 'fine', 'penalty', 'lawsuit', 'settlement'
        }
        
        self.product_keywords = {
            'launch', 'release', 'product', 'service', 'innovation',
            'patent', 'technology', 'development', 'trial', 'study'
        }
        
        self.urgency_keywords = {
            'breaking', 'urgent', 'immediate', 'emergency', 'critical',
            'suspend', 'halt', 'stop', 'investigate', 'probe'
        }
        
        # Sentiment indicators
        self.positive_indicators = {
            'growth', 'increase', 'rise', 'surge', 'jump', 'soar',
            'strong', 'robust', 'healthy', 'successful', 'profit',
            'gain', 'beat', 'exceed', 'outperform', 'upgrade'
        }
        
        self.negative_indicators = {
            'decline', 'fall', 'drop', 'plunge', 'crash', 'weak',
            'poor', 'disappointing', 'loss', 'miss', 'underperform',
            'downgrade', 'warning', 'concern', 'risk', 'trouble'
        }
    
    async def analyze_article(self, article: NewsArticle, 
                            target_companies: List[str] = None,
                            target_tickers: List[str] = None) -> NewsAnalysis:
        """Perform comprehensive analysis of news article."""
        
        try:
            start_time = datetime.now()
            
            # Extract company mentions
            company_mentions = self._extract_company_mentions(article.content)
            
            # Determine relevance
            relevance = self._determine_relevance(article, company_mentions, target_companies, target_tickers)
            
            # Categorize news
            category = self._categorize_news(article.title, article.content)
            
            # Analyze sentiment
            sentiment_score, sentiment_confidence = self._analyze_sentiment(article.content)
            
            # Extract financial metrics
            financial_metrics = self._extract_financial_metrics(article.content)
            
            # Calculate urgency
            urgency_score = self._calculate_urgency_score(article)
            
            # Extract key phrases
            key_phrases = self._extract_key_phrases(article.content)
            
            # Determine primary company
            primary_company = self._identify_primary_company(company_mentions)
            
            # Generate impact assessment
            impact_assessment = self._generate_impact_assessment(article, category, sentiment_score)
            
            # Calculate overall confidence
            confidence = self._calculate_analysis_confidence(article, company_mentions, relevance)
            
            analysis = NewsAnalysis(
                article_id=article.id,
                relevance=relevance,
                category=category,
                confidence=confidence,
                overall_sentiment=sentiment_score,
                sentiment_confidence=sentiment_confidence,
                company_mentions=company_mentions,
                primary_company=primary_company,
                impact_assessment=impact_assessment,
                key_phrases=key_phrases,
                financial_metrics=financial_metrics,
                urgency_score=urgency_score,
                analyzed_at=datetime.now()
            )
            
            analysis_time = (datetime.now() - start_time).total_seconds()
            
            self.logger.info("article_analyzed",
                           article_id=article.id,
                           relevance=relevance.value,
                           category=category.value,
                           sentiment=sentiment_score,
                           analysis_time=analysis_time)
            
            return analysis
            
        except Exception as e:
            self.logger.error("article_analysis_failed", 
                            article_id=article.id, error=str(e))
            
            # Return minimal analysis on error
            return NewsAnalysis(
                article_id=article.id,
                relevance=NewsRelevance.IRRELEVANT,
                category=NewsCategory.OTHER,
                confidence=0.0,
                overall_sentiment=0.0,
                sentiment_confidence=0.0,
                company_mentions=[],
                primary_company=None,
                impact_assessment="Analysis failed",
                key_phrases=[],
                financial_metrics={},
                urgency_score=0.0,
                analyzed_at=datetime.now()
            )
    
    def _extract_company_mentions(self, text: str) -> List[CompanyMention]:
        """Extract and analyze company mentions from text."""
        
        mentions = []
        text_lower = text.lower()
        
        # Find ticker symbols
        ticker_matches = self.ticker_pattern.findall(text)
        
        # Find company names
        company_matches = self.company_pattern.findall(text)
        
        # Process ticker mentions
        for ticker in set(ticker_matches):
            if len(ticker) >= 1 and ticker.isalpha():
                count = text.count(ticker)
                positions = [i for i in range(len(text)) if text.startswith(ticker, i)]
                
                # Simple context sentiment (would use more sophisticated analysis)
                context_sentiment = self._get_context_sentiment(text, ticker)
                
                mentions.append(CompanyMention(
                    company_name=self.ticker_company_map.get(ticker, ticker),
                    ticker=ticker,
                    mention_count=count,
                    context_sentiment=context_sentiment,
                    mention_positions=positions
                ))
        
        # Process company name mentions
        for company in set(company_matches):
            if company not in [m.company_name for m in mentions]:
                count = text_lower.count(company.lower())
                positions = [i for i in range(len(text)) 
                           if text.lower().startswith(company.lower(), i)]
                
                context_sentiment = self._get_context_sentiment(text, company)
                
                mentions.append(CompanyMention(
                    company_name=company,
                    ticker=self.company_ticker_map.get(company),
                    mention_count=count,
                    context_sentiment=context_sentiment,
                    mention_positions=positions
                ))
        
        return mentions
    
    def _get_context_sentiment(self, text: str, entity: str) -> float:
        """Get sentiment of text surrounding entity mention."""
        
        # Find entity positions
        entity_lower = entity.lower()
        text_lower = text.lower()
        
        sentiment_scores = []
        
        for i in range(len(text_lower)):
            if text_lower.startswith(entity_lower, i):
                # Extract context window (50 chars before and after)
                start = max(0, i - 50)
                end = min(len(text), i + len(entity) + 50)
                context = text[start:end]
                
                # Simple sentiment based on positive/negative words
                positive_count = sum(1 for word in self.positive_indicators 
                                   if word in context.lower())
                negative_count = sum(1 for word in self.negative_indicators 
                                   if word in context.lower())
                
                if positive_count > negative_count:
                    sentiment_scores.append(0.7)
                elif negative_count > positive_count:
                    sentiment_scores.append(0.3)
                else:
                    sentiment_scores.append(0.5)
        
        if sentiment_scores:
            # Convert 0.0-1.0 to -1.0-1.0 range
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            return (avg_sentiment - 0.5) * 2
        
        return 0.0  # Neutral if no context found
    
    def _determine_relevance(self, article: NewsArticle, 
                           company_mentions: List[CompanyMention],
                           target_companies: List[str] = None,
                           target_tickers: List[str] = None) -> NewsRelevance:
        """Determine article relevance to investment analysis."""
        
        # Check for direct company matches
        mentioned_companies = {m.company_name.lower() for m in company_mentions}
        mentioned_tickers = {m.ticker.lower() for m in company_mentions if m.ticker}
        
        target_companies_lower = {c.lower() for c in (target_companies or [])}
        target_tickers_lower = {t.lower() for t in (target_tickers or [])}
        
        # Direct company/ticker match
        if (mentioned_companies & target_companies_lower or 
            mentioned_tickers & target_tickers_lower):
            
            # Check for high-impact keywords
            title_content = f"{article.title} {article.content}".lower()
            
            if any(keyword in title_content for keyword in ['acquisition', 'merger', 'bankruptcy', 'FDA approval']):
                return NewsRelevance.CRITICAL
            
            if any(keyword in title_content for keyword in ['earnings', 'revenue', 'guidance', 'CEO']):
                return NewsRelevance.HIGH
            
            return NewsRelevance.MEDIUM
        
        # Check for sector/industry relevance
        if self._is_sector_relevant(article.content, target_companies):
            return NewsRelevance.MEDIUM
        
        # General financial market news
        if any(keyword in article.content.lower() for keyword in ['stock market', 'S&P 500', 'Nasdaq', 'Dow Jones']):
            return NewsRelevance.LOW
        
        return NewsRelevance.IRRELEVANT
    
    def _is_sector_relevant(self, content: str, target_companies: List[str] = None) -> bool:
        """Check if article is relevant to target companies' sectors."""
        
        # Sector keywords (simplified)
        tech_keywords = ['technology', 'software', 'AI', 'cloud', 'semiconductor', 'tech']
        healthcare_keywords = ['healthcare', 'pharmaceutical', 'biotech', 'drug', 'medical']
        finance_keywords = ['bank', 'financial', 'insurance', 'credit', 'lending']
        
        content_lower = content.lower()
        
        # Would need actual sector mapping for target companies
        # This is a simplified check
        return any(keyword in content_lower for keyword in tech_keywords + healthcare_keywords + finance_keywords)
    
    def _categorize_news(self, title: str, content: str) -> NewsCategory:
        """Categorize news article by content type."""
        
        text = f"{title} {content}".lower()
        
        # Check categories by keyword presence
        if any(keyword in text for keyword in self.earnings_keywords):
            return NewsCategory.EARNINGS
        
        if any(keyword in text for keyword in self.acquisition_keywords):
            return NewsCategory.ACQUISITION
        
        if any(keyword in text for keyword in self.management_keywords):
            return NewsCategory.MANAGEMENT
        
        if any(keyword in text for keyword in self.regulatory_keywords):
            return NewsCategory.REGULATORY
        
        if any(keyword in text for keyword in self.product_keywords):
            return NewsCategory.PRODUCT
        
        if any(keyword in text for keyword in ['analyst', 'rating', 'price target', 'recommendation']):
            return NewsCategory.ANALYST
        
        if any(keyword in text for keyword in ['lawsuit', 'legal', 'court', 'settlement']):
            return NewsCategory.LEGAL
        
        if any(keyword in text for keyword in ['market', 'sector', 'industry', 'economy']):
            return NewsCategory.MARKET
        
        return NewsCategory.OTHER
    
    def _analyze_sentiment(self, content: str) -> Tuple[float, float]:
        """Analyze sentiment of article content."""
        
        try:
            # Use TextBlob for basic sentiment analysis
            blob = TextBlob(content)
            polarity = blob.sentiment.polarity  # -1 to 1
            subjectivity = blob.sentiment.subjectivity  # 0 to 1
            
            # Confidence is inverse of subjectivity (more objective = more confident)
            confidence = 1 - subjectivity
            
            return polarity, confidence
            
        except Exception as e:
            self.logger.warning("sentiment_analysis_failed", error=str(e))
            
            # Fallback to keyword-based sentiment
            positive_count = sum(1 for word in self.positive_indicators if word in content.lower())
            negative_count = sum(1 for word in self.negative_indicators if word in content.lower())
            
            total_indicators = positive_count + negative_count
            
            if total_indicators == 0:
                return 0.0, 0.0  # Neutral, low confidence
            
            sentiment = (positive_count - negative_count) / total_indicators
            confidence = min(1.0, total_indicators / 10)  # Higher count = higher confidence
            
            return sentiment, confidence
    
    def _extract_financial_metrics(self, content: str) -> Dict[str, Any]:
        """Extract financial metrics from article content."""
        
        metrics = {}
        
        # Revenue mentions
        revenue_matches = self.revenue_pattern.findall(content)
        if revenue_matches:
            metrics['revenue_mentions'] = revenue_matches
        
        # Profit mentions
        profit_matches = self.profit_pattern.findall(content)
        if profit_matches:
            metrics['profit_mentions'] = profit_matches
        
        # EPS mentions
        eps_matches = self.eps_pattern.findall(content)
        if eps_matches:
            metrics['eps_mentions'] = eps_matches
        
        # Price target mentions
        price_target_matches = self.price_target_pattern.findall(content)
        if price_target_matches:
            metrics['price_target_mentions'] = price_target_matches
        
        # Date/period mentions
        date_matches = self.date_pattern.findall(content)
        if date_matches:
            metrics['period_mentions'] = date_matches
        
        return metrics
    
    def _calculate_urgency_score(self, article: NewsArticle) -> float:
        """Calculate urgency score based on article characteristics."""
        
        urgency = 0.0
        
        # Source tier bonus
        tier_urgency = {
            SourceTier.TIER_1: 0.4,
            SourceTier.TIER_2: 0.3,
            SourceTier.TIER_3: 0.2,
            SourceTier.TIER_4: 0.1
        }
        urgency += tier_urgency.get(article.source_tier, 0.1)
        
        # Recency bonus
        hours_old = (datetime.now() - article.published_at).total_seconds() / 3600
        if hours_old < 1:
            urgency += 0.3
        elif hours_old < 6:
            urgency += 0.2
        elif hours_old < 24:
            urgency += 0.1
        
        # Urgency keywords
        text = f"{article.title} {article.content}".lower()
        urgency_keyword_count = sum(1 for keyword in self.urgency_keywords if keyword in text)
        urgency += min(0.3, urgency_keyword_count * 0.1)
        
        return min(1.0, urgency)
    
    def _extract_key_phrases(self, content: str, max_phrases: int = 10) -> List[str]:
        """Extract key phrases from article content."""
        
        try:
            # Simple implementation - would use more sophisticated NLP
            sentences = content.split('.')
            
            # Find sentences with financial keywords
            key_sentences = []
            
            for sentence in sentences[:20]:  # Limit to first 20 sentences
                sentence = sentence.strip()
                if len(sentence) < 20:  # Skip very short sentences
                    continue
                
                # Check for financial keywords
                sentence_lower = sentence.lower()
                keyword_count = sum(1 for keywords in [
                    self.earnings_keywords, self.acquisition_keywords, 
                    self.management_keywords, self.regulatory_keywords
                ] for keyword in keywords if keyword in sentence_lower)
                
                if keyword_count > 0:
                    key_sentences.append((sentence, keyword_count))
            
            # Sort by keyword count and take top phrases
            key_sentences.sort(key=lambda x: x[1], reverse=True)
            
            return [sentence for sentence, _ in key_sentences[:max_phrases]]
            
        except Exception as e:
            self.logger.warning("key_phrase_extraction_failed", error=str(e))
            return []
    
    def _identify_primary_company(self, company_mentions: List[CompanyMention]) -> Optional[str]:
        """Identify the primary company focus of the article."""
        
        if not company_mentions:
            return None
        
        # Sort by mention count and context sentiment
        scored_mentions = []
        
        for mention in company_mentions:
            # Score based on mention count and positive context
            score = mention.mention_count
            if mention.context_sentiment > 0:
                score *= 1.2
            elif mention.context_sentiment < -0.2:
                score *= 1.1  # Negative news still relevant
            
            scored_mentions.append((mention.company_name, score))
        
        # Return highest scoring company
        scored_mentions.sort(key=lambda x: x[1], reverse=True)
        return scored_mentions[0][0]
    
    def _generate_impact_assessment(self, article: NewsArticle, 
                                  category: NewsCategory,
                                  sentiment: float) -> str:
        """Generate impact assessment summary."""
        
        impact_parts = []
        
        # Category impact
        category_impact = {
            NewsCategory.EARNINGS: "Financial performance impact",
            NewsCategory.ACQUISITION: "Corporate structure impact",
            NewsCategory.MANAGEMENT: "Leadership change impact",
            NewsCategory.REGULATORY: "Compliance/regulatory impact",
            NewsCategory.PRODUCT: "Product/market impact",
            NewsCategory.ANALYST: "Market perception impact",
            NewsCategory.LEGAL: "Legal/financial risk impact",
            NewsCategory.MARKET: "Sector/market impact"
        }
        
        impact_parts.append(category_impact.get(category, "General impact"))
        
        # Sentiment impact
        if sentiment > 0.3:
            impact_parts.append("positive sentiment")
        elif sentiment < -0.3:
            impact_parts.append("negative sentiment")
        else:
            impact_parts.append("neutral sentiment")
        
        # Source credibility
        tier_credibility = {
            SourceTier.TIER_1: "high credibility source",
            SourceTier.TIER_2: "reliable source", 
            SourceTier.TIER_3: "moderate credibility",
            SourceTier.TIER_4: "social/unverified source"
        }
        impact_parts.append(tier_credibility.get(article.source_tier, "unknown source"))
        
        return " | ".join(impact_parts)
    
    def _calculate_analysis_confidence(self, article: NewsArticle,
                                     company_mentions: List[CompanyMention],
                                     relevance: NewsRelevance) -> float:
        """Calculate confidence in analysis results."""
        
        confidence = 0.0
        
        # Source tier confidence
        tier_confidence = {
            SourceTier.TIER_1: 0.4,
            SourceTier.TIER_2: 0.3,
            SourceTier.TIER_3: 0.2,
            SourceTier.TIER_4: 0.1
        }
        confidence += tier_confidence.get(article.source_tier, 0.1)
        
        # Company mention confidence
        if company_mentions:
            mention_confidence = min(0.3, len(company_mentions) * 0.1)
            confidence += mention_confidence
        
        # Content length confidence (more content = better analysis)
        content_length = len(article.content)
        if content_length > 1000:
            confidence += 0.2
        elif content_length > 500:
            confidence += 0.1
        
        # Relevance confidence
        relevance_confidence = {
            NewsRelevance.CRITICAL: 0.1,
            NewsRelevance.HIGH: 0.08,
            NewsRelevance.MEDIUM: 0.05,
            NewsRelevance.LOW: 0.02,
            NewsRelevance.IRRELEVANT: 0.0
        }
        confidence += relevance_confidence.get(relevance, 0.0)
        
        return min(1.0, confidence)
    
    def update_company_mappings(self, company_ticker_pairs: List[Tuple[str, str]]) -> None:
        """Update company name to ticker mappings."""
        
        for company, ticker in company_ticker_pairs:
            self.company_ticker_map[company] = ticker
            self.ticker_company_map[ticker] = company
        
        self.logger.info("company_mappings_updated", count=len(company_ticker_pairs))
    
    async def batch_analyze_articles(self, articles: List[NewsArticle],
                                   target_companies: List[str] = None,
                                   target_tickers: List[str] = None) -> List[NewsAnalysis]:
        """Analyze multiple articles in batch."""
        
        analyses = []
        
        for article in articles:
            try:
                analysis = await self.analyze_article(article, target_companies, target_tickers)
                analyses.append(analysis)
            except Exception as e:
                self.logger.error("batch_analysis_item_failed", 
                                article_id=article.id, error=str(e))
        
        self.logger.info("batch_analysis_completed",
                        total_articles=len(articles),
                        successful_analyses=len(analyses))
        
        return analyses