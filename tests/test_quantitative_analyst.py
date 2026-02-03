"""Tests for Quantitative Analyst agent."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from src.agents.quantitative_analyst import QuantitativeAnalyst
from src.agents.base import AgentRole, AgentResult


class TestQuantitativeAnalyst:
    """Test cases for Quantitative Analyst agent."""

    @pytest.fixture
    def analyst(self):
        """Create quantitative analyst for testing."""
        config = {
            'confidence_threshold': 0.7,
            'min_data_points': 50,
            'lookback_periods': {
                'short_term': 30,
                'medium_term': 90,
                'long_term': 252,
                'extended': 504
            }
        }
        
        with patch('src.agents.quantitative_analyst.AlphaVantageClient'):
            with patch('src.agents.quantitative_analyst.FinnhubClient'):
                return QuantitativeAnalyst(config)

    @pytest.fixture
    def sample_research_request(self):
        """Sample research request for testing."""
        return {
            'query': 'Analyze tech stocks for quantitative signals',
            'companies': [
                {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology'},
                {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'sector': 'Technology'}
            ],
            'time_horizon': 12
        }

    @pytest.fixture
    def sample_price_data(self):
        """Generate sample price data for testing."""
        dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
        
        # Generate realistic price data with some trend and volatility
        np.random.seed(42)  # For reproducible tests
        
        # AAPL data - upward trending with moderate volatility
        aapl_prices = []
        price = 150.0
        for i, date in enumerate(dates):
            # Add trend and random walk
            trend = 0.0003  # Slight upward trend
            volatility = 0.02
            
            daily_return = trend + np.random.normal(0, volatility)
            price *= (1 + daily_return)
            aapl_prices.append(price)
        
        aapl_data = pd.DataFrame({
            'Open': aapl_prices,
            'High': [p * (1 + abs(np.random.normal(0, 0.01))) for p in aapl_prices],
            'Low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in aapl_prices],
            'Close': aapl_prices,
            'Volume': [np.random.randint(50000000, 100000000) for _ in aapl_prices]
        }, index=dates)
        
        # GOOGL data - more volatile, mixed trend
        googl_prices = []
        price = 2500.0
        for i, date in enumerate(dates):
            trend = 0.0001 if i < len(dates) // 2 else -0.0001  # Trend change
            volatility = 0.025
            
            daily_return = trend + np.random.normal(0, volatility)
            price *= (1 + daily_return)
            googl_prices.append(price)
        
        googl_data = pd.DataFrame({
            'Open': googl_prices,
            'High': [p * (1 + abs(np.random.normal(0, 0.015))) for p in googl_prices],
            'Low': [p * (1 - abs(np.random.normal(0, 0.015))) for p in googl_prices],
            'Close': googl_prices,
            'Volume': [np.random.randint(20000000, 50000000) for _ in googl_prices]
        }, index=dates)
        
        # Add calculated columns
        for data in [aapl_data, googl_data]:
            data['Returns'] = data['Close'].pct_change()
            data['Log_Returns'] = np.log(data['Close'] / data['Close'].shift(1))
            data['Volume_MA'] = data['Volume'].rolling(window=20).mean()
        
        return {
            'AAPL': aapl_data,
            'GOOGL': googl_data
        }

    def test_analyst_initialization(self, analyst):
        """Test analyst initializes correctly."""
        assert analyst.role == AgentRole.QUANTITATIVE_ANALYST
        assert 'short_term' in analyst.lookback_periods
        assert analyst.confidence_threshold == 0.7
        assert analyst.min_data_points == 50

    @pytest.mark.asyncio
    async def test_validate_inputs_success(self, analyst, sample_research_request):
        """Test successful input validation."""
        
        result = await analyst.validate_inputs(sample_research_request)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_inputs_missing_companies(self, analyst):
        """Test input validation with missing companies."""
        
        request = {'query': 'Test'}
        
        result = await analyst.validate_inputs(request)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_empty_companies(self, analyst):
        """Test input validation with empty companies list."""
        
        request = {'query': 'Test', 'companies': []}
        
        result = await analyst.validate_inputs(request)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_inputs_invalid_company_format(self, analyst):
        """Test input validation with invalid company format."""
        
        request = {
            'query': 'Test',
            'companies': ['AAPL']  # Should be dict, not string
        }
        
        result = await analyst.validate_inputs(request)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_price_data_success(self, analyst, sample_research_request, sample_price_data):
        """Test successful price data fetching."""
        
        with patch('yfinance.Ticker') as mock_ticker:
            # Mock yfinance response
            mock_ticker.return_value.history.return_value = sample_price_data['AAPL']
            
            price_data = await analyst._fetch_price_data(sample_research_request['companies'][:1])
            
            assert 'AAPL' in price_data
            assert len(price_data['AAPL']) > 0
            assert 'Returns' in price_data['AAPL'].columns

    @pytest.mark.asyncio
    async def test_fetch_price_data_insufficient_data(self, analyst, sample_research_request):
        """Test price data fetching with insufficient data."""
        
        # Create minimal data (less than min_data_points)
        insufficient_data = pd.DataFrame({
            'Close': [100, 101, 102],
            'Volume': [1000, 1100, 1200]
        }, index=pd.date_range('2024-01-01', periods=3))
        
        with patch('yfinance.Ticker') as mock_ticker:
            mock_ticker.return_value.history.return_value = insufficient_data
            
            price_data = await analyst._fetch_price_data(sample_research_request['companies'][:1])
            
            assert len(price_data) == 0  # Should not include insufficient data

    def test_analyze_momentum(self, analyst, sample_price_data):
        """Test momentum analysis."""
        
        momentum = analyst._analyze_momentum(sample_price_data['AAPL'])
        
        assert 'short_term' in momentum
        assert 'long_term' in momentum
        assert 'overall_signal' in momentum
        
        # Check momentum metrics
        for period in momentum:
            if period != 'overall_signal':
                assert 'period_return' in momentum[period]
                assert 'momentum_score' in momentum[period]
                assert 'avg_daily_return' in momentum[period]
                
                # Momentum score should be between 0 and 1
                assert 0 <= momentum[period]['momentum_score'] <= 1

    def test_analyze_volatility(self, analyst, sample_price_data):
        """Test volatility analysis."""
        
        volatility = analyst._analyze_volatility(sample_price_data['AAPL'])
        
        assert 'short_term' in volatility
        assert 'regime' in volatility
        
        # Check volatility metrics
        for period in volatility:
            if period not in ['regime']:
                assert 'daily_volatility' in volatility[period]
                assert 'annualized_volatility' in volatility[period]
                assert 'volatility_trend' in volatility[period]
                
                # Volatility should be positive
                assert volatility[period]['daily_volatility'] >= 0
                assert volatility[period]['annualized_volatility'] >= 0

    def test_analyze_trend(self, analyst, sample_price_data):
        """Test trend analysis using regression."""
        
        trend = analyst._analyze_trend(sample_price_data['AAPL'])
        
        assert 'short_term' in trend
        assert 'long_term' in trend
        
        # Check trend metrics
        for period in trend:
            assert 'trend_slope' in trend[period]
            assert 'r_squared' in trend[period]
            assert 'trend_strength' in trend[period]
            assert 'trend_direction' in trend[period]
            
            # R-squared should be between 0 and 1
            assert 0 <= trend[period]['r_squared'] <= 1
            
            # Trend direction should be valid
            assert trend[period]['trend_direction'] in ['upward', 'downward']

    def test_analyze_volume(self, analyst, sample_price_data):
        """Test volume analysis."""
        
        volume = analyst._analyze_volume(sample_price_data['AAPL'])
        
        assert 'avg_volume_20d' in volume
        assert 'avg_volume_60d' in volume
        assert 'volume_trend' in volume
        assert 'volume_breakout' in volume
        
        # Volume should be positive
        assert volume['avg_volume_20d'] > 0
        assert volume['avg_volume_60d'] > 0
        
        # Volume trend should be valid
        assert volume['volume_trend'] in ['increasing', 'decreasing']

    def test_calculate_technical_indicators(self, analyst, sample_price_data):
        """Test technical indicator calculations."""
        
        indicators = analyst._calculate_technical_indicators(sample_price_data['AAPL'])
        
        assert 'current_price' in indicators
        assert 'sma_20' in indicators
        assert 'sma_50' in indicators
        assert 'rsi' in indicators
        assert 'bollinger' in indicators
        
        # RSI should be between 0 and 100
        assert 0 <= indicators['rsi'] <= 100
        
        # Moving averages should be positive
        assert indicators['sma_20'] > 0
        assert indicators['sma_50'] > 0

    def test_calculate_risk_metrics(self, analyst, sample_price_data):
        """Test risk metrics calculation."""
        
        risk = analyst._calculate_risk_metrics(sample_price_data['AAPL'])
        
        assert 'annualized_volatility' in risk
        assert 'sharpe_ratio' in risk
        assert 'var_95' in risk
        assert 'max_drawdown' in risk
        assert 'skewness' in risk
        assert 'kurtosis' in risk
        
        # Volatility should be positive
        assert risk['annualized_volatility'] >= 0
        
        # VaR should be negative (loss)
        assert risk['var_95'] <= 0
        
        # Max drawdown should be negative
        assert risk['max_drawdown'] <= 0

    def test_analyze_performance(self, analyst, sample_price_data):
        """Test performance analysis."""
        
        performance = analyst._analyze_performance(sample_price_data['AAPL'])
        
        assert 'short_term' in performance
        assert 'long_term' in performance
        
        # Check performance metrics
        for period in performance:
            assert 'total_return' in performance[period]
            assert 'annualized_return' in performance[period]
            assert 'win_rate' in performance[period]
            
            # Win rate should be between 0 and 1
            assert 0 <= performance[period]['win_rate'] <= 1

    @pytest.mark.asyncio
    async def test_analyze_company(self, analyst, sample_price_data):
        """Test comprehensive company analysis."""
        
        company_info = {'symbol': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology'}
        
        analysis = await analyst._analyze_company('AAPL', sample_price_data['AAPL'], company_info)
        
        assert analysis['symbol'] == 'AAPL'
        assert analysis['company_name'] == 'Apple Inc.'
        assert 'data_period' in analysis
        assert 'momentum' in analysis
        assert 'volatility' in analysis
        assert 'trend' in analysis
        assert 'volume' in analysis
        assert 'technical_indicators' in analysis
        assert 'risk_metrics' in analysis
        assert 'performance' in analysis

    @pytest.mark.asyncio
    async def test_perform_comparative_analysis(self, analyst, sample_price_data):
        """Test comparative analysis across multiple companies."""
        
        # Mock company analyses
        company_analyses = {
            'AAPL': {
                'performance': {'long_term': {'annualized_return': 0.15}},
                'risk_metrics': {'annualized_volatility': 0.25, 'sharpe_ratio': 0.6}
            },
            'GOOGL': {
                'performance': {'long_term': {'annualized_return': 0.12}},
                'risk_metrics': {'annualized_volatility': 0.30, 'sharpe_ratio': 0.4}
            }
        }
        
        comparative = await analyst._perform_comparative_analysis(company_analyses, sample_price_data)
        
        assert 'sharpe_ranking' in comparative
        assert 'correlation_matrix' in comparative
        
        # Check ranking
        rankings = comparative['sharpe_ranking']
        assert len(rankings) == 2
        assert rankings[0]['sharpe'] >= rankings[1]['sharpe']  # Sorted by Sharpe

    @pytest.mark.asyncio
    async def test_perform_factor_analysis(self, analyst, sample_price_data):
        """Test factor analysis."""
        
        factor_analysis = await analyst._perform_factor_analysis(sample_price_data)
        
        assert 'market_factor' in factor_analysis
        
        market_factor = factor_analysis['market_factor']
        assert 'avg_daily_return' in market_factor
        assert 'volatility' in market_factor
        assert 'correlation_to_market' in market_factor
        
        # Check beta calculations
        correlations = market_factor['correlation_to_market']
        for symbol in ['AAPL', 'GOOGL']:
            assert symbol in correlations
            assert 'beta' in correlations[symbol]
            assert 'correlation' in correlations[symbol]

    @pytest.mark.asyncio
    async def test_calculate_portfolio_metrics(self, analyst, sample_price_data):
        """Test portfolio-level metrics calculation."""
        
        portfolio = await analyst._calculate_portfolio_metrics(sample_price_data)
        
        assert 'equal_weighted' in portfolio
        assert 'diversification_ratio' in portfolio
        
        eq_weighted = portfolio['equal_weighted']
        assert 'avg_daily_return' in eq_weighted
        assert 'annualized_return' in eq_weighted
        assert 'volatility' in eq_weighted
        assert 'sharpe_ratio' in eq_weighted

    @pytest.mark.asyncio
    async def test_generate_trading_signals(self, analyst):
        """Test trading signals generation."""
        
        # Mock company analysis with strong momentum
        company_analyses = {
            'AAPL': {
                'momentum': {
                    'short_term': {'momentum_score': 0.8},
                    'long_term': {'momentum_score': 0.7}
                },
                'technical_indicators': {
                    'rsi': 25,  # Oversold
                    'price_vs_sma20': -0.08
                },
                'risk_metrics': {
                    'max_drawdown': -0.15,
                    'sharpe_ratio': 1.2
                }
            }
        }
        
        signals = await analyst._generate_trading_signals(company_analyses)
        
        assert 'AAPL' in signals
        
        aapl_signals = signals['AAPL']
        assert len(aapl_signals) > 0
        
        # Should have momentum buy signal
        momentum_signals = [s for s in aapl_signals if s['type'] == 'momentum']
        assert len(momentum_signals) > 0
        assert momentum_signals[0]['signal'] == 'buy'

    def test_calculate_correlation_matrix(self, analyst, sample_price_data):
        """Test correlation matrix calculation."""
        
        corr_matrix = analyst._calculate_correlation_matrix(sample_price_data)
        
        assert 'AAPL' in corr_matrix
        assert 'GOOGL' in corr_matrix
        
        # Check diagonal elements (should be 1.0)
        assert abs(corr_matrix['AAPL']['AAPL'] - 1.0) < 0.001
        assert abs(corr_matrix['GOOGL']['GOOGL'] - 1.0) < 0.001
        
        # Check symmetry
        assert abs(corr_matrix['AAPL']['GOOGL'] - corr_matrix['GOOGL']['AAPL']) < 0.001

    def test_classify_momentum(self, analyst):
        """Test momentum classification."""
        
        # Test strong bullish
        signal = analyst._classify_momentum(0.8, 0.7)
        assert signal == 'strong_bullish'
        
        # Test strong bearish
        signal = analyst._classify_momentum(0.2, 0.3)
        assert signal == 'strong_bearish'
        
        # Test neutral
        signal = analyst._classify_momentum(0.5, 0.5)
        assert signal == 'neutral'

    def test_classify_volatility_regime(self, analyst):
        """Test volatility regime classification."""
        
        # Test high volatility
        regime = analyst._classify_volatility_regime(0.3, 0.15)
        assert regime == 'high_volatility'
        
        # Test low volatility
        regime = analyst._classify_volatility_regime(0.08, 0.15)
        assert regime == 'low_volatility'
        
        # Test normal volatility
        regime = analyst._classify_volatility_regime(0.15, 0.15)
        assert regime == 'normal_volatility'

    def test_calculate_confidence(self, analyst, sample_price_data):
        """Test confidence calculation."""
        
        # Mock complete analysis results
        analysis_results = {
            'AAPL': {
                'momentum': {'overall_signal': 'strong_bullish'},
                'volatility': {'regime': 'normal_volatility'},
                'trend': {'trend_strength': 'strong'},
                'risk_metrics': {'sharpe_ratio': 0.8}
            }
        }
        
        confidence = analyst._calculate_confidence(analysis_results, sample_price_data)
        
        assert 0.1 <= confidence <= 1.0

    def test_generate_reasoning(self, analyst):
        """Test reasoning generation."""
        
        # Mock analysis data
        analysis_data = {
            'individual_analysis': {
                'AAPL': {'momentum': {'overall_signal': 'strong_bullish'}},
                'GOOGL': {'momentum': {'overall_signal': 'moderate_bearish'}}
            },
            'methodology': {
                'momentum_analysis': 'description',
                'risk_metrics': 'description'
            },
            'portfolio_metrics': {
                'equal_weighted': {'sharpe_ratio': 0.75}
            },
            'trading_signals': {
                'AAPL': [{'type': 'momentum', 'signal': 'buy'}],
                'GOOGL': [{'type': 'risk', 'signal': 'caution'}]
            }
        }
        
        reasoning = analyst._generate_reasoning(analysis_data, 0.8)
        
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0
        assert '2 companies' in reasoning
        assert 'high' in reasoning  # confidence level

    def test_get_methodology_summary(self, analyst):
        """Test methodology summary."""
        
        methodology = analyst._get_methodology_summary()
        
        assert isinstance(methodology, dict)
        assert len(methodology) > 0
        assert 'momentum_analysis' in methodology
        assert 'risk_metrics' in methodology

    def test_get_data_sources(self, analyst):
        """Test data sources list."""
        
        sources = analyst._get_data_sources()
        
        assert isinstance(sources, list)
        assert len(sources) > 0
        assert any('Yahoo Finance' in source for source in sources)

    @pytest.mark.asyncio
    async def test_analyze_integration_success(self, analyst, sample_research_request, sample_price_data):
        """Test full integration analysis."""
        
        with patch.object(analyst, '_fetch_price_data', return_value=sample_price_data) as mock_fetch:
            
            result = await analyst.analyze(sample_research_request)
            
            assert result.success is True
            assert result.agent == AgentRole.QUANTITATIVE_ANALYST
            assert result.confidence > 0
            
            # Check data structure
            data = result.data
            assert 'individual_analysis' in data
            assert 'comparative_analysis' in data
            assert 'factor_analysis' in data
            assert 'portfolio_metrics' in data
            assert 'trading_signals' in data
            assert 'methodology' in data
            
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_no_price_data(self, analyst, sample_research_request):
        """Test analysis with no price data available."""
        
        with patch.object(analyst, '_fetch_price_data', return_value={}):
            
            result = await analyst.analyze(sample_research_request)
            
            assert result.success is False
            assert 'Failed to fetch sufficient price data' in result.reasoning

    @pytest.mark.asyncio
    async def test_analyze_exception_handling(self, analyst, sample_research_request):
        """Test analysis exception handling."""
        
        with patch.object(analyst, '_fetch_price_data', side_effect=Exception("Test error")):
            
            result = await analyst.analyze(sample_research_request)
            
            assert result.success is False
            assert 'Test error' in result.reasoning

    def test_create_error_result(self, analyst):
        """Test error result creation."""
        
        error_msg = "Test error message"
        result = analyst._create_error_result(error_msg)
        
        assert result.success is False
        assert result.agent == AgentRole.QUANTITATIVE_ANALYST
        assert result.confidence == 0.0
        assert error_msg in result.reasoning
        assert error_msg in result.errors


class TestQuantitativeAnalysisIntegration:
    """Integration tests for quantitative analysis."""

    @pytest.mark.asyncio
    async def test_multi_stock_analysis_workflow(self):
        """Test complete multi-stock quantitative analysis workflow."""
        
        with patch('src.agents.quantitative_analyst.AlphaVantageClient'):
            with patch('src.agents.quantitative_analyst.FinnhubClient'):
                with patch('yfinance.Ticker') as mock_ticker:
                    
                    analyst = QuantitativeAnalyst()
                    
                    # Mock price data for multiple stocks
                    dates = pd.date_range('2023-01-01', '2024-01-01', freq='D')
                    mock_data = pd.DataFrame({
                        'Close': np.random.randint(100, 200, len(dates)),
                        'Volume': np.random.randint(1000000, 5000000, len(dates))
                    }, index=dates)
                    
                    mock_data['Returns'] = mock_data['Close'].pct_change()
                    mock_data['Log_Returns'] = np.log(mock_data['Close'] / mock_data['Close'].shift(1))
                    mock_data['Volume_MA'] = mock_data['Volume'].rolling(20).mean()
                    
                    mock_ticker.return_value.history.return_value = mock_data
                    
                    research_request = {
                        'query': 'Multi-stock quantitative analysis',
                        'companies': [
                            {'symbol': 'AAPL', 'name': 'Apple Inc.'},
                            {'symbol': 'GOOGL', 'name': 'Alphabet Inc.'},
                            {'symbol': 'MSFT', 'name': 'Microsoft Corp.'}
                        ]
                    }
                    
                    result = await analyst.analyze(research_request)
                    
                    assert result.success is True
                    assert len(result.data['individual_analysis']) == 3
                    assert 'comparative_analysis' in result.data
                    assert 'portfolio_metrics' in result.data

    def test_statistical_calculations_accuracy(self):
        """Test accuracy of statistical calculations."""
        
        with patch('src.agents.quantitative_analyst.AlphaVantageClient'):
            with patch('src.agents.quantitative_analyst.FinnhubClient'):
                
                analyst = QuantitativeAnalyst()
                
                # Create known data for testing calculations
                dates = pd.date_range('2024-01-01', periods=100, freq='D')
                prices = [100 + i * 0.1 for i in range(100)]  # Linear growth
                
                data = pd.DataFrame({
                    'Close': prices,
                    'Volume': [1000000] * 100,
                    'Returns': pd.Series(prices).pct_change()
                }, index=dates)
                
                # Test momentum calculation
                momentum = analyst._analyze_momentum(data)
                assert momentum['short_term']['momentum_score'] > 0.5  # Should be positive momentum
                
                # Test volatility calculation
                volatility = analyst._analyze_volatility(data)
                assert volatility['short_term']['daily_volatility'] > 0
                
                # Test trend analysis
                trend = analyst._analyze_trend(data)
                assert trend['short_term']['trend_direction'] == 'upward'

    def test_edge_cases_handling(self):
        """Test handling of edge cases in data."""
        
        with patch('src.agents.quantitative_analyst.AlphaVantageClient'):
            with patch('src.agents.quantitative_analyst.FinnhubClient'):
                
                analyst = QuantitativeAnalyst()
                
                # Test with constant prices
                dates = pd.date_range('2024-01-01', periods=100, freq='D')
                constant_data = pd.DataFrame({
                    'Close': [100] * 100,
                    'Volume': [1000000] * 100,
                    'Returns': [0] * 100
                }, index=dates)
                
                # Should handle without crashing
                momentum = analyst._analyze_momentum(constant_data)
                assert 'short_term' in momentum
                
                volatility = analyst._analyze_volatility(constant_data)
                assert volatility['short_term']['daily_volatility'] == 0
                
                # Test with extreme volatility
                volatile_prices = [100 * (1 + 0.1 * (-1)**i) for i in range(100)]
                volatile_data = pd.DataFrame({
                    'Close': volatile_prices,
                    'Volume': [1000000] * 100,
                    'Returns': pd.Series(volatile_prices).pct_change()
                }, index=dates)
                
                vol_analysis = analyst._analyze_volatility(volatile_data)
                assert vol_analysis['short_term']['daily_volatility'] > 0.05  # Should be high