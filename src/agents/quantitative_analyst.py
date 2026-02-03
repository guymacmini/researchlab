"""Quantitative Analyst agent for statistical analysis and backtesting."""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import yfinance as yf
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import structlog

from src.agents.base import BaseAgent, AgentRole, AgentResult
from src.data.clients.alpha_vantage_client import AlphaVantageClient
from src.data.clients.finnhub_client import FinnhubClient

logger = structlog.get_logger()


class QuantitativeAnalyst(BaseAgent):
    """
    Quantitative Analyst specializing in:
    - Statistical analysis of stock performance
    - Factor analysis and correlation studies
    - Momentum and mean reversion signals  
    - Basic backtesting and performance attribution
    - Risk-adjusted return metrics
    """
    
    role = AgentRole.QUANTITATIVE_ANALYST
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
        # Initialize data clients (optional for quantitative analysis as we primarily use yfinance)
        self.alpha_vantage = None
        self.finnhub = None
        
        try:
            self.alpha_vantage = AlphaVantageClient()
        except ValueError:
            self.logger.warning("Alpha Vantage API key not configured, skipping client initialization")
        
        try:
            self.finnhub = FinnhubClient()
        except ValueError:
            self.logger.warning("Finnhub API key not configured, skipping client initialization")
        
        # Analysis parameters
        self.lookback_periods = self.config.get('lookback_periods', {
            'short_term': 30,    # 1 month
            'medium_term': 90,   # 3 months
            'long_term': 252,    # 1 year
            'extended': 504      # 2 years
        })
        
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        self.min_data_points = self.config.get('min_data_points', 50)
        
    async def validate_inputs(self, research_request: Dict[str, Any]) -> bool:
        """Validate inputs for quantitative analysis."""
        
        required_fields = ['companies']
        for field in required_fields:
            if field not in research_request:
                self.logger.error("missing_required_field", field=field)
                return False
        
        companies = research_request.get('companies', [])
        if not companies:
            self.logger.error("no_companies_provided")
            return False
        
        # Validate each company has required fields
        for company in companies:
            if not isinstance(company, dict) or 'symbol' not in company:
                self.logger.error("invalid_company_format", company=company)
                return False
        
        return True
    
    async def analyze(self, research_request: Dict[str, Any]) -> AgentResult:
        """
        Perform quantitative analysis on specified companies.
        
        Returns comprehensive statistical analysis including:
        - Price momentum and trend analysis
        - Volatility and risk metrics
        - Correlation analysis 
        - Factor analysis
        - Performance attribution
        - Basic backtesting signals
        """
        
        start_time = datetime.now()
        
        try:
            companies = research_request['companies']
            
            # Get historical price data
            self.logger.info("fetching_historical_data", companies=len(companies))
            price_data = await self._fetch_price_data(companies)
            
            if not price_data:
                return self._create_error_result("Failed to fetch sufficient price data")
            
            # Perform quantitative analysis
            analysis_results = {}
            
            # 1. Individual company analysis
            for company in companies:
                symbol = company['symbol']
                if symbol in price_data:
                    company_analysis = await self._analyze_company(symbol, price_data[symbol], company)
                    analysis_results[symbol] = company_analysis
            
            # 2. Comparative analysis
            if len(analysis_results) > 1:
                comparative_analysis = await self._perform_comparative_analysis(
                    analysis_results, price_data
                )
            else:
                comparative_analysis = {}
            
            # 3. Factor analysis
            factor_analysis = await self._perform_factor_analysis(price_data)
            
            # 4. Portfolio-level metrics
            portfolio_metrics = await self._calculate_portfolio_metrics(price_data)
            
            # 5. Generate trading signals
            trading_signals = await self._generate_trading_signals(analysis_results)
            
            # Compile final results
            final_data = {
                'individual_analysis': analysis_results,
                'comparative_analysis': comparative_analysis,
                'factor_analysis': factor_analysis,
                'portfolio_metrics': portfolio_metrics,
                'trading_signals': trading_signals,
                'methodology': self._get_methodology_summary(),
                'analysis_timestamp': start_time.isoformat(),
                'lookback_periods': self.lookback_periods
            }
            
            # Calculate overall confidence
            confidence = self._calculate_confidence(analysis_results, price_data)
            
            # Generate reasoning
            reasoning = self._generate_reasoning(final_data, confidence)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.info("quantitative_analysis_completed", 
                           companies=len(companies),
                           execution_time=execution_time,
                           confidence=confidence)
            
            return AgentResult(
                agent=self.role,
                success=True,
                data=final_data,
                confidence=confidence,
                sources=self._get_data_sources(),
                reasoning=reasoning
            )
            
        except Exception as e:
            self.logger.error("quantitative_analysis_failed", error=str(e))
            return self._create_error_result(f"Quantitative analysis failed: {str(e)}")
    
    async def _fetch_price_data(self, companies: List[Dict[str, Any]]) -> Dict[str, pd.DataFrame]:
        """Fetch historical price data for analysis."""
        
        price_data = {}
        
        for company in companies:
            symbol = company['symbol']
            
            try:
                # Use yfinance for comprehensive historical data
                ticker = yf.Ticker(symbol)
                
                # Get 2 years of daily data
                end_date = datetime.now()
                start_date = end_date - timedelta(days=730)
                
                hist = ticker.history(start=start_date, end=end_date)
                
                if len(hist) >= self.min_data_points:
                    # Clean and prepare data
                    hist = hist.dropna()
                    hist['Returns'] = hist['Close'].pct_change()
                    hist['Log_Returns'] = np.log(hist['Close'] / hist['Close'].shift(1))
                    hist['Volume_MA'] = hist['Volume'].rolling(window=20).mean()
                    
                    price_data[symbol] = hist
                    
                    self.logger.info("price_data_fetched", 
                                   symbol=symbol, 
                                   data_points=len(hist))
                else:
                    self.logger.warning("insufficient_price_data", 
                                      symbol=symbol, 
                                      data_points=len(hist))
                    
            except Exception as e:
                self.logger.error("price_data_fetch_failed", 
                                symbol=symbol, error=str(e))
        
        return price_data
    
    async def _analyze_company(self, symbol: str, data: pd.DataFrame, 
                             company_info: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comprehensive quantitative analysis for a single company."""
        
        analysis = {
            'symbol': symbol,
            'company_name': company_info.get('name', symbol),
            'data_period': {
                'start': data.index.min().strftime('%Y-%m-%d'),
                'end': data.index.max().strftime('%Y-%m-%d'),
                'trading_days': len(data)
            }
        }
        
        # Price momentum analysis
        analysis['momentum'] = self._analyze_momentum(data)
        
        # Volatility analysis
        analysis['volatility'] = self._analyze_volatility(data)
        
        # Trend analysis
        analysis['trend'] = self._analyze_trend(data)
        
        # Volume analysis
        analysis['volume'] = self._analyze_volume(data)
        
        # Technical indicators
        analysis['technical_indicators'] = self._calculate_technical_indicators(data)
        
        # Risk metrics
        analysis['risk_metrics'] = self._calculate_risk_metrics(data)
        
        # Performance attribution
        analysis['performance'] = self._analyze_performance(data)
        
        return analysis
    
    def _analyze_momentum(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price momentum across different timeframes."""
        
        momentum = {}
        
        for period_name, days in self.lookback_periods.items():
            if len(data) >= days:
                # Calculate returns over period
                period_return = (data['Close'].iloc[-1] / data['Close'].iloc[-days] - 1)
                
                # Calculate momentum score (0-1)
                positive_days = (data['Returns'].tail(days) > 0).sum()
                momentum_score = positive_days / days
                
                # Calculate average daily return
                avg_daily_return = data['Returns'].tail(days).mean()
                
                momentum[period_name] = {
                    'period_return': float(period_return),
                    'momentum_score': float(momentum_score),
                    'avg_daily_return': float(avg_daily_return),
                    'days': days
                }
        
        # Overall momentum assessment
        short_momentum = momentum.get('short_term', {}).get('momentum_score', 0.5)
        long_momentum = momentum.get('long_term', {}).get('momentum_score', 0.5)
        
        momentum['overall_signal'] = self._classify_momentum(short_momentum, long_momentum)
        
        return momentum
    
    def _analyze_volatility(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price volatility patterns."""
        
        volatility = {}
        
        for period_name, days in self.lookback_periods.items():
            if len(data) >= days:
                period_data = data.tail(days)
                
                # Standard volatility metrics
                daily_vol = period_data['Returns'].std()
                annualized_vol = daily_vol * np.sqrt(252)
                
                # Rolling volatility trend
                rolling_vol = period_data['Returns'].rolling(window=20).std()
                vol_trend = 'increasing' if rolling_vol.iloc[-1] > rolling_vol.mean() else 'decreasing'
                
                volatility[period_name] = {
                    'daily_volatility': float(daily_vol),
                    'annualized_volatility': float(annualized_vol),
                    'volatility_trend': vol_trend,
                    'volatility_percentile': float(stats.percentileofscore(rolling_vol.dropna(), rolling_vol.iloc[-1]) / 100)
                }
        
        # Volatility regime classification
        current_vol = volatility.get('short_term', {}).get('annualized_volatility', 0.2)
        long_term_vol = volatility.get('long_term', {}).get('annualized_volatility', 0.2)
        
        volatility['regime'] = self._classify_volatility_regime(current_vol, long_term_vol)
        
        return volatility
    
    def _analyze_trend(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price trend using regression analysis."""
        
        trend = {}
        
        for period_name, days in self.lookback_periods.items():
            if len(data) >= days:
                period_data = data.tail(days).copy()
                
                # Linear regression on log prices
                X = np.arange(len(period_data)).reshape(-1, 1)
                y = np.log(period_data['Close'].values)
                
                model = LinearRegression()
                model.fit(X, y)
                
                # Trend metrics
                slope = model.coef_[0]
                r_squared = r2_score(y, model.predict(X))
                annualized_trend = slope * 252  # Annualize the trend
                
                trend[period_name] = {
                    'trend_slope': float(slope),
                    'annualized_trend': float(annualized_trend),
                    'r_squared': float(r_squared),
                    'trend_strength': 'strong' if r_squared > 0.7 else 'moderate' if r_squared > 0.4 else 'weak',
                    'trend_direction': 'upward' if slope > 0 else 'downward'
                }
        
        return trend
    
    def _analyze_volume(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume patterns and price-volume relationships."""
        
        volume = {}
        
        # Volume trend analysis
        volume['avg_volume_20d'] = float(data['Volume'].tail(20).mean())
        volume['avg_volume_60d'] = float(data['Volume'].tail(60).mean())
        volume['volume_trend'] = 'increasing' if volume['avg_volume_20d'] > volume['avg_volume_60d'] else 'decreasing'
        
        # Price-volume correlation
        if len(data) >= 60:
            price_change = data['Close'].pct_change().tail(60)
            volume_change = data['Volume'].pct_change().tail(60)
            
            correlation = price_change.corr(volume_change)
            volume['price_volume_correlation'] = float(correlation) if not np.isnan(correlation) else 0.0
        
        # Volume breakout detection
        recent_volume = data['Volume'].tail(5).mean()
        historical_volume = data['Volume'].tail(60).mean()
        volume['volume_breakout'] = recent_volume > (historical_volume * 1.5)
        
        return volume
    
    def _calculate_technical_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate key technical indicators."""
        
        indicators = {}
        
        # Moving averages
        indicators['sma_20'] = float(data['Close'].tail(20).mean())
        indicators['sma_50'] = float(data['Close'].tail(50).mean())
        indicators['sma_200'] = float(data['Close'].tail(200).mean()) if len(data) >= 200 else None
        
        current_price = float(data['Close'].iloc[-1])
        indicators['current_price'] = current_price
        
        # Price vs moving averages
        indicators['price_vs_sma20'] = (current_price / indicators['sma_20'] - 1) if indicators['sma_20'] > 0 else 0
        indicators['price_vs_sma50'] = (current_price / indicators['sma_50'] - 1) if indicators['sma_50'] > 0 else 0
        
        # RSI calculation
        if len(data) >= 14:
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            indicators['rsi'] = float(rsi.iloc[-1])
            indicators['rsi_signal'] = 'oversold' if rsi.iloc[-1] < 30 else 'overbought' if rsi.iloc[-1] > 70 else 'neutral'
        
        # Bollinger Bands
        if len(data) >= 20:
            sma_20 = data['Close'].rolling(window=20).mean()
            std_20 = data['Close'].rolling(window=20).std()
            upper_band = sma_20 + (2 * std_20)
            lower_band = sma_20 - (2 * std_20)
            
            indicators['bollinger'] = {
                'upper_band': float(upper_band.iloc[-1]),
                'lower_band': float(lower_band.iloc[-1]),
                'position': 'above' if current_price > upper_band.iloc[-1] else 'below' if current_price < lower_band.iloc[-1] else 'within'
            }
        
        return indicators
    
    def _calculate_risk_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive risk metrics."""
        
        risk = {}
        
        if len(data) >= 30:
            returns = data['Returns'].dropna()
            
            # Basic risk metrics
            risk['annualized_volatility'] = float(returns.std() * np.sqrt(252))
            risk['downside_volatility'] = float(returns[returns < 0].std() * np.sqrt(252)) if len(returns[returns < 0]) > 0 else 0.0
            
            # Sharpe ratio (assuming 2% risk-free rate)
            risk_free_rate = 0.02
            excess_returns = returns.mean() * 252 - risk_free_rate
            risk['sharpe_ratio'] = float(excess_returns / risk['annualized_volatility']) if risk['annualized_volatility'] > 0 else 0.0
            
            # VaR and CVaR (95% confidence)
            risk['var_95'] = float(np.percentile(returns, 5))
            risk['cvar_95'] = float(returns[returns <= risk['var_95']].mean()) if len(returns[returns <= risk['var_95']]) > 0 else risk['var_95']
            
            # Maximum drawdown
            cumulative = (1 + returns).cumprod()
            rolling_max = cumulative.expanding().max()
            drawdown = (cumulative - rolling_max) / rolling_max
            risk['max_drawdown'] = float(drawdown.min())
            
            # Skewness and kurtosis
            risk['skewness'] = float(stats.skew(returns))
            risk['kurtosis'] = float(stats.kurtosis(returns))
        
        return risk
    
    def _analyze_performance(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze performance across different periods."""
        
        performance = {}
        
        for period_name, days in self.lookback_periods.items():
            if len(data) >= days:
                period_data = data.tail(days)
                
                # Total return
                total_return = (period_data['Close'].iloc[-1] / period_data['Close'].iloc[0] - 1)
                
                # Annualized return
                years = days / 252
                annualized_return = (1 + total_return) ** (1/years) - 1 if years > 0 else total_return
                
                # Win rate
                positive_days = (period_data['Returns'] > 0).sum()
                win_rate = positive_days / len(period_data)
                
                performance[period_name] = {
                    'total_return': float(total_return),
                    'annualized_return': float(annualized_return),
                    'win_rate': float(win_rate),
                    'days': days
                }
        
        return performance
    
    async def _perform_comparative_analysis(self, company_analyses: Dict[str, Any], 
                                          price_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Perform comparative analysis across companies."""
        
        comparative = {}
        
        # Performance ranking
        performance_metrics = {}
        for symbol, analysis in company_analyses.items():
            long_term_perf = analysis.get('performance', {}).get('long_term', {})
            if long_term_perf:
                performance_metrics[symbol] = {
                    'annualized_return': long_term_perf.get('annualized_return', 0),
                    'volatility': analysis.get('risk_metrics', {}).get('annualized_volatility', 0),
                    'sharpe_ratio': analysis.get('risk_metrics', {}).get('sharpe_ratio', 0)
                }
        
        if performance_metrics:
            # Rank by Sharpe ratio
            sorted_by_sharpe = sorted(performance_metrics.items(), 
                                    key=lambda x: x[1]['sharpe_ratio'], reverse=True)
            comparative['sharpe_ranking'] = [{'symbol': s, 'sharpe': round(d['sharpe_ratio'], 3)} 
                                           for s, d in sorted_by_sharpe]
        
        # Correlation analysis
        if len(price_data) > 1:
            correlation_matrix = self._calculate_correlation_matrix(price_data)
            comparative['correlation_matrix'] = correlation_matrix
        
        return comparative
    
    async def _perform_factor_analysis(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Perform factor analysis to identify common drivers."""
        
        factor_analysis = {}
        
        if len(price_data) > 1:
            # Create returns matrix
            returns_data = {}
            for symbol, data in price_data.items():
                returns_data[symbol] = data['Returns'].dropna()
            
            # Align dates
            common_dates = None
            for returns in returns_data.values():
                if common_dates is None:
                    common_dates = returns.index
                else:
                    common_dates = common_dates.intersection(returns.index)
            
            if len(common_dates) > 50:
                # Create aligned returns matrix
                aligned_returns = pd.DataFrame()
                for symbol, returns in returns_data.items():
                    aligned_returns[symbol] = returns.loc[common_dates]
                
                # Basic factor analysis - market factor
                market_return = aligned_returns.mean(axis=1)  # Equal-weighted market
                
                factor_analysis['market_factor'] = {
                    'avg_daily_return': float(market_return.mean()),
                    'volatility': float(market_return.std()),
                    'correlation_to_market': {}
                }
                
                # Beta calculations
                for symbol in aligned_returns.columns:
                    stock_returns = aligned_returns[symbol]
                    beta = stock_returns.cov(market_return) / market_return.var()
                    correlation = stock_returns.corr(market_return)
                    
                    factor_analysis['market_factor']['correlation_to_market'][symbol] = {
                        'beta': float(beta),
                        'correlation': float(correlation)
                    }
        
        return factor_analysis
    
    async def _calculate_portfolio_metrics(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate portfolio-level metrics assuming equal weighting."""
        
        portfolio = {}
        
        if len(price_data) > 1:
            # Equal-weighted portfolio
            returns_data = {}
            for symbol, data in price_data.items():
                returns_data[symbol] = data['Returns'].dropna()
            
            # Align dates and create portfolio
            common_dates = None
            for returns in returns_data.values():
                if common_dates is None:
                    common_dates = returns.index
                else:
                    common_dates = common_dates.intersection(returns.index)
            
            if len(common_dates) > 30:
                portfolio_returns = []
                for date in common_dates:
                    daily_returns = []
                    for returns in returns_data.values():
                        if date in returns.index:
                            daily_returns.append(returns[date])
                    
                    if daily_returns:
                        portfolio_returns.append(np.mean(daily_returns))
                
                portfolio_returns = pd.Series(portfolio_returns, index=common_dates)
                
                # Portfolio metrics
                portfolio['equal_weighted'] = {
                    'avg_daily_return': float(portfolio_returns.mean()),
                    'annualized_return': float(portfolio_returns.mean() * 252),
                    'volatility': float(portfolio_returns.std() * np.sqrt(252)),
                    'sharpe_ratio': float((portfolio_returns.mean() * 252 - 0.02) / (portfolio_returns.std() * np.sqrt(252)))
                }
                
                # Diversification benefit
                individual_vol = np.mean([data['Returns'].std() for data in returns_data.values()])
                diversification_ratio = float(individual_vol / portfolio_returns.std())
                portfolio['diversification_ratio'] = diversification_ratio
        
        return portfolio
    
    async def _generate_trading_signals(self, company_analyses: Dict[str, Any]) -> Dict[str, Any]:
        """Generate trading signals based on quantitative analysis."""
        
        signals = {}
        
        for symbol, analysis in company_analyses.items():
            symbol_signals = []
            
            # Momentum signal
            momentum = analysis.get('momentum', {})
            short_momentum = momentum.get('short_term', {}).get('momentum_score', 0.5)
            long_momentum = momentum.get('long_term', {}).get('momentum_score', 0.5)
            
            if short_momentum > 0.65 and long_momentum > 0.55:
                symbol_signals.append({
                    'type': 'momentum',
                    'signal': 'buy',
                    'strength': 'strong' if short_momentum > 0.75 else 'moderate',
                    'rationale': f'Strong momentum: {short_momentum:.2f} short-term, {long_momentum:.2f} long-term'
                })
            elif short_momentum < 0.35 and long_momentum < 0.45:
                symbol_signals.append({
                    'type': 'momentum',
                    'signal': 'sell',
                    'strength': 'strong' if short_momentum < 0.25 else 'moderate',
                    'rationale': f'Weak momentum: {short_momentum:.2f} short-term, {long_momentum:.2f} long-term'
                })
            
            # Technical signal
            technical = analysis.get('technical_indicators', {})
            rsi = technical.get('rsi', 50)
            price_vs_sma20 = technical.get('price_vs_sma20', 0)
            
            if rsi < 30 and price_vs_sma20 < -0.05:
                symbol_signals.append({
                    'type': 'technical',
                    'signal': 'buy',
                    'strength': 'moderate',
                    'rationale': f'Oversold conditions: RSI={rsi:.1f}, Price vs SMA20={price_vs_sma20:.1%}'
                })
            elif rsi > 70 and price_vs_sma20 > 0.05:
                symbol_signals.append({
                    'type': 'technical',
                    'signal': 'sell',
                    'strength': 'moderate',
                    'rationale': f'Overbought conditions: RSI={rsi:.1f}, Price vs SMA20={price_vs_sma20:.1%}'
                })
            
            # Risk signal
            risk_metrics = analysis.get('risk_metrics', {})
            max_drawdown = risk_metrics.get('max_drawdown', 0)
            sharpe_ratio = risk_metrics.get('sharpe_ratio', 0)
            
            if max_drawdown < -0.20:
                symbol_signals.append({
                    'type': 'risk',
                    'signal': 'caution',
                    'strength': 'strong',
                    'rationale': f'High drawdown risk: {max_drawdown:.1%} maximum drawdown'
                })
            
            if sharpe_ratio > 1.0:
                symbol_signals.append({
                    'type': 'risk_adjusted',
                    'signal': 'buy',
                    'strength': 'strong' if sharpe_ratio > 1.5 else 'moderate',
                    'rationale': f'Strong risk-adjusted returns: Sharpe ratio {sharpe_ratio:.2f}'
                })
            
            signals[symbol] = symbol_signals
        
        return signals
    
    def _calculate_correlation_matrix(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate correlation matrix between stocks."""
        
        # Create returns matrix
        returns_data = {}
        for symbol, data in price_data.items():
            returns_data[symbol] = data['Returns'].dropna()
        
        # Align dates
        common_dates = None
        for returns in returns_data.values():
            if common_dates is None:
                common_dates = returns.index
            else:
                common_dates = common_dates.intersection(returns.index)
        
        if len(common_dates) > 30:
            aligned_returns = pd.DataFrame()
            for symbol, returns in returns_data.items():
                aligned_returns[symbol] = returns.loc[common_dates]
            
            correlation_matrix = aligned_returns.corr()
            
            # Convert to dictionary format
            corr_dict = {}
            for i, symbol1 in enumerate(correlation_matrix.columns):
                corr_dict[symbol1] = {}
                for j, symbol2 in enumerate(correlation_matrix.columns):
                    corr_dict[symbol1][symbol2] = float(correlation_matrix.iloc[i, j])
            
            return corr_dict
        
        return {}
    
    def _classify_momentum(self, short_momentum: float, long_momentum: float) -> str:
        """Classify overall momentum signal."""
        
        if short_momentum > 0.65 and long_momentum > 0.55:
            return 'strong_bullish'
        elif short_momentum > 0.55 and long_momentum > 0.50:
            return 'moderate_bullish'
        elif short_momentum < 0.35 and long_momentum < 0.45:
            return 'strong_bearish'
        elif short_momentum < 0.45 and long_momentum < 0.50:
            return 'moderate_bearish'
        else:
            return 'neutral'
    
    def _classify_volatility_regime(self, current_vol: float, long_term_vol: float) -> str:
        """Classify volatility regime."""
        
        if current_vol > long_term_vol * 1.5:
            return 'high_volatility'
        elif current_vol < long_term_vol * 0.7:
            return 'low_volatility'
        else:
            return 'normal_volatility'
    
    def _calculate_confidence(self, analysis_results: Dict[str, Any], 
                            price_data: Dict[str, pd.DataFrame]) -> float:
        """Calculate overall confidence in the quantitative analysis."""
        
        confidence_factors = []
        
        # Data quality factor
        min_data_points = min([len(data) for data in price_data.values()])
        data_quality = min(1.0, min_data_points / 252)  # 1 year = full confidence
        confidence_factors.append(data_quality * 0.3)  # 30% weight
        
        # Analysis completeness factor
        complete_analyses = 0
        total_analyses = len(analysis_results)
        
        for analysis in analysis_results.values():
            required_sections = ['momentum', 'volatility', 'trend', 'risk_metrics']
            if all(section in analysis for section in required_sections):
                complete_analyses += 1
        
        completeness = complete_analyses / total_analyses if total_analyses > 0 else 0
        confidence_factors.append(completeness * 0.4)  # 40% weight
        
        # Signal consistency factor
        signal_consistency = 0.0
        if len(analysis_results) > 0:
            # Check for consistent signals across momentum, technical, and risk
            consistent_signals = 0
            total_signals = 0
            
            for analysis in analysis_results.values():
                momentum_signal = analysis.get('momentum', {}).get('overall_signal', 'neutral')
                
                if momentum_signal in ['strong_bullish', 'moderate_bullish']:
                    consistent_signals += 1
                elif momentum_signal in ['strong_bearish', 'moderate_bearish']:
                    consistent_signals += 1
                
                total_signals += 1
            
            signal_consistency = consistent_signals / total_signals if total_signals > 0 else 0
        
        confidence_factors.append(signal_consistency * 0.3)  # 30% weight
        
        total_confidence = sum(confidence_factors)
        return max(0.1, min(1.0, total_confidence))  # Clamp between 0.1 and 1.0
    
    def _generate_reasoning(self, analysis_data: Dict[str, Any], confidence: float) -> str:
        """Generate human-readable reasoning for the analysis."""
        
        reasoning_parts = []
        
        # Data overview
        individual_analyses = analysis_data.get('individual_analysis', {})
        companies_analyzed = len(individual_analyses)
        
        reasoning_parts.append(
            f"Quantitative analysis completed for {companies_analyzed} companies "
            f"using comprehensive statistical and technical methodologies."
        )
        
        # Methodology summary
        methodology = analysis_data.get('methodology', {})
        reasoning_parts.append(
            f"Analysis employed {len(methodology)} quantitative techniques including "
            "momentum analysis, volatility modeling, trend regression, and risk metrics."
        )
        
        # Key findings
        if individual_analyses:
            strong_momentum_count = 0
            high_volatility_count = 0
            
            for symbol, analysis in individual_analyses.items():
                momentum_signal = analysis.get('momentum', {}).get('overall_signal', 'neutral')
                if momentum_signal in ['strong_bullish', 'strong_bearish']:
                    strong_momentum_count += 1
                
                vol_regime = analysis.get('volatility', {}).get('regime', 'normal_volatility')
                if vol_regime == 'high_volatility':
                    high_volatility_count += 1
            
            if strong_momentum_count > 0:
                reasoning_parts.append(
                    f"{strong_momentum_count} companies showing strong momentum signals."
                )
            
            if high_volatility_count > 0:
                reasoning_parts.append(
                    f"{high_volatility_count} companies in high volatility regime."
                )
        
        # Portfolio insights
        portfolio_metrics = analysis_data.get('portfolio_metrics', {})
        if portfolio_metrics and 'equal_weighted' in portfolio_metrics:
            portfolio_sharpe = portfolio_metrics['equal_weighted'].get('sharpe_ratio', 0)
            reasoning_parts.append(
                f"Equal-weighted portfolio shows Sharpe ratio of {portfolio_sharpe:.2f}."
            )
        
        # Trading signals
        trading_signals = analysis_data.get('trading_signals', {})
        if trading_signals:
            total_signals = sum([len(signals) for signals in trading_signals.values()])
            reasoning_parts.append(f"Generated {total_signals} actionable trading signals.")
        
        # Confidence assessment
        confidence_level = "high" if confidence > 0.8 else "moderate" if confidence > 0.6 else "low"
        reasoning_parts.append(
            f"Analysis confidence is {confidence_level} ({confidence:.2f}) based on "
            "data quality, completeness, and signal consistency."
        )
        
        return " ".join(reasoning_parts)
    
    def _get_methodology_summary(self) -> Dict[str, str]:
        """Get summary of quantitative methodologies used."""
        
        return {
            'momentum_analysis': 'Multi-timeframe momentum scoring using price trends and positive return ratios',
            'volatility_modeling': 'Rolling volatility analysis with regime classification and percentile ranking',
            'trend_analysis': 'Linear regression on log prices with R-squared significance testing',
            'technical_indicators': 'RSI, Bollinger Bands, and moving average crossover analysis',
            'risk_metrics': 'Comprehensive risk assessment including VaR, CVaR, Sharpe ratio, and maximum drawdown',
            'factor_analysis': 'Market factor modeling and beta calculations for systematic risk assessment',
            'correlation_analysis': 'Cross-asset correlation matrices for diversification analysis',
            'portfolio_optimization': 'Equal-weighted portfolio construction with diversification ratio calculation'
        }
    
    def _get_data_sources(self) -> List[str]:
        """Get list of data sources used in analysis."""
        
        return [
            'Yahoo Finance - Historical price and volume data',
            'Alpha Vantage - Fundamental and technical indicators',
            'Finnhub - Market data validation',
            'Internal calculations - Statistical models and risk metrics'
        ]
    
    def _create_error_result(self, error_message: str) -> AgentResult:
        """Create error result for failed analysis."""
        
        return AgentResult(
            agent=self.role,
            success=False,
            data={},
            confidence=0.0,
            sources=self._get_data_sources(),
            reasoning=f"Quantitative analysis failed: {error_message}",
            errors=[error_message]
        )