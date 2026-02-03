"""Sentiment Analyst agent for news sentiment scoring and analysis."""

from typing import Dict, List, Any, Optional, Tuple
import asyncio
from datetime import datetime, timedelta
import json
import re
import statistics
from collections import defaultdict, Counter

import structlog
import anthropic
import httpx

from src.core.config import settings
from src.core.database import DatabaseManager
from src.data.models import Company, CompanyAnalysis
from src.data.clients.finnhub_client import FinnhubClient
from .base import BaseAgent, AgentRole, AgentResult


class SentimentAnalystAgent(BaseAgent):
    """
    Sentiment Analyst agent responsible for:
    - Analyzing sentiment from news articles and social media
    - Scoring sentiment trends over time
    - Identifying sentiment shifts and catalysts
    - Evaluating news source credibility and reach
    - Tracking narrative changes and themes
    - Providing sentiment-based investment signals
    """
    
    role = AgentRole.SENTIMENT_ANALYST
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.client = anthropic.Anthropic(api_key=settings.api.anthropic_api_key)
        self.finnhub_client = FinnhubClient()
        self.model = settings.agents.get('sentiment_analyst_model', 'claude-3-sonnet-20240229')
        
        # Sentiment scoring parameters
        self.sentiment_scale = [-1.0, 1.0]  # -1 (very negative) to +1 (very positive)
        self.confidence_scale = [0.0, 1.0]  # 0 (no confidence) to 1 (very confident)
        
        # News source credibility weights (higher = more credible)
        self.source_credibility = {
            'reuters': 0.95,
            'bloomberg': 0.95,
            'wall street journal': 0.9,
            'financial times': 0.9,
            'cnbc': 0.85,
            'marketwatch': 0.8,
            'yahoo finance': 0.75,
            'seeking alpha': 0.7,
            'benzinga': 0.65,
            'motley fool': 0.6,
            'default': 0.5  # Unknown sources
        }
        
        # Time decay weights for recent vs older news
        self.time_weights = {
            'today': 1.0,
            'yesterday': 0.8,
            'this_week': 0.6,
            'this_month': 0.4,
            'older': 0.2
        }
        
        # Sentiment categories for classification
        self.sentiment_categories = {
            'earnings': 'Earnings and financial performance',
            'product': 'Product launches and updates',
            'management': 'Management changes and strategy',
            'regulation': 'Regulatory and legal news',
            'market': 'Market conditions and industry trends',
            'merger': 'M&A and corporate actions',
            'partnership': 'Partnerships and collaborations',
            'innovation': 'R&D and innovation',
            'competition': 'Competitive landscape',
            'general': 'General company news'
        }
        
    async def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """Validate that required inputs are present."""
        required_fields = ['project_id', 'companies']
        
        for field in required_fields:
            if field not in context:
                self.logger.error("missing_required_field", field=field)
                return False
        
        companies = context.get('companies', [])
        if not companies:
            self.logger.error("no_companies_provided")
            return False
            
        return True
    
    async def analyze(self, context: Dict[str, Any]) -> AgentResult:
        """Perform sentiment analysis of companies and market conditions."""
        
        self.logger.info("sentiment_analysis_started", 
                        companies_count=len(context.get('companies', [])))
        
        try:
            companies = context.get('companies', [])
            project_id = context['project_id']
            investment_thesis = context.get('investment_thesis', '')
            time_horizon = context.get('time_horizon', 30)  # days
            
            # Analyze sentiment for each company
            company_analyses = []
            overall_market_sentiment = {}
            
            for company in companies:
                symbol = company.get('symbol')
                if not symbol:
                    continue
                    
                self.logger.info("analyzing_company_sentiment", symbol=symbol)
                
                # Get news and sentiment data
                news_sentiment = await self._analyze_news_sentiment(symbol, time_horizon)
                
                # Get social media sentiment if available
                social_sentiment = await self._analyze_social_sentiment(symbol, time_horizon)
                
                # Combine and weight different sentiment sources
                combined_sentiment = await self._combine_sentiment_sources(
                    news_sentiment, social_sentiment, investment_thesis
                )
                
                # Analyze sentiment trends and patterns
                trend_analysis = await self._analyze_sentiment_trends(
                    symbol, news_sentiment, time_horizon
                )
                
                company_analyses.append({
                    'symbol': symbol,
                    'company_name': company.get('name', symbol),
                    'news_sentiment': news_sentiment,
                    'social_sentiment': social_sentiment,
                    'combined_sentiment': combined_sentiment,
                    'trend_analysis': trend_analysis,
                    'sentiment_score': combined_sentiment.get('overall_score', 0.0),
                    'confidence': combined_sentiment.get('confidence', 0.5)
                })
            
            # Analyze market-wide sentiment patterns
            market_sentiment = await self._analyze_market_sentiment(
                company_analyses, investment_thesis
            )
            
            # Generate sentiment-based signals and alerts
            signals = await self._generate_sentiment_signals(
                company_analyses, market_sentiment, investment_thesis
            )
            
            # Calculate overall confidence
            confidence = await self._calculate_confidence(company_analyses, market_sentiment)
            
            result_data = {
                'company_analyses': company_analyses,
                'market_sentiment': market_sentiment,
                'sentiment_signals': signals,
                'analysis_timestamp': datetime.now().isoformat(),
                'time_horizon_days': time_horizon,
                'methodology': self._get_methodology_summary()
            }
            
            self.logger.info("sentiment_analysis_completed", 
                           confidence=confidence,
                           companies_analyzed=len(company_analyses),
                           avg_sentiment=statistics.mean([c['sentiment_score'] for c in company_analyses]))
            
            return AgentResult(
                agent=self.role,
                success=True,
                data=result_data,
                confidence=confidence,
                sources=self._get_data_sources(),
                reasoning=self._generate_analysis_reasoning(result_data),
                errors=None
            )
            
        except Exception as e:
            self.logger.error("sentiment_analysis_failed", error=str(e))
            return AgentResult(
                agent=self.role,
                success=False,
                data={},
                confidence=0.0,
                sources=[],
                reasoning=f"Analysis failed: {str(e)}",
                errors=[str(e)]
            )
    
    async def _analyze_news_sentiment(self, symbol: str, time_horizon: int) -> Dict[str, Any]:
        """Analyze sentiment from news articles about a company."""
        
        try:
            # Get recent news
            news_data = await self.finnhub_client.get_company_news(
                symbol, days_back=time_horizon
            )
            
            if not news_data:
                return {
                    'articles_analyzed': 0,
                    'overall_sentiment': 0.0,
                    'confidence': 0.0,
                    'sentiment_by_category': {},
                    'sentiment_over_time': {},
                    'key_themes': [],
                    'source_breakdown': {}
                }
            
            # Analyze sentiment for each article
            article_sentiments = []
            sentiment_by_date = defaultdict(list)
            sentiment_by_source = defaultdict(list)
            sentiment_by_category = defaultdict(list)
            
            for article in news_data[:50]:  # Limit to recent 50 articles
                sentiment_data = await self._analyze_article_sentiment(article, symbol)
                
                if sentiment_data:
                    article_sentiments.append(sentiment_data)
                    
                    # Group by date
                    article_date = datetime.fromtimestamp(article.get('datetime', 0)).date()
                    sentiment_by_date[str(article_date)].append(sentiment_data['sentiment_score'])
                    
                    # Group by source
                    source = article.get('source', 'unknown').lower()
                    sentiment_by_source[source].append(sentiment_data['sentiment_score'])
                    
                    # Group by category
                    category = sentiment_data.get('category', 'general')
                    sentiment_by_category[category].append(sentiment_data['sentiment_score'])
            
            if not article_sentiments:
                return {
                    'articles_analyzed': 0,
                    'overall_sentiment': 0.0,
                    'confidence': 0.0,
                    'sentiment_by_category': {},
                    'sentiment_over_time': {},
                    'key_themes': [],
                    'source_breakdown': {}
                }
            
            # Calculate weighted overall sentiment
            overall_sentiment = await self._calculate_weighted_sentiment(article_sentiments)
            
            # Calculate sentiment over time
            sentiment_over_time = {
                date: statistics.mean(scores) 
                for date, scores in sentiment_by_date.items()
            }
            
            # Calculate sentiment by category
            category_sentiment = {
                category: {
                    'average_sentiment': statistics.mean(scores),
                    'article_count': len(scores)
                }
                for category, scores in sentiment_by_category.items()
            }
            
            # Source breakdown with credibility weighting
            source_breakdown = {
                source: {
                    'average_sentiment': statistics.mean(scores),
                    'article_count': len(scores),
                    'credibility_weight': self.source_credibility.get(source, self.source_credibility['default'])
                }
                for source, scores in sentiment_by_source.items()
            }
            
            # Extract key themes
            key_themes = await self._extract_sentiment_themes(article_sentiments)
            
            return {
                'articles_analyzed': len(article_sentiments),
                'overall_sentiment': overall_sentiment['score'],
                'confidence': overall_sentiment['confidence'],
                'sentiment_by_category': category_sentiment,
                'sentiment_over_time': sentiment_over_time,
                'key_themes': key_themes,
                'source_breakdown': source_breakdown
            }
            
        except Exception as e:
            self.logger.error("news_sentiment_analysis_error", symbol=symbol, error=str(e))
            return {
                'articles_analyzed': 0,
                'overall_sentiment': 0.0,
                'confidence': 0.0,
                'sentiment_by_category': {},
                'sentiment_over_time': {},
                'key_themes': [],
                'source_breakdown': {},
                'error': str(e)
            }
    
    async def _analyze_article_sentiment(self, article: Dict, symbol: str) -> Optional[Dict]:
        """Analyze sentiment of a single news article."""
        
        try:
            headline = article.get('headline', '')
            summary = article.get('summary', '')
            source = article.get('source', 'unknown')
            
            if not headline and not summary:
                return None
            
            # Combine headline and summary for analysis
            text_content = f"Headline: {headline}\n\nSummary: {summary}"
            
            prompt = f"""
            Analyze the sentiment of this news article about {symbol}:

            {text_content}

            Please provide:
            1. Sentiment score from -1.0 (very negative) to +1.0 (very positive)
            2. Confidence in the sentiment assessment (0.0 to 1.0)
            3. Primary category of news (earnings, product, management, regulation, market, merger, partnership, innovation, competition, general)
            4. Key sentiment drivers (brief list of positive/negative factors)
            5. Potential impact on stock price (low, medium, high)
            6. Emotional tone (objective, optimistic, pessimistic, uncertain, alarming, celebratory)

            Consider:
            - Context and implications for the company
            - Language tone and word choice
            - Forward-looking statements vs historical facts
            - Market context and timing
            - Source credibility and potential bias

            Return as JSON:
            {{
                "sentiment_score": <float>,
                "confidence": <float>,
                "category": "<category>",
                "sentiment_drivers": {{
                    "positive": ["<factor1>", "<factor2>"],
                    "negative": ["<factor1>", "<factor2>"]
                }},
                "potential_impact": "<low/medium/high>",
                "emotional_tone": "<tone>",
                "reasoning": "<brief explanation of sentiment assessment>"
            }}
            """
            
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                sentiment_data = json.loads(json_match.group())
                
                # Add metadata
                sentiment_data.update({
                    'headline': headline,
                    'source': source,
                    'timestamp': article.get('datetime', 0),
                    'url': article.get('url', ''),
                    'credibility_weight': self.source_credibility.get(source.lower(), self.source_credibility['default'])
                })
                
                return sentiment_data
            else:
                self.logger.warning("no_json_in_sentiment_response", symbol=symbol)
                return None
                
        except Exception as e:
            self.logger.error("article_sentiment_analysis_error", 
                            symbol=symbol, source=article.get('source', ''), error=str(e))
            return None
    
    async def _analyze_social_sentiment(self, symbol: str, time_horizon: int) -> Dict[str, Any]:
        """Analyze sentiment from social media sources (placeholder for future implementation)."""
        
        # Placeholder - would integrate with Twitter API, Reddit API, etc.
        # For now, return empty structure
        
        return {
            'platform_breakdown': {},
            'overall_sentiment': 0.0,
            'confidence': 0.0,
            'volume_metrics': {
                'mentions_count': 0,
                'engagement_rate': 0.0,
                'viral_posts': []
            },
            'trending_topics': [],
            'influencer_sentiment': {},
            'note': 'Social media sentiment analysis not yet implemented'
        }
    
    async def _combine_sentiment_sources(self, news_sentiment: Dict, 
                                       social_sentiment: Dict, 
                                       investment_thesis: str) -> Dict[str, Any]:
        """Combine sentiment from different sources with appropriate weighting."""
        
        # Weight news sentiment more heavily than social media for now
        news_weight = 0.8
        social_weight = 0.2
        
        news_score = news_sentiment.get('overall_sentiment', 0.0)
        news_conf = news_sentiment.get('confidence', 0.0)
        social_score = social_sentiment.get('overall_sentiment', 0.0)
        social_conf = social_sentiment.get('confidence', 0.0)
        
        # Weighted combination
        if news_conf > 0 and social_conf > 0:
            combined_score = (news_score * news_weight + social_score * social_weight)
            combined_confidence = (news_conf * news_weight + social_conf * social_weight)
        elif news_conf > 0:
            combined_score = news_score
            combined_confidence = news_conf * 0.9  # Reduce confidence when only one source
        elif social_conf > 0:
            combined_score = social_score
            combined_confidence = social_conf * 0.9
        else:
            combined_score = 0.0
            combined_confidence = 0.0
        
        # Analyze thesis alignment
        thesis_alignment = await self._analyze_thesis_sentiment_alignment(
            news_sentiment, social_sentiment, investment_thesis
        )
        
        return {
            'overall_score': combined_score,
            'confidence': combined_confidence,
            'news_weight': news_weight,
            'social_weight': social_weight,
            'thesis_alignment': thesis_alignment,
            'source_breakdown': {
                'news': {'score': news_score, 'confidence': news_conf},
                'social': {'score': social_score, 'confidence': social_conf}
            }
        }
    
    async def _analyze_sentiment_trends(self, symbol: str, news_sentiment: Dict, 
                                      time_horizon: int) -> Dict[str, Any]:
        """Analyze sentiment trends and patterns over time."""
        
        sentiment_over_time = news_sentiment.get('sentiment_over_time', {})
        
        if len(sentiment_over_time) < 2:
            return {
                'trend_direction': 'insufficient_data',
                'trend_strength': 0.0,
                'recent_shift': False,
                'volatility': 0.0,
                'momentum': 'neutral'
            }
        
        # Sort by date and calculate trend
        sorted_dates = sorted(sentiment_over_time.keys())
        sentiment_values = [sentiment_over_time[date] for date in sorted_dates]
        
        # Calculate trend direction and strength
        if len(sentiment_values) >= 3:
            recent_trend = sentiment_values[-3:]
            older_values = sentiment_values[:-3] if len(sentiment_values) > 3 else sentiment_values[:-1]
            
            recent_avg = statistics.mean(recent_trend)
            older_avg = statistics.mean(older_values) if older_values else recent_avg
            
            trend_change = recent_avg - older_avg
            trend_direction = 'improving' if trend_change > 0.1 else 'declining' if trend_change < -0.1 else 'stable'
            trend_strength = abs(trend_change)
            
        else:
            trend_change = sentiment_values[-1] - sentiment_values[0]
            trend_direction = 'improving' if trend_change > 0 else 'declining' if trend_change < 0 else 'stable'
            trend_strength = abs(trend_change)
        
        # Check for recent sentiment shifts
        recent_shift = False
        if len(sentiment_values) >= 3:
            latest_change = abs(sentiment_values[-1] - sentiment_values[-2])
            avg_change = statistics.mean([
                abs(sentiment_values[i] - sentiment_values[i-1]) 
                for i in range(1, len(sentiment_values))
            ])
            recent_shift = latest_change > avg_change * 1.5
        
        # Calculate sentiment volatility
        volatility = statistics.stdev(sentiment_values) if len(sentiment_values) > 1 else 0.0
        
        # Determine momentum
        if trend_direction == 'improving' and trend_strength > 0.2:
            momentum = 'bullish'
        elif trend_direction == 'declining' and trend_strength > 0.2:
            momentum = 'bearish'
        else:
            momentum = 'neutral'
        
        return {
            'trend_direction': trend_direction,
            'trend_strength': round(trend_strength, 3),
            'recent_shift': recent_shift,
            'volatility': round(volatility, 3),
            'momentum': momentum,
            'data_points': len(sentiment_values),
            'time_series': dict(zip(sorted_dates, sentiment_values))
        }
    
    async def _analyze_market_sentiment(self, company_analyses: List[Dict], 
                                      investment_thesis: str) -> Dict[str, Any]:
        """Analyze market-wide sentiment patterns across all companies."""
        
        if not company_analyses:
            return {'error': 'No company analyses provided'}
        
        # Calculate market-wide metrics
        sentiment_scores = [c['sentiment_score'] for c in company_analyses]
        confidence_scores = [c['confidence'] for c in company_analyses]
        
        market_sentiment = statistics.mean(sentiment_scores)
        market_confidence = statistics.mean(confidence_scores)
        sentiment_dispersion = statistics.stdev(sentiment_scores) if len(sentiment_scores) > 1 else 0.0
        
        # Analyze sentiment distribution
        positive_count = sum(1 for s in sentiment_scores if s > 0.1)
        negative_count = sum(1 for s in sentiment_scores if s < -0.1)
        neutral_count = len(sentiment_scores) - positive_count - negative_count
        
        # Market sentiment regime
        if market_sentiment > 0.3:
            regime = 'bullish'
        elif market_sentiment < -0.3:
            regime = 'bearish'
        elif sentiment_dispersion < 0.3:
            regime = 'consensus'
        else:
            regime = 'mixed'
        
        # Identify sentiment leaders and laggards
        sorted_companies = sorted(
            company_analyses, 
            key=lambda c: c['sentiment_score'], 
            reverse=True
        )
        
        sentiment_leaders = sorted_companies[:3]
        sentiment_laggards = sorted_companies[-3:]
        
        # Cross-company sentiment themes
        all_themes = []
        for company in company_analyses:
            themes = company.get('news_sentiment', {}).get('key_themes', [])
            all_themes.extend(themes)
        
        theme_frequency = Counter(all_themes)
        common_themes = theme_frequency.most_common(5)
        
        return {
            'market_sentiment_score': round(market_sentiment, 3),
            'market_confidence': round(market_confidence, 3),
            'sentiment_dispersion': round(sentiment_dispersion, 3),
            'sentiment_regime': regime,
            'distribution': {
                'positive': positive_count,
                'negative': negative_count,
                'neutral': neutral_count
            },
            'sentiment_leaders': [
                {'symbol': c['symbol'], 'sentiment': c['sentiment_score']} 
                for c in sentiment_leaders
            ],
            'sentiment_laggards': [
                {'symbol': c['symbol'], 'sentiment': c['sentiment_score']} 
                for c in sentiment_laggards
            ],
            'common_themes': [{'theme': theme, 'frequency': freq} for theme, freq in common_themes]
        }
    
    async def _generate_sentiment_signals(self, company_analyses: List[Dict], 
                                        market_sentiment: Dict, 
                                        investment_thesis: str) -> Dict[str, Any]:
        """Generate sentiment-based investment signals and alerts."""
        
        signals = {
            'buy_signals': [],
            'sell_signals': [],
            'watch_alerts': [],
            'thesis_support': [],
            'thesis_risk': []
        }
        
        for company in company_analyses:
            symbol = company['symbol']
            sentiment_score = company['sentiment_score']
            confidence = company['confidence']
            trend_analysis = company.get('trend_analysis', {})
            
            # Buy signals
            if (sentiment_score > 0.5 and confidence > 0.7 and 
                trend_analysis.get('momentum') == 'bullish'):
                signals['buy_signals'].append({
                    'symbol': symbol,
                    'reason': 'Strong positive sentiment with bullish momentum',
                    'sentiment_score': sentiment_score,
                    'confidence': confidence
                })
            
            # Sell signals
            if (sentiment_score < -0.5 and confidence > 0.7 and 
                trend_analysis.get('momentum') == 'bearish'):
                signals['sell_signals'].append({
                    'symbol': symbol,
                    'reason': 'Strong negative sentiment with bearish momentum',
                    'sentiment_score': sentiment_score,
                    'confidence': confidence
                })
            
            # Watch alerts for sentiment shifts
            if trend_analysis.get('recent_shift') and confidence > 0.6:
                signals['watch_alerts'].append({
                    'symbol': symbol,
                    'reason': 'Recent sentiment shift detected',
                    'trend_direction': trend_analysis.get('trend_direction'),
                    'sentiment_score': sentiment_score
                })
        
        # Market-level signals
        market_regime = market_sentiment.get('sentiment_regime', 'mixed')
        
        if market_regime == 'bullish' and market_sentiment.get('market_confidence', 0) > 0.7:
            signals['thesis_support'].append({
                'signal': 'market_tailwind',
                'description': 'Positive market sentiment supports thesis',
                'market_sentiment': market_sentiment.get('market_sentiment_score', 0)
            })
        elif market_regime == 'bearish' and market_sentiment.get('market_confidence', 0) > 0.7:
            signals['thesis_risk'].append({
                'signal': 'market_headwind',
                'description': 'Negative market sentiment creates thesis risk',
                'market_sentiment': market_sentiment.get('market_sentiment_score', 0)
            })
        
        return signals
    
    async def _calculate_weighted_sentiment(self, article_sentiments: List[Dict]) -> Dict[str, float]:
        """Calculate weighted overall sentiment from individual articles."""
        
        if not article_sentiments:
            return {'score': 0.0, 'confidence': 0.0}
        
        total_weight = 0.0
        weighted_score = 0.0
        weighted_confidence = 0.0
        
        for article in article_sentiments:
            # Get base weights
            credibility_weight = article.get('credibility_weight', 0.5)
            article_confidence = article.get('confidence', 0.5)
            
            # Time decay weight
            article_time = datetime.fromtimestamp(article.get('timestamp', 0))
            days_old = (datetime.now() - article_time).days
            
            if days_old <= 1:
                time_weight = self.time_weights['today']
            elif days_old <= 2:
                time_weight = self.time_weights['yesterday']
            elif days_old <= 7:
                time_weight = self.time_weights['this_week']
            elif days_old <= 30:
                time_weight = self.time_weights['this_month']
            else:
                time_weight = self.time_weights['older']
            
            # Impact weight based on potential impact
            impact_weight = {
                'high': 1.0,
                'medium': 0.7,
                'low': 0.4
            }.get(article.get('potential_impact', 'low'), 0.4)
            
            # Combined weight
            combined_weight = credibility_weight * time_weight * impact_weight * article_confidence
            
            weighted_score += article.get('sentiment_score', 0.0) * combined_weight
            weighted_confidence += article_confidence * combined_weight
            total_weight += combined_weight
        
        if total_weight > 0:
            return {
                'score': weighted_score / total_weight,
                'confidence': min(weighted_confidence / total_weight, 1.0)
            }
        else:
            return {'score': 0.0, 'confidence': 0.0}
    
    async def _extract_sentiment_themes(self, article_sentiments: List[Dict]) -> List[str]:
        """Extract key sentiment themes from article analysis."""
        
        all_drivers = []
        
        for article in article_sentiments:
            drivers = article.get('sentiment_drivers', {})
            all_drivers.extend(drivers.get('positive', []))
            all_drivers.extend(drivers.get('negative', []))
        
        if not all_drivers:
            return []
        
        # Count theme frequency and return most common
        theme_counts = Counter(all_drivers)
        return [theme for theme, count in theme_counts.most_common(10)]
    
    async def _analyze_thesis_sentiment_alignment(self, news_sentiment: Dict, 
                                                social_sentiment: Dict, 
                                                investment_thesis: str) -> Dict[str, Any]:
        """Analyze how well sentiment aligns with investment thesis."""
        
        if not investment_thesis.strip():
            return {
                'alignment_score': 0.0,
                'confidence': 0.0,
                'supporting_themes': [],
                'conflicting_themes': []
            }
        
        # Get key themes from sentiment analysis
        news_themes = news_sentiment.get('key_themes', [])
        
        # Use LLM to assess alignment
        prompt = f"""
        Investment Thesis: {investment_thesis}
        
        Sentiment Themes from News: {', '.join(news_themes)}
        
        Assess how well the current sentiment themes align with the investment thesis:
        1. Alignment score from -1.0 (completely contradicts) to +1.0 (strongly supports)
        2. Confidence in assessment (0.0 to 1.0)
        3. Supporting themes that align with thesis
        4. Conflicting themes that contradict thesis
        5. Brief explanation
        
        Return as JSON:
        {{
            "alignment_score": <float>,
            "confidence": <float>,
            "supporting_themes": ["<theme1>", "<theme2>"],
            "conflicting_themes": ["<theme1>", "<theme2>"],
            "explanation": "<brief explanation>"
        }}
        """
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    'alignment_score': 0.0,
                    'confidence': 0.0,
                    'supporting_themes': [],
                    'conflicting_themes': []
                }
                
        except Exception as e:
            self.logger.error("thesis_alignment_analysis_error", error=str(e))
            return {
                'alignment_score': 0.0,
                'confidence': 0.0,
                'supporting_themes': [],
                'conflicting_themes': []
            }
    
    async def _calculate_confidence(self, company_analyses: List[Dict], 
                                  market_sentiment: Dict) -> float:
        """Calculate overall confidence in sentiment analysis."""
        
        if not company_analyses:
            return 0.1
        
        # Base confidence on data quality and quantity
        base_confidence = 0.3
        
        # Boost based on number of companies analyzed
        company_bonus = min(0.2, len(company_analyses) * 0.03)
        
        # Boost based on articles analyzed
        total_articles = sum(
            analysis.get('news_sentiment', {}).get('articles_analyzed', 0)
            for analysis in company_analyses
        )
        article_bonus = min(0.2, total_articles * 0.005)
        
        # Boost based on average confidence of individual analyses
        avg_individual_confidence = statistics.mean([
            analysis.get('confidence', 0.5) for analysis in company_analyses
        ])
        confidence_bonus = (avg_individual_confidence - 0.5) * 0.3
        
        # Reduce confidence if sentiment is very dispersed (conflicting signals)
        market_dispersion = market_sentiment.get('sentiment_dispersion', 0.5)
        dispersion_penalty = min(0.2, market_dispersion * 0.3)
        
        final_confidence = (base_confidence + company_bonus + article_bonus + 
                          confidence_bonus - dispersion_penalty)
        
        return max(0.1, min(0.95, final_confidence))
    
    def _get_data_sources(self) -> List[str]:
        """Get list of data sources used."""
        return [
            "Finnhub News API",
            "Claude LLM Sentiment Analysis",
            "Multi-source News Aggregation",
            "Credibility-weighted Analysis"
        ]
    
    def _generate_analysis_reasoning(self, result_data: Dict) -> str:
        """Generate human-readable reasoning for the analysis."""
        
        company_count = len(result_data.get('company_analyses', []))
        total_articles = sum(
            analysis.get('news_sentiment', {}).get('articles_analyzed', 0)
            for analysis in result_data.get('company_analyses', [])
        )
        
        market_sentiment = result_data.get('market_sentiment', {})
        avg_sentiment = market_sentiment.get('market_sentiment_score', 0.0)
        
        reasoning = f"Analyzed sentiment for {company_count} companies using {total_articles} news articles. "
        
        if avg_sentiment > 0.2:
            reasoning += "Market sentiment is generally positive. "
        elif avg_sentiment < -0.2:
            reasoning += "Market sentiment is generally negative. "
        else:
            reasoning += "Market sentiment is neutral or mixed. "
        
        signals = result_data.get('sentiment_signals', {})
        buy_signals = len(signals.get('buy_signals', []))
        sell_signals = len(signals.get('sell_signals', []))
        
        reasoning += f"Generated {buy_signals} buy signals and {sell_signals} sell signals based on sentiment trends and momentum."
        
        return reasoning
    
    def _get_methodology_summary(self) -> Dict[str, str]:
        """Get summary of analysis methodology."""
        return {
            'sentiment_extraction': 'LLM-based sentiment analysis of news headlines and summaries',
            'credibility_weighting': 'Source credibility and time decay weighting for sentiment scores',
            'trend_analysis': 'Time series analysis of sentiment patterns and momentum',
            'market_context': 'Cross-company sentiment analysis for market regime identification',
            'signal_generation': 'Rule-based sentiment signals with confidence thresholds',
            'thesis_alignment': 'Investment thesis relevance scoring for sentiment themes'
        }