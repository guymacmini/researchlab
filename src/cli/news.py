"""News monitoring CLI commands."""

import click
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

from src.news.monitor import NewsMonitor
from src.news.analyzer import NewsAnalyzer


@click.group()
def news_cli():
    """News monitoring and analysis commands."""
    pass


@news_cli.group()
def monitor():
    """News monitoring commands."""
    pass


@monitor.command('start')
@click.option('--companies', help='Comma-separated company names to monitor')
@click.option('--tickers', help='Comma-separated ticker symbols to monitor') 
@click.option('--keywords', help='Comma-separated keywords to monitor')
@click.option('--sources', help='Comma-separated news sources (reuters, bloomberg, etc.)')
@click.option('--interval', type=int, default=300, help='Check interval in seconds')
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file')
@click.option('--output', '-o', type=click.Path(), help='Output file for alerts')
@click.option('--daemon', is_flag=True, help='Run as daemon process')
def start_monitoring(companies, tickers, keywords, sources, interval, config, output, daemon):
    """
    Start news monitoring.
    
    Examples:
        researchlab news monitor start --companies "Apple Inc." --tickers AAPL
        researchlab news monitor start --config news_config.json --daemon
    """
    
    click.echo("🔄 Starting news monitoring...")
    
    # Parse inputs
    monitor_config = {}
    
    if companies:
        monitor_config['companies'] = [c.strip() for c in companies.split(',')]
        click.echo(f"Companies: {', '.join(monitor_config['companies'])}")
    
    if tickers:
        monitor_config['tickers'] = [t.strip().upper() for t in tickers.split(',')]
        click.echo(f"Tickers: {', '.join(monitor_config['tickers'])}")
    
    if keywords:
        monitor_config['keywords'] = [k.strip() for k in keywords.split(',')]
        click.echo(f"Keywords: {', '.join(monitor_config['keywords'])}")
    
    if sources:
        monitor_config['sources'] = [s.strip() for s in sources.split(',')]
        click.echo(f"Sources: {', '.join(monitor_config['sources'])}")
    
    # Load from config file if provided
    if config:
        try:
            with open(config, 'r') as f:
                file_config = json.load(f)
                monitor_config.update(file_config)
            click.echo(f"✅ Loaded configuration from {config}")
        except Exception as e:
            click.echo(f"❌ Error loading config: {e}")
            return 1
    
    if not any(monitor_config.get(key) for key in ['companies', 'tickers', 'keywords']):
        click.echo("❌ Must specify at least one of: --companies, --tickers, or --keywords")
        return 1
    
    monitor_config['check_interval'] = interval
    monitor_config['output_file'] = output
    
    click.echo(f"Check interval: {interval}s")
    
    if daemon:
        click.echo("🔧 Starting as daemon process...")
        result = asyncio.run(_start_monitoring_daemon(monitor_config))
    else:
        click.echo("🔧 Starting monitoring (Ctrl+C to stop)...")
        result = asyncio.run(_start_monitoring_interactive(monitor_config))
    
    if result:
        click.echo("✅ News monitoring started successfully")
    else:
        click.echo("❌ Failed to start news monitoring")
        return 1


async def _start_monitoring_daemon(config: Dict[str, Any]) -> bool:
    """Start monitoring as daemon process."""
    
    try:
        monitor = NewsMonitor()
        await monitor.configure(config)
        await monitor.start_daemon()
        return True
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


async def _start_monitoring_interactive(config: Dict[str, Any]) -> bool:
    """Start monitoring interactively."""
    
    try:
        monitor = NewsMonitor()
        await monitor.configure(config)
        
        # Start monitoring loop
        while True:
            try:
                alerts = await monitor.check_news()
                
                if alerts:
                    click.echo(f"\n📢 {len(alerts)} new alerts:")
                    for alert in alerts:
                        _display_alert(alert)
                    
                    # Save to file if configured
                    if config.get('output_file'):
                        _save_alerts(alerts, config['output_file'])
                
                await asyncio.sleep(config.get('check_interval', 300))
                
            except KeyboardInterrupt:
                click.echo("\n⏹️  Stopping news monitoring...")
                break
            
        return True
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


def _display_alert(alert: Dict[str, Any]):
    """Display news alert."""
    
    timestamp = alert.get('timestamp', datetime.now().strftime('%H:%M:%S'))
    title = alert.get('title', 'No title')
    source = alert.get('source', 'Unknown')
    relevance = alert.get('relevance_score', 0)
    sentiment = alert.get('sentiment', {}).get('label', 'neutral')
    
    sentiment_emoji = {
        'positive': '🟢',
        'negative': '🔴', 
        'neutral': '⚪'
    }.get(sentiment, '⚪')
    
    click.echo(f"  [{timestamp}] {sentiment_emoji} {title}")
    click.echo(f"    Source: {source} | Relevance: {relevance:.2f} | Sentiment: {sentiment}")
    
    if alert.get('url'):
        click.echo(f"    URL: {alert['url']}")
    
    click.echo()


def _save_alerts(alerts: List[Dict], output_file: str):
    """Save alerts to file."""
    
    try:
        # Load existing alerts
        existing_alerts = []
        if Path(output_file).exists():
            with open(output_file, 'r') as f:
                existing_alerts = json.load(f)
        
        # Add new alerts
        existing_alerts.extend(alerts)
        
        # Save all alerts
        with open(output_file, 'w') as f:
            json.dump(existing_alerts, f, indent=2, default=str)
            
    except Exception as e:
        click.echo(f"Error saving alerts: {e}")


@monitor.command('stop')
def stop_monitoring():
    """
    Stop news monitoring daemon.
    
    Examples:
        researchlab news monitor stop
    """
    
    click.echo("⏹️  Stopping news monitoring...")
    
    result = asyncio.run(_stop_monitoring_daemon())
    
    if result:
        click.echo("✅ News monitoring stopped")
    else:
        click.echo("❌ Failed to stop monitoring (may not be running)")


async def _stop_monitoring_daemon() -> bool:
    """Stop monitoring daemon."""
    
    try:
        monitor = NewsMonitor()
        await monitor.stop_daemon()
        return True
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


@monitor.command('status')
def get_monitoring_status():
    """
    Get news monitoring status.
    
    Examples:
        researchlab news monitor status
    """
    
    status = asyncio.run(_get_monitoring_status())
    
    if status:
        click.echo("📊 News Monitoring Status")
        click.echo("=" * 30)
        click.echo(f"Status: {status.get('status', 'unknown')}")
        click.echo(f"Uptime: {status.get('uptime', 'N/A')}")
        click.echo(f"Articles Processed: {status.get('articles_processed', 0)}")
        click.echo(f"Alerts Generated: {status.get('alerts_generated', 0)}")
        click.echo(f"Last Check: {status.get('last_check', 'N/A')}")
        
        monitored = status.get('monitored_entities', {})
        if monitored.get('companies'):
            click.echo(f"Companies: {', '.join(monitored['companies'])}")
        if monitored.get('tickers'):
            click.echo(f"Tickers: {', '.join(monitored['tickers'])}")
        if monitored.get('keywords'):
            click.echo(f"Keywords: {', '.join(monitored['keywords'])}")
    else:
        click.echo("❌ News monitoring is not running")


async def _get_monitoring_status() -> Dict[str, Any]:
    """Get monitoring status."""
    
    try:
        monitor = NewsMonitor()
        return await monitor.get_status()
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


@news_cli.command('articles')
@click.option('--hours', type=int, default=24, help='Hours to look back')
@click.option('--companies', help='Filter by companies (comma-separated)')
@click.option('--tickers', help='Filter by tickers (comma-separated)')
@click.option('--keywords', help='Filter by keywords (comma-separated)')
@click.option('--sources', help='Filter by sources (comma-separated)')
@click.option('--sentiment', type=click.Choice(['positive', 'negative', 'neutral']), 
              help='Filter by sentiment')
@click.option('--limit', type=int, default=50, help='Maximum articles to show')
@click.option('--format', type=click.Choice(['table', 'json', 'summary']), default='summary')
@click.option('--output', '-o', type=click.Path(), help='Save articles to file')
def get_articles(hours, companies, tickers, keywords, sources, sentiment, limit, format, output):
    """
    Get recent news articles.
    
    Examples:
        researchlab news articles --hours 12 --companies "Apple Inc."
        researchlab news articles --tickers AAPL,GOOGL --sentiment positive
    """
    
    click.echo(f"📰 Getting articles from last {hours} hours...")
    
    # Build filters
    filters = {}
    
    if companies:
        filters['companies'] = [c.strip() for c in companies.split(',')]
    
    if tickers:
        filters['tickers'] = [t.strip().upper() for t in tickers.split(',')]
    
    if keywords:
        filters['keywords'] = [k.strip() for k in keywords.split(',')]
    
    if sources:
        filters['sources'] = [s.strip() for s in sources.split(',')]
    
    if sentiment:
        filters['sentiment'] = sentiment
    
    filters['hours_back'] = hours
    filters['limit'] = limit
    
    articles = asyncio.run(_get_news_articles(filters))
    
    if not articles:
        click.echo("No articles found matching criteria")
        return
    
    click.echo(f"Found {len(articles)} articles")
    
    if format == 'json':
        output_str = json.dumps(articles, indent=2, default=str)
        if output:
            Path(output).write_text(output_str)
            click.echo(f"Articles saved to {output}")
        else:
            click.echo(output_str)
    
    elif format == 'table':
        _display_articles_table(articles)
    
    else:  # summary
        _display_articles_summary(articles)
    
    if output and format != 'json':
        # Save as JSON anyway
        json_output = str(Path(output).with_suffix('.json'))
        with open(json_output, 'w') as f:
            json.dump(articles, f, indent=2, default=str)
        click.echo(f"Articles also saved as JSON to {json_output}")


async def _get_news_articles(filters: Dict[str, Any]) -> List[Dict]:
    """Get news articles with filters."""
    
    try:
        analyzer = NewsAnalyzer()
        return await analyzer.get_articles(filters)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return []


def _display_articles_table(articles: List[Dict]):
    """Display articles in table format."""
    
    click.echo(f"\n{'Time':<8} {'Sentiment':<10} {'Source':<15} {'Title':<50}")
    click.echo("-" * 85)
    
    for article in articles:
        timestamp = article.get('published_at', datetime.now())
        if isinstance(timestamp, str):
            time_str = timestamp[:8]
        else:
            time_str = timestamp.strftime('%H:%M:%S')
        
        sentiment = article.get('sentiment', {}).get('label', 'neutral')
        sentiment_emoji = {
            'positive': '🟢 Pos',
            'negative': '🔴 Neg',
            'neutral': '⚪ Neu'
        }.get(sentiment, '⚪ Neu')
        
        source = article.get('source', 'Unknown')[:13]
        title = article.get('title', 'No title')[:48]
        
        click.echo(f"{time_str:<8} {sentiment_emoji:<10} {source:<15} {title:<50}")


def _display_articles_summary(articles: List[Dict]):
    """Display articles summary."""
    
    click.echo(f"\n📰 Articles Summary ({len(articles)} total)")
    click.echo("=" * 40)
    
    # Group by sentiment
    by_sentiment = {}
    for article in articles:
        sentiment = article.get('sentiment', {}).get('label', 'neutral')
        by_sentiment.setdefault(sentiment, []).append(article)
    
    for sentiment, sentiment_articles in by_sentiment.items():
        sentiment_emoji = {
            'positive': '🟢',
            'negative': '🔴',
            'neutral': '⚪'
        }.get(sentiment, '⚪')
        
        click.echo(f"\n{sentiment_emoji} {sentiment.title()} ({len(sentiment_articles)} articles):")
        
        # Show top articles for this sentiment
        for article in sentiment_articles[:5]:
            title = article.get('title', 'No title')
            source = article.get('source', 'Unknown')
            score = article.get('sentiment', {}).get('score', 0)
            
            click.echo(f"  • {title[:60]}...")
            click.echo(f"    {source} | Score: {score:.2f}")
        
        if len(sentiment_articles) > 5:
            click.echo(f"    ... and {len(sentiment_articles) - 5} more")


@news_cli.command('trends')
@click.option('--hours', type=int, default=24, help='Hours to analyze')
@click.option('--companies', help='Focus on specific companies (comma-separated)')
@click.option('--tickers', help='Focus on specific tickers (comma-separated)')
@click.option('--export', type=click.Path(), help='Export trends to CSV')
def analyze_trends(hours, companies, tickers, export):
    """
    Analyze news trends and sentiment.
    
    Examples:
        researchlab news trends --hours 48
        researchlab news trends --tickers AAPL,GOOGL --export trends.csv
    """
    
    click.echo(f"📈 Analyzing news trends from last {hours} hours...")
    
    filters = {'hours_back': hours}
    
    if companies:
        filters['companies'] = [c.strip() for c in companies.split(',')]
    
    if tickers:
        filters['tickers'] = [t.strip().upper() for t in tickers.split(',')]
    
    trends = asyncio.run(_analyze_news_trends(filters))
    
    if not trends:
        click.echo("No trends data available")
        return
    
    _display_trends(trends)
    
    if export:
        _export_trends_csv(trends, export)
        click.echo(f"📊 Trends exported to {export}")


async def _analyze_news_trends(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze news trends."""
    
    try:
        analyzer = NewsAnalyzer()
        return await analyzer.analyze_trends(filters)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _display_trends(trends: Dict[str, Any]):
    """Display trends analysis."""
    
    click.echo(f"\n📊 News Trends Analysis")
    click.echo("=" * 30)
    
    # Overall sentiment
    overall = trends.get('overall_sentiment', {})
    if overall:
        click.echo(f"Overall Sentiment: {overall.get('label', 'neutral').title()}")
        click.echo(f"Average Score: {overall.get('average_score', 0):.2f}")
        click.echo(f"Total Articles: {overall.get('total_articles', 0)}")
    
    # Sentiment breakdown
    breakdown = trends.get('sentiment_breakdown', {})
    if breakdown:
        click.echo(f"\nSentiment Breakdown:")
        for sentiment, count in breakdown.items():
            percentage = (count / overall.get('total_articles', 1)) * 100
            click.echo(f"  {sentiment.title()}: {count} ({percentage:.1f}%)")
    
    # Top keywords
    keywords = trends.get('trending_keywords', [])
    if keywords:
        click.echo(f"\nTrending Keywords:")
        for i, (keyword, frequency) in enumerate(keywords[:10], 1):
            click.echo(f"  {i}. {keyword} ({frequency} mentions)")
    
    # Company trends
    company_trends = trends.get('company_trends', {})
    if company_trends:
        click.echo(f"\nCompany Sentiment:")
        for company, data in company_trends.items():
            sentiment = data.get('sentiment', 'neutral')
            score = data.get('average_score', 0)
            count = data.get('article_count', 0)
            
            sentiment_emoji = {
                'positive': '🟢',
                'negative': '🔴',
                'neutral': '⚪'
            }.get(sentiment, '⚪')
            
            click.echo(f"  {sentiment_emoji} {company}: {sentiment} ({score:.2f}, {count} articles)")
    
    # Time trends
    time_trends = trends.get('time_trends', [])
    if time_trends:
        click.echo(f"\nTrend Over Time:")
        for period in time_trends[-5:]:  # Show last 5 periods
            period_str = period.get('period', 'Unknown')
            sentiment = period.get('average_sentiment', 0)
            count = period.get('article_count', 0)
            
            trend_indicator = "📈" if sentiment > 0 else "📉" if sentiment < 0 else "➡️"
            click.echo(f"  {trend_indicator} {period_str}: {sentiment:+.2f} ({count} articles)")


def _export_trends_csv(trends: Dict[str, Any], export_path: str):
    """Export trends to CSV."""
    
    try:
        import csv
        
        with open(export_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow(['Metric', 'Value', 'Details'])
            
            # Overall sentiment
            overall = trends.get('overall_sentiment', {})
            if overall:
                writer.writerow([
                    'Overall Sentiment',
                    overall.get('label', 'neutral'),
                    f"Score: {overall.get('average_score', 0):.2f}, Articles: {overall.get('total_articles', 0)}"
                ])
            
            # Company trends
            company_trends = trends.get('company_trends', {})
            for company, data in company_trends.items():
                writer.writerow([
                    f'Company: {company}',
                    data.get('sentiment', 'neutral'),
                    f"Score: {data.get('average_score', 0):.2f}, Articles: {data.get('article_count', 0)}"
                ])
            
            # Keywords
            keywords = trends.get('trending_keywords', [])
            for keyword, frequency in keywords:
                writer.writerow(['Trending Keyword', keyword, f'Frequency: {frequency}'])
            
    except Exception as e:
        click.echo(f"Error exporting CSV: {e}")


@news_cli.command('analyze')
@click.argument('article_id')
@click.option('--targets', help='Analysis targets: companies, tickers (comma-separated)')
@click.option('--deep', is_flag=True, help='Perform deep analysis')
def analyze_article(article_id, targets, deep):
    """
    Analyze specific article.
    
    Examples:
        researchlab news analyze article_12345
        researchlab news analyze article_12345 --targets AAPL,GOOGL --deep
    """
    
    click.echo(f"🔍 Analyzing article {article_id}...")
    
    analysis_config = {
        'article_id': article_id,
        'deep_analysis': deep
    }
    
    if targets:
        analysis_config['targets'] = [t.strip() for t in targets.split(',')]
        click.echo(f"Focusing on: {', '.join(analysis_config['targets'])}")
    
    analysis = asyncio.run(_analyze_article(analysis_config))
    
    if analysis:
        _display_article_analysis(analysis)
    else:
        click.echo(f"❌ Could not analyze article {article_id}")
        return 1


async def _analyze_article(config: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze specific article."""
    
    try:
        analyzer = NewsAnalyzer()
        return await analyzer.analyze_article(config)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _display_article_analysis(analysis: Dict[str, Any]):
    """Display article analysis results."""
    
    click.echo(f"\n📋 Article Analysis")
    click.echo("=" * 25)
    
    # Basic info
    title = analysis.get('title', 'No title')
    click.echo(f"Title: {title}")
    
    source = analysis.get('source', 'Unknown')
    click.echo(f"Source: {source}")
    
    published = analysis.get('published_at', 'Unknown')
    click.echo(f"Published: {published}")
    
    # Sentiment
    sentiment_data = analysis.get('sentiment', {})
    if sentiment_data:
        sentiment = sentiment_data.get('label', 'neutral')
        score = sentiment_data.get('score', 0)
        confidence = sentiment_data.get('confidence', 0)
        
        sentiment_emoji = {
            'positive': '🟢',
            'negative': '🔴',
            'neutral': '⚪'
        }.get(sentiment, '⚪')
        
        click.echo(f"Sentiment: {sentiment_emoji} {sentiment.title()} (Score: {score:.2f}, Confidence: {confidence:.2f})")
    
    # Entities
    entities = analysis.get('entities', {})
    if entities:
        click.echo(f"\n🏷️  Entities:")
        
        for entity_type, entity_list in entities.items():
            if entity_list:
                click.echo(f"  {entity_type.title()}: {', '.join(entity_list[:5])}")
                if len(entity_list) > 5:
                    click.echo(f"    ... and {len(entity_list) - 5} more")
    
    # Key themes
    themes = analysis.get('key_themes', [])
    if themes:
        click.echo(f"\n🎯 Key Themes:")
        for theme in themes[:5]:
            click.echo(f"  • {theme}")
    
    # Impact assessment
    impact = analysis.get('impact_assessment', {})
    if impact:
        click.echo(f"\n📊 Impact Assessment:")
        
        for target, impact_data in impact.items():
            impact_level = impact_data.get('level', 'low')
            reasoning = impact_data.get('reasoning', 'No reasoning provided')
            
            impact_emoji = {
                'high': '🔴',
                'medium': '🟡',
                'low': '🟢'
            }.get(impact_level, '⚪')
            
            click.echo(f"  {impact_emoji} {target}: {impact_level.title()} impact")
            click.echo(f"    {reasoning}")


@news_cli.command('export')
@click.option('--hours', type=int, default=24, help='Hours of data to export')
@click.option('--format', type=click.Choice(['json', 'csv', 'excel']), default='json')
@click.option('--output', '-o', required=True, type=click.Path(), help='Output file')
@click.option('--companies', help='Filter by companies (comma-separated)')
@click.option('--tickers', help='Filter by tickers (comma-separated)')
def export_news_data(hours, format, output, companies, tickers):
    """
    Export news data.
    
    Examples:
        researchlab news export --hours 48 --format csv --output news_data.csv
        researchlab news export --tickers AAPL,GOOGL --output apple_google_news.json
    """
    
    click.echo(f"📤 Exporting {hours} hours of news data...")
    
    filters = {'hours_back': hours}
    
    if companies:
        filters['companies'] = [c.strip() for c in companies.split(',')]
    
    if tickers:
        filters['tickers'] = [t.strip().upper() for t in tickers.split(',')]
    
    success = asyncio.run(_export_news_data(filters, format, output))
    
    if success:
        click.echo(f"✅ News data exported to {output}")
    else:
        click.echo("❌ Failed to export news data")
        return 1


async def _export_news_data(filters: Dict[str, Any], format: str, output: str) -> bool:
    """Export news data to file."""
    
    try:
        analyzer = NewsAnalyzer()
        data = await analyzer.export_data(filters, format)
        
        if format == 'json':
            with open(output, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        
        elif format == 'csv':
            import csv
            
            with open(output, 'w', newline='') as csvfile:
                if data:
                    writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
        
        elif format == 'excel':
            try:
                import pandas as pd
                df = pd.DataFrame(data)
                df.to_excel(output, index=False)
            except ImportError:
                click.echo("❌ pandas required for Excel export. Install with: pip install pandas openpyxl")
                return False
        
        return True
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False