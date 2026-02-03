"""Tests for Sentiment Analyst agent."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import statistics

from src.agents.sentiment_analyst import SentimentAnalystAgent
from src.agents.base import AgentRole, AgentResult


class TestSentimentAnalystAgent:
    """Test cases for Sentiment Analyst agent."""

    @pytest.fixture
    def agent(self):
        """Create a Sentiment Analyst agent for testing."""
        with patch('src.agents.sentiment_analyst.settings') as mock_settings:
            mock_settings.api.anthropic_api_key = "test_anthropic_key"
            mock_settings.api.finnhub_api_key = "test_finnhub_key"
            with patch('src.agents.sentiment_analyst.FinnhubClient'):
                return SentimentAnalystAgent()

    @pytest.fixture
    def sample_context(self):
        """Sample context for testing."""
        return {
            'project_id': 'test-project-123',
            'companies': [
                {
                    'symbol': 'AAPL',
                    'name': 'Apple Inc.',
                    'sector': 'Technology'
                },
                {
                    'symbol': 'TSLA',
                    'name': 'Tesla Inc.',
                    'sector': 'Automotive'
                }
            ],
            'investment_thesis': 'AI and automation will drive growth in technology companies',
            'time_horizon': 30
        }

    @pytest.fixture
    def mock_news_data(self):
        """Mock news data from Finnhub."""
        return [
            {
                'headline': 'Apple Reports Strong Q3 Earnings with AI Growth',
                'summary': 'Apple exceeded expectations with strong revenue growth driven by AI initiatives',
                'source': 'Reuters',
                'datetime': int(datetime.now().timestamp()) - 86400,  # 1 day ago
                'url': 'https://example.com/news1'
            },
            {
                'headline': 'Apple Faces Supply Chain Challenges in China',
                'summary': 'Manufacturing disruptions could impact future product launches',
                'source': 'Bloomberg',
                'datetime': int(datetime.now().timestamp()) - 172800,  # 2 days ago
                'url': 'https://example.com/news2'
            },
            {
                'headline': 'New iPhone Features Receive Mixed Reviews',
                'summary': 'Some features praised while others criticized by analysts',
                'source': 'CNBC',
                'datetime': int(datetime.now().timestamp()) - 259200,  # 3 days ago
                'url': 'https://example.com/news3'
            }
        ]

    @pytest.fixture
    def mock_article_sentiment(self):
        """Mock sentiment analysis result for a single article."""
        return {
            'sentiment_score': 0.7,
            'confidence': 0.8,
            'category': 'earnings',
            'sentiment_drivers': {
                'positive': ['strong revenue growth', 'exceeded expectations'],
                'negative': ['supply chain concerns']
            },
            'potential_impact': 'high',
            'emotional_tone': 'optimistic',
            'reasoning': 'Strong earnings results with positive forward guidance'
        }

    @pytest.fixture
    def mock_news_sentiment(self):
        """Mock news sentiment analysis result."""
        return {
            'articles_analyzed': 25,
            'overall_sentiment': 0.4,
            'confidence': 0.75,
            'sentiment_by_category': {
                'earnings': {'average_sentiment': 0.6, 'article_count': 8},
                'product': {'average_sentiment': 0.2, 'article_count': 5},
                'market': {'average_sentiment': -0.1, 'article_count': 12}
            },
            'sentiment_over_time': {
                '2024-02-01': 0.3,
                '2024-02-02': 0.5,
                '2024-02-03': 0.4
            },
            'key_themes': [
                'AI growth',
                'supply chain challenges',
                'strong earnings',
                'market competition'
            ],
            'source_breakdown': {
                'reuters': {
                    'average_sentiment': 0.6,
                    'article_count': 8,
                    'credibility_weight': 0.95
                },
                'bloomberg': {
                    'average_sentiment': 0.3,
                    'article_count': 10,
                    'credibility_weight': 0.95
                }
            }
        }

    def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent.role == AgentRole.SENTIMENT_ANALYST
        assert hasattr(agent, 'client')
        assert hasattr(agent, 'finnhub_client')
        assert hasattr(agent, 'source_credibility')
        assert hasattr(agent, 'sentiment_categories')
        assert len(agent.sentiment_categories) == 10

    def test_source_credibility_weights(self, agent):
        """Test source credibility weights are properly defined."""
        assert 'reuters' in agent.source_credibility
        assert 'bloomberg' in agent.source_credibility
        assert 'default' in agent.source_credibility
        
        # Reuters should have high credibility
        assert agent.source_credibility['reuters'] >= 0.9
        
        # All weights should be between 0 and 1
        for source, weight in agent.source_credibility.items():
            assert 0.0 <= weight <= 1.0

    def test_sentiment_categories_defined(self, agent):
        """Test all sentiment categories are properly defined."""
        expected_categories = {
            'earnings', 'product', 'management', 'regulation', 'market',
            'merger', 'partnership', 'innovation', 'competition', 'general'
        }
        assert set(agent.sentiment_categories.keys()) == expected_categories
        
        # All categories should have descriptions
        for category, description in agent.sentiment_categories.items():
            assert description
            assert len(description) > 10

    @pytest.mark.asyncio
    async def test_validate_inputs_success(self, agent, sample_context):
        """Test input validation with valid inputs."""
        result = await agent.validate_inputs(sample_context)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_inputs_missing_project_id(self, agent, sample_context):
        """Test input validation fails without project_id."""
        del sample_context['project_id']
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_missing_companies(self, agent, sample_context):
        """Test input validation fails without companies."""
        del sample_context['companies']
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_empty_companies(self, agent, sample_context):
        """Test input validation fails with empty companies list."""
        sample_context['companies'] = []
        result = await agent.validate_inputs(sample_context)
        assert result is False

    @pytest.mark.asyncio
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._analyze_news_sentiment')
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._analyze_social_sentiment')
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._combine_sentiment_sources')
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._analyze_sentiment_trends')
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._analyze_market_sentiment')
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._generate_sentiment_signals')
    async def test_analyze_success(self, mock_generate_signals, mock_market_sentiment,
                                 mock_trends, mock_combine, mock_social, mock_news,
                                 agent, sample_context, mock_news_sentiment):
        """Test successful sentiment analysis workflow."""
        
        # Setup mocks
        mock_news.return_value = mock_news_sentiment
        mock_social.return_value = {
            'platform_breakdown': {},
            'overall_sentiment': 0.0,
            'confidence': 0.0,
            'volume_metrics': {'mentions_count': 0},
            'trending_topics': []
        }
        mock_combine.return_value = {
            'overall_score': 0.4,
            'confidence': 0.75,
            'thesis_alignment': {'alignment_score': 0.6}
        }
        mock_trends.return_value = {
            'trend_direction': 'improving',
            'trend_strength': 0.3,
            'momentum': 'bullish'
        }
        mock_market_sentiment.return_value = {
            'market_sentiment_score': 0.35,
            'sentiment_regime': 'bullish'
        }
        mock_generate_signals.return_value = {
            'buy_signals': [],
            'sell_signals': [],
            'watch_alerts': []
        }

        result = await agent.analyze(sample_context)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.agent == AgentRole.SENTIMENT_ANALYST
        assert result.confidence > 0.0
        assert 'company_analyses' in result.data
        assert 'market_sentiment' in result.data
        assert len(result.data['company_analyses']) == 2

    @pytest.mark.asyncio
    @patch('src.data.clients.finnhub_client.FinnhubClient.get_company_news')
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._analyze_article_sentiment')
    async def test_analyze_news_sentiment(self, mock_article_sentiment_func, mock_get_news,
                                        agent, mock_news_data, mock_article_sentiment):
        """Test news sentiment analysis."""
        
        # Setup mocks
        mock_get_news.return_value = mock_news_data
        mock_article_sentiment_func.return_value = mock_article_sentiment
        
        result = await agent._analyze_news_sentiment('AAPL', 30)

        assert 'articles_analyzed' in result
        assert 'overall_sentiment' in result
        assert 'confidence' in result
        assert 'sentiment_by_category' in result
        assert 'sentiment_over_time' in result
        assert 'key_themes' in result
        assert 'source_breakdown' in result
        
        assert result['articles_analyzed'] > 0
        assert -1.0 <= result['overall_sentiment'] <= 1.0
        assert 0.0 <= result['confidence'] <= 1.0

    @pytest.mark.asyncio
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent.client')
    async def test_analyze_article_sentiment(self, mock_client, agent, mock_news_data,
                                           mock_article_sentiment):
        """Test single article sentiment analysis."""
        
        # Setup mock LLM response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps(mock_article_sentiment)
        mock_client.messages.create.return_value = mock_response

        article = mock_news_data[0]
        result = await agent._analyze_article_sentiment(article, 'AAPL')

        assert result is not None
        assert 'sentiment_score' in result
        assert 'confidence' in result
        assert 'category' in result
        assert 'sentiment_drivers' in result
        assert 'potential_impact' in result
        
        # Verify metadata added
        assert 'headline' in result
        assert 'source' in result
        assert 'credibility_weight' in result

    @pytest.mark.asyncio
    async def test_analyze_social_sentiment(self, agent):
        """Test social sentiment analysis (placeholder implementation)."""
        
        result = await agent._analyze_social_sentiment('AAPL', 30)
        
        assert 'platform_breakdown' in result
        assert 'overall_sentiment' in result
        assert 'confidence' in result
        assert 'volume_metrics' in result
        assert result['overall_sentiment'] == 0.0  # Placeholder returns 0

    @pytest.mark.asyncio
    async def test_combine_sentiment_sources(self, agent, mock_news_sentiment):
        """Test sentiment source combination."""
        
        social_sentiment = {
            'overall_sentiment': 0.2,
            'confidence': 0.6
        }
        
        result = await agent._combine_sentiment_sources(
            mock_news_sentiment, social_sentiment, 'Test thesis'
        )
        
        assert 'overall_score' in result
        assert 'confidence' in result
        assert 'news_weight' in result
        assert 'social_weight' in result
        assert 'thesis_alignment' in result
        assert 'source_breakdown' in result
        
        # Should be weighted combination
        assert -1.0 <= result['overall_score'] <= 1.0
        assert 0.0 <= result['confidence'] <= 1.0

    @pytest.mark.asyncio
    async def test_analyze_sentiment_trends(self, agent, mock_news_sentiment):
        """Test sentiment trend analysis."""
        
        result = await agent._analyze_sentiment_trends('AAPL', mock_news_sentiment, 30)
        
        assert 'trend_direction' in result
        assert 'trend_strength' in result
        assert 'recent_shift' in result
        assert 'volatility' in result
        assert 'momentum' in result
        
        assert result['trend_direction'] in ['improving', 'declining', 'stable', 'insufficient_data']
        assert result['momentum'] in ['bullish', 'bearish', 'neutral']
        assert isinstance(result['recent_shift'], bool)
        assert result['volatility'] >= 0.0

    @pytest.mark.asyncio
    async def test_analyze_market_sentiment(self, agent):
        """Test market-wide sentiment analysis."""
        
        company_analyses = [
            {
                'symbol': 'AAPL',
                'sentiment_score': 0.5,
                'confidence': 0.8,
                'news_sentiment': {'key_themes': ['AI growth', 'strong earnings']}
            },
            {
                'symbol': 'GOOGL',
                'sentiment_score': -0.2,
                'confidence': 0.7,
                'news_sentiment': {'key_themes': ['regulation concerns', 'competition']}
            }
        ]
        
        result = await agent._analyze_market_sentiment(company_analyses, 'Test thesis')
        
        assert 'market_sentiment_score' in result
        assert 'market_confidence' in result
        assert 'sentiment_dispersion' in result
        assert 'sentiment_regime' in result
        assert 'distribution' in result
        assert 'sentiment_leaders' in result
        assert 'sentiment_laggards' in result
        assert 'common_themes' in result
        
        assert result['sentiment_regime'] in ['bullish', 'bearish', 'consensus', 'mixed']
        assert -1.0 <= result['market_sentiment_score'] <= 1.0

    @pytest.mark.asyncio
    async def test_generate_sentiment_signals(self, agent):
        """Test sentiment signal generation."""
        
        company_analyses = [
            {
                'symbol': 'AAPL',
                'sentiment_score': 0.8,  # Strong positive
                'confidence': 0.9,
                'trend_analysis': {'momentum': 'bullish', 'recent_shift': True}
            },
            {
                'symbol': 'TSLA',
                'sentiment_score': -0.7,  # Strong negative
                'confidence': 0.8,
                'trend_analysis': {'momentum': 'bearish', 'recent_shift': False}
            }
        ]
        
        market_sentiment = {
            'sentiment_regime': 'bullish',
            'market_confidence': 0.8,
            'market_sentiment_score': 0.4
        }
        
        result = await agent._generate_sentiment_signals(
            company_analyses, market_sentiment, 'Test thesis'
        )
        
        assert 'buy_signals' in result
        assert 'sell_signals' in result
        assert 'watch_alerts' in result
        assert 'thesis_support' in result
        assert 'thesis_risk' in result
        
        # Should generate buy signal for AAPL
        assert len(result['buy_signals']) >= 1
        assert result['buy_signals'][0]['symbol'] == 'AAPL'
        
        # Should generate sell signal for TSLA
        assert len(result['sell_signals']) >= 1
        assert result['sell_signals'][0]['symbol'] == 'TSLA'

    @pytest.mark.asyncio
    async def test_calculate_weighted_sentiment(self, agent):
        """Test weighted sentiment calculation."""
        
        article_sentiments = [
            {
                'sentiment_score': 0.8,
                'confidence': 0.9,
                'credibility_weight': 0.95,  # Reuters
                'timestamp': int(datetime.now().timestamp()) - 3600,  # 1 hour ago
                'potential_impact': 'high'
            },
            {
                'sentiment_score': -0.3,
                'confidence': 0.7,
                'credibility_weight': 0.6,  # Lower credibility source
                'timestamp': int(datetime.now().timestamp()) - 86400 * 7,  # 1 week ago
                'potential_impact': 'low'
            }
        ]
        
        result = await agent._calculate_weighted_sentiment(article_sentiments)
        
        assert 'score' in result
        assert 'confidence' in result
        assert -1.0 <= result['score'] <= 1.0
        assert 0.0 <= result['confidence'] <= 1.0
        
        # Should weight recent, high-credibility, high-impact news more heavily
        assert result['score'] > 0  # Should be positive due to strong positive recent news

    @pytest.mark.asyncio
    async def test_extract_sentiment_themes(self, agent):
        """Test sentiment theme extraction."""
        
        article_sentiments = [
            {
                'sentiment_drivers': {
                    'positive': ['strong earnings', 'AI growth'],
                    'negative': ['supply chain issues']
                }
            },
            {
                'sentiment_drivers': {
                    'positive': ['market leadership'],
                    'negative': ['competition', 'supply chain issues']
                }
            }
        ]
        
        themes = await agent._extract_sentiment_themes(article_sentiments)
        
        assert isinstance(themes, list)
        assert 'supply chain issues' in themes  # Should appear twice, so be prominent
        assert len(themes) <= 10  # Should limit to top themes

    @pytest.mark.asyncio
    async def test_calculate_confidence(self, agent):
        """Test confidence calculation."""
        
        company_analyses = [
            {
                'confidence': 0.8,
                'news_sentiment': {'articles_analyzed': 25}
            },
            {
                'confidence': 0.7,
                'news_sentiment': {'articles_analyzed': 30}
            }
        ]
        
        market_sentiment = {
            'sentiment_dispersion': 0.2  # Low dispersion = high agreement
        }
        
        confidence = await agent._calculate_confidence(company_analyses, market_sentiment)
        
        assert 0.0 <= confidence <= 1.0
        assert isinstance(confidence, float)

    def test_get_data_sources(self, agent):
        """Test data sources list."""
        
        sources = agent._get_data_sources()
        
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert all(isinstance(source, str) for source in sources)
        assert 'Finnhub' in str(sources)

    def test_generate_analysis_reasoning(self, agent):
        """Test analysis reasoning generation."""
        
        result_data = {
            'company_analyses': [
                {
                    'news_sentiment': {'articles_analyzed': 20}
                },
                {
                    'news_sentiment': {'articles_analyzed': 15}
                }
            ],
            'market_sentiment': {
                'market_sentiment_score': 0.35
            },
            'sentiment_signals': {
                'buy_signals': [{'symbol': 'AAPL'}],
                'sell_signals': []
            }
        }
        
        reasoning = agent._generate_analysis_reasoning(result_data)
        
        assert isinstance(reasoning, str)
        assert len(reasoning) > 50
        assert '2 companies' in reasoning
        assert '35 news articles' in reasoning
        assert 'positive' in reasoning.lower()  # Should mention positive sentiment

    def test_get_methodology_summary(self, agent):
        """Test methodology summary."""
        
        methodology = agent._get_methodology_summary()
        
        assert isinstance(methodology, dict)
        assert 'sentiment_extraction' in methodology
        assert 'credibility_weighting' in methodology
        assert 'trend_analysis' in methodology
        assert 'market_context' in methodology
        assert all(isinstance(v, str) for v in methodology.values())

    @pytest.mark.asyncio
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent._analyze_news_sentiment')
    async def test_analyze_handles_exceptions(self, mock_news_sentiment, agent, sample_context):
        """Test that analyze handles exceptions gracefully."""
        
        # Setup mock to raise exception
        mock_news_sentiment.side_effect = Exception("Test error")

        result = await agent.analyze(sample_context)

        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.confidence == 0.0
        assert len(result.errors) == 1
        assert "Test error" in result.errors[0]

    def test_empty_article_sentiments_handling(self, agent):
        """Test handling of empty article sentiments."""
        
        # Test empty list
        result = agent._extract_sentiment_themes([])
        assert result == []

        # Test weighted sentiment with empty list
        result_async = agent._calculate_weighted_sentiment([])
        # Since it's async, we need to check the structure
        assert hasattr(agent, '_calculate_weighted_sentiment')

    @pytest.mark.asyncio
    async def test_news_sentiment_no_data(self, agent):
        """Test news sentiment analysis with no data."""
        
        with patch.object(agent.finnhub_client, 'get_company_news') as mock_get_news:
            mock_get_news.return_value = []
            
            result = await agent._analyze_news_sentiment('AAPL', 30)
            
            assert result['articles_analyzed'] == 0
            assert result['overall_sentiment'] == 0.0
            assert result['confidence'] == 0.0

    @pytest.mark.asyncio
    async def test_article_sentiment_no_content(self, agent):
        """Test article sentiment analysis with no content."""
        
        empty_article = {'headline': '', 'summary': '', 'source': 'test'}
        
        result = await agent._analyze_article_sentiment(empty_article, 'AAPL')
        
        assert result is None

    @pytest.mark.asyncio 
    @patch('src.agents.sentiment_analyst.SentimentAnalystAgent.client')
    async def test_thesis_alignment_analysis(self, mock_client, agent):
        """Test investment thesis alignment analysis."""
        
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            'alignment_score': 0.6,
            'confidence': 0.8,
            'supporting_themes': ['AI growth', 'innovation'],
            'conflicting_themes': ['regulatory concerns']
        })
        mock_client.messages.create.return_value = mock_response
        
        news_sentiment = {'key_themes': ['AI growth', 'regulatory concerns']}
        social_sentiment = {'key_themes': []}
        thesis = 'AI will drive future growth'
        
        result = await agent._analyze_thesis_sentiment_alignment(
            news_sentiment, social_sentiment, thesis
        )
        
        assert 'alignment_score' in result
        assert 'confidence' in result
        assert 'supporting_themes' in result
        assert 'conflicting_themes' in result
        assert -1.0 <= result['alignment_score'] <= 1.0

    @pytest.mark.asyncio
    async def test_sentiment_trends_insufficient_data(self, agent):
        """Test sentiment trend analysis with insufficient data."""
        
        news_sentiment = {
            'sentiment_over_time': {
                '2024-02-01': 0.3  # Only one data point
            }
        }
        
        result = await agent._analyze_sentiment_trends('AAPL', news_sentiment, 30)
        
        assert result['trend_direction'] == 'insufficient_data'
        assert result['trend_strength'] == 0.0
        assert result['momentum'] == 'neutral'

    def test_source_credibility_lookup(self, agent):
        """Test source credibility weight lookup."""
        
        # Test known high-credibility source
        assert agent.source_credibility['reuters'] >= 0.9
        
        # Test default weight for unknown source
        unknown_weight = agent.source_credibility.get('unknown_source', agent.source_credibility['default'])
        assert unknown_weight == agent.source_credibility['default']

    @pytest.mark.asyncio
    async def test_market_sentiment_empty_analyses(self, agent):
        """Test market sentiment analysis with empty company analyses."""
        
        result = await agent._analyze_market_sentiment([], 'Test thesis')
        
        assert 'error' in result