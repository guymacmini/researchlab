"""SEC EDGAR CLI commands."""

import click
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from src.data.sec_edgar import SECEDGARManager, SECEDGARClient


@click.group()
def sec_cli():
    """SEC EDGAR data access commands."""
    pass


@sec_cli.command('filings')
@click.argument('symbol')
@click.option('--form-types', help='Comma-separated form types (default: 10-K,10-Q)')
@click.option('--limit', type=int, default=5, help='Maximum number of filings to retrieve')
@click.option('--output', '-o', type=click.Path(), help='Save filings list to file')
@click.option('--format', type=click.Choice(['table', 'json']), default='table')
def get_filings(symbol, form_types, limit, output, format):
    """
    Get SEC filings for a company.
    
    Examples:
        researchlab sec filings AAPL
        researchlab sec filings AAPL --form-types 10-K --limit 3
        researchlab sec filings GOOGL --format json --output googl_filings.json
    """
    
    click.echo(f"🔍 Getting SEC filings for {symbol}...")
    
    # Parse form types
    if form_types:
        form_types_list = [t.strip() for t in form_types.split(',')]
    else:
        form_types_list = ["10-K", "10-Q"]
    
    click.echo(f"Form types: {', '.join(form_types_list)}")
    click.echo(f"Limit: {limit}")
    
    filings = asyncio.run(_get_company_filings(symbol, form_types_list, limit))
    
    if not filings:
        click.echo(f"❌ No filings found for {symbol}")
        return 1
    
    if format == 'json':
        output_str = json.dumps([f.dict() for f in filings], indent=2, default=str)
        if output:
            Path(output).write_text(output_str)
            click.echo(f"Filings saved to {output}")
        else:
            click.echo(output_str)
    
    else:  # table format
        _display_filings_table(filings)
        
        if output:
            json_output = str(Path(output).with_suffix('.json'))
            with open(json_output, 'w') as f:
                json.dump([f.dict() for f in filings], f, indent=2, default=str)
            click.echo(f"Filings also saved as JSON to {json_output}")


async def _get_company_filings(symbol: str, form_types: List[str], limit: int):
    """Get company filings using SEC EDGAR client."""
    try:
        client = SECEDGARClient()
        filings = await client.get_company_filings(
            symbol=symbol,
            form_types=form_types,
            limit=limit
        )
        return filings
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return []


def _display_filings_table(filings):
    """Display filings in table format."""
    
    click.echo(f"\n📋 SEC Filings ({len(filings)} found)")
    click.echo("=" * 80)
    click.echo(f"{'Form':<8} {'Filing Date':<12} {'Company':<25} {'Accession Number':<20}")
    click.echo("-" * 80)
    
    for filing in filings:
        form_type = filing.form_type
        filing_date = filing.filing_date.strftime('%Y-%m-%d')
        company_name = filing.company_name[:23] + '..' if len(filing.company_name) > 25 else filing.company_name
        accession = filing.accession_number[:18] + '..' if len(filing.accession_number) > 20 else filing.accession_number
        
        click.echo(f"{form_type:<8} {filing_date:<12} {company_name:<25} {accession:<20}")


@sec_cli.command('financial')
@click.argument('symbol')
@click.option('--periods', type=int, default=4, help='Number of periods to analyze')
@click.option('--quarterly', is_flag=True, help='Include quarterly filings (10-Q)')
@click.option('--output', '-o', type=click.Path(), help='Save financial data to file')
@click.option('--format', type=click.Choice(['summary', 'detailed', 'json']), default='summary')
def get_financial_data(symbol, periods, quarterly, output, format):
    """
    Get comprehensive financial data for a company.
    
    Examples:
        researchlab sec financial AAPL
        researchlab sec financial MSFT --periods 8 --quarterly
        researchlab sec financial GOOGL --format json --output googl_financial.json
    """
    
    click.echo(f"📊 Getting financial data for {symbol}...")
    click.echo(f"Periods: {periods}")
    click.echo(f"Include quarterly: {'Yes' if quarterly else 'No'}")
    
    data = asyncio.run(_get_financial_data(symbol, periods, quarterly))
    
    if not data or "error" in data:
        click.echo(f"❌ Failed to get financial data for {symbol}")
        if "error" in data:
            click.echo(f"Error: {data['error']}")
        return 1
    
    if format == 'json':
        output_str = json.dumps(data, indent=2, default=str)
        if output:
            Path(output).write_text(output_str)
            click.echo(f"Financial data saved to {output}")
        else:
            click.echo(output_str)
    
    elif format == 'detailed':
        _display_financial_detailed(data)
        
        if output:
            with open(output, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            click.echo(f"Detailed data saved to {output}")
    
    else:  # summary
        _display_financial_summary(data)
        
        if output:
            with open(output, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            click.echo(f"Summary data saved to {output}")


async def _get_financial_data(symbol: str, periods: int, include_quarterly: bool):
    """Get financial data using SEC EDGAR manager."""
    try:
        manager = SECEDGARManager()
        data = await manager.get_company_financial_data(
            symbol=symbol,
            periods=periods,
            include_quarterly=include_quarterly
        )
        return data
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return {"error": str(e)}


def _display_financial_summary(data: Dict[str, Any]):
    """Display financial data summary."""
    
    click.echo(f"\n💰 Financial Summary - {data.get('company_name', 'Unknown Company')}")
    click.echo("=" * 60)
    
    summary = data.get('financial_summary', {})
    
    click.echo(f"Symbol: {data.get('symbol', 'N/A')}")
    click.echo(f"CIK: {data.get('cik', 'N/A')}")
    click.echo(f"Periods Analyzed: {summary.get('periods_analyzed', 0)}")
    
    if summary.get('latest_filing_date'):
        latest_date = summary['latest_filing_date'][:10]  # Just the date part
        click.echo(f"Latest Filing: {latest_date}")
    
    # Display periods data
    periods_data = summary.get('periods_data', [])
    if periods_data:
        click.echo(f"\n📈 Financial Metrics (in millions):")
        click.echo(f"{'Period':<12} {'Revenue':<15} {'Net Income':<15} {'Total Assets':<15}")
        click.echo("-" * 60)
        
        for period in periods_data[:5]:  # Show first 5 periods
            period_date = period.get('filing_date', 'N/A')[:10]
            revenue = period.get('revenue')
            net_income = period.get('net_income')
            total_assets = period.get('total_assets')
            
            revenue_str = f"{revenue/1000000:.0f}M" if revenue else "N/A"
            income_str = f"{net_income/1000000:.0f}M" if net_income else "N/A"
            assets_str = f"{total_assets/1000000:.0f}M" if total_assets else "N/A"
            
            click.echo(f"{period_date:<12} {revenue_str:<15} {income_str:<15} {assets_str:<15}")
    
    # Display trends
    trends = summary.get('trends', {})
    if trends:
        click.echo(f"\n📊 Growth Trends (Period-over-Period):")
        for metric, growth in trends.items():
            metric_name = metric.replace('_growth', '').replace('_', ' ').title()
            growth_str = f"{growth:+.1f}%" if growth is not None else "N/A"
            click.echo(f"  {metric_name}: {growth_str}")


def _display_financial_detailed(data: Dict[str, Any]):
    """Display detailed financial data."""
    
    _display_financial_summary(data)
    
    click.echo(f"\n📋 Detailed Filing Information")
    click.echo("=" * 50)
    
    filings = data.get('filings', [])
    
    for i, filing in enumerate(filings[:3], 1):  # Show first 3 filings
        click.echo(f"\n{i}. {filing.get('form_type')} - {filing.get('filing_date', 'N/A')[:10]}")
        
        # Business description
        if filing.get('business_description'):
            business = filing['business_description'][:200] + "..." if len(filing['business_description']) > 200 else filing['business_description']
            click.echo(f"   Business: {business}")
        
        # Risk factors
        risk_factors = filing.get('risk_factors', [])
        if risk_factors:
            click.echo(f"   Risk Factors ({len(risk_factors)}):")
            for j, risk in enumerate(risk_factors[:3], 1):
                risk_short = risk[:100] + "..." if len(risk) > 100 else risk
                click.echo(f"     {j}. {risk_short}")
        
        # Financial highlights
        financial_data = filing.get('financial_data', {})
        if financial_data:
            income = financial_data.get('income_statement', {})
            balance = financial_data.get('balance_sheet', {})
            
            click.echo(f"   Financial Highlights:")
            if income.get('revenue'):
                click.echo(f"     Revenue: ${income['revenue']:,.0f}")
            if income.get('net_income'):
                click.echo(f"     Net Income: ${income['net_income']:,.0f}")
            if balance.get('total_assets'):
                click.echo(f"     Total Assets: ${balance['total_assets']:,.0f}")


@sec_cli.command('search')
@click.argument('symbol')
@click.argument('search_terms', nargs=-1, required=True)
@click.option('--form-types', help='Comma-separated form types (default: 10-K,10-Q)')
@click.option('--output', '-o', type=click.Path(), help='Save search results to file')
def search_filings(symbol, search_terms, form_types, output):
    """
    Search filing content for specific terms.
    
    Examples:
        researchlab sec search AAPL "artificial intelligence" "machine learning"
        researchlab sec search TSLA "climate change" "carbon emissions"
        researchlab sec search MSFT "cloud computing" --form-types 10-K
    """
    
    click.echo(f"🔍 Searching {symbol} filings for: {', '.join(search_terms)}")
    
    # Parse form types
    if form_types:
        form_types_list = [t.strip() for t in form_types.split(',')]
    else:
        form_types_list = ["10-K", "10-Q"]
    
    results = asyncio.run(_search_filing_content(symbol, list(search_terms), form_types_list))
    
    if not results:
        click.echo(f"❌ No matches found for search terms")
        return
    
    _display_search_results(results, search_terms)
    
    if output:
        with open(output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        click.echo(f"Search results saved to {output}")


async def _search_filing_content(symbol: str, search_terms: List[str], form_types: List[str]):
    """Search filing content."""
    try:
        manager = SECEDGARManager()
        results = await manager.search_filings_by_content(
            symbol=symbol,
            search_terms=search_terms,
            form_types=form_types
        )
        return results
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return []


def _display_search_results(results: List[Dict], search_terms: List[str]):
    """Display search results."""
    
    click.echo(f"\n🎯 Search Results ({len(results)} filings with matches)")
    click.echo("=" * 60)
    
    for i, result in enumerate(results, 1):
        filing = result['filing']
        matches = result['matches']
        
        click.echo(f"\n{i}. {filing['form_type']} - {filing['filing_date'][:10]}")
        click.echo(f"   Company: {filing['company_name']}")
        click.echo(f"   Matches: {len(matches)} terms found")
        
        for match in matches:
            term = match['term']
            context = match['context']
            
            # Highlight the search term in context
            highlighted_context = context.replace(
                term, 
                f"**{term}**"
            )
            
            # Truncate long context
            if len(highlighted_context) > 150:
                highlighted_context = highlighted_context[:147] + "..."
            
            click.echo(f"   🔍 '{term}': {highlighted_context}")


@sec_cli.command('cik')
@click.argument('symbol')
def get_company_cik(symbol):
    """
    Get CIK (Central Index Key) for a company symbol.
    
    Examples:
        researchlab sec cik AAPL
        researchlab sec cik GOOGL
    """
    
    click.echo(f"🔍 Getting CIK for {symbol}...")
    
    cik = asyncio.run(_get_cik(symbol))
    
    if cik:
        click.echo(f"✅ CIK for {symbol}: {cik}")
        click.echo(f"SEC URL: https://www.sec.gov/cgi-bin/browse-edgar?CIK={cik}")
    else:
        click.echo(f"❌ CIK not found for {symbol}")
        return 1


async def _get_cik(symbol: str):
    """Get CIK for symbol."""
    try:
        client = SECEDGARClient()
        cik = await client.get_company_cik(symbol)
        return cik
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


@sec_cli.command('download')
@click.argument('symbol')
@click.argument('accession_number')
@click.option('--output', '-o', type=click.Path(), help='Output file for document')
@click.option('--format', type=click.Choice(['html', 'text']), default='html')
def download_filing(symbol, accession_number, output, format):
    """
    Download a specific filing document.
    
    Examples:
        researchlab sec download AAPL 0000320193-24-000001
        researchlab sec download AAPL 0000320193-24-000001 --output aapl_10k.html
    """
    
    click.echo(f"⬇️  Downloading filing {accession_number} for {symbol}...")
    
    result = asyncio.run(_download_filing_document(symbol, accession_number, format))
    
    if not result:
        click.echo("❌ Failed to download filing")
        return 1
    
    content, filing_info = result
    
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(content)
        click.echo(f"✅ Filing saved to {output}")
        click.echo(f"Size: {len(content):,} characters")
    else:
        # Display preview
        preview = content[:1000] + "..." if len(content) > 1000 else content
        click.echo(f"\n📄 Document Preview:")
        click.echo("-" * 40)
        click.echo(preview)
        click.echo(f"\n[Full document: {len(content):,} characters]")
    
    # Display filing info
    if filing_info:
        click.echo(f"\n📋 Filing Information:")
        click.echo(f"  Company: {filing_info.get('company_name', 'N/A')}")
        click.echo(f"  Form Type: {filing_info.get('form_type', 'N/A')}")
        click.echo(f"  Filing Date: {filing_info.get('filing_date', 'N/A')}")


async def _download_filing_document(symbol: str, accession_number: str, format_type: str):
    """Download filing document."""
    try:
        client = SECEDGARClient()
        
        # First get the filing info
        filings = await client.get_company_filings(symbol, limit=20)
        
        target_filing = None
        for filing in filings:
            if filing.accession_number == accession_number:
                target_filing = filing
                break
        
        if not target_filing:
            click.echo(f"❌ Filing {accession_number} not found for {symbol}")
            return None
        
        # Download document
        content = await client.download_filing_document(target_filing)
        
        if not content:
            return None
        
        # Convert to text if requested
        if format_type == 'text':
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            content = soup.get_text()
        
        return content, target_filing.dict()
    
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


@sec_cli.command('analyze')
@click.argument('symbol')
@click.option('--metrics', help='Specific metrics to analyze (revenue,assets,income)')
@click.option('--periods', type=int, default=4, help='Number of periods for trend analysis')
@click.option('--output', '-o', type=click.Path(), help='Save analysis to file')
def analyze_financials(symbol, metrics, periods, output):
    """
    Analyze financial metrics and trends.
    
    Examples:
        researchlab sec analyze AAPL
        researchlab sec analyze MSFT --metrics revenue,income --periods 8
        researchlab sec analyze GOOGL --output googl_analysis.json
    """
    
    click.echo(f"📊 Analyzing financial metrics for {symbol}...")
    
    # Parse specific metrics
    if metrics:
        metrics_list = [m.strip() for m in metrics.split(',')]
        click.echo(f"Focus metrics: {', '.join(metrics_list)}")
    else:
        metrics_list = None
    
    analysis = asyncio.run(_analyze_financial_metrics(symbol, periods, metrics_list))
    
    if not analysis:
        click.echo(f"❌ Failed to analyze {symbol}")
        return 1
    
    _display_financial_analysis(analysis)
    
    if output:
        with open(output, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)
        click.echo(f"Analysis saved to {output}")


async def _analyze_financial_metrics(symbol: str, periods: int, focus_metrics: List[str] = None):
    """Analyze financial metrics."""
    try:
        manager = SECEDGARManager()
        data = await manager.get_company_financial_data(symbol, periods=periods)
        
        if "error" in data:
            return None
        
        # Perform additional analysis
        analysis = {
            "symbol": symbol,
            "company_name": data.get("company_name"),
            "analysis_date": datetime.now().isoformat(),
            "periods_analyzed": periods,
            "focus_metrics": focus_metrics,
            "financial_analysis": _calculate_financial_ratios(data),
            "trend_analysis": _analyze_trends(data),
            "raw_data": data
        }
        
        return analysis
    
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _calculate_financial_ratios(data: Dict) -> Dict:
    """Calculate key financial ratios."""
    ratios = {}
    
    periods_data = data.get('financial_summary', {}).get('periods_data', [])
    
    if periods_data:
        latest = periods_data[0]
        
        # Calculate ratios from latest period
        revenue = latest.get('revenue')
        net_income = latest.get('net_income')
        total_assets = latest.get('total_assets')
        shareholders_equity = latest.get('shareholders_equity')
        
        if revenue and net_income:
            ratios['profit_margin'] = (net_income / revenue) * 100
        
        if net_income and total_assets:
            ratios['roa'] = (net_income / total_assets) * 100  # Return on Assets
        
        if net_income and shareholders_equity:
            ratios['roe'] = (net_income / shareholders_equity) * 100  # Return on Equity
        
        if total_assets and shareholders_equity:
            ratios['debt_to_equity'] = ((total_assets - shareholders_equity) / shareholders_equity) * 100
    
    return ratios


def _analyze_trends(data: Dict) -> Dict:
    """Analyze trends in financial data."""
    trend_analysis = {}
    
    periods_data = data.get('financial_summary', {}).get('periods_data', [])
    
    if len(periods_data) >= 2:
        # Calculate average growth rates
        metrics = ['revenue', 'net_income', 'total_assets']
        
        for metric in metrics:
            values = [period.get(metric) for period in periods_data if period.get(metric) is not None]
            
            if len(values) >= 2:
                # Calculate period-over-period growth rates
                growth_rates = []
                for i in range(1, len(values)):
                    if values[i-1] != 0:
                        growth_rate = ((values[i-1] - values[i]) / abs(values[i])) * 100
                        growth_rates.append(growth_rate)
                
                if growth_rates:
                    trend_analysis[f'{metric}_avg_growth'] = sum(growth_rates) / len(growth_rates)
                    trend_analysis[f'{metric}_growth_volatility'] = max(growth_rates) - min(growth_rates)
    
    return trend_analysis


def _display_financial_analysis(analysis: Dict):
    """Display financial analysis results."""
    
    click.echo(f"\n🎯 Financial Analysis - {analysis.get('company_name', 'Unknown')}")
    click.echo("=" * 60)
    
    click.echo(f"Symbol: {analysis.get('symbol')}")
    click.echo(f"Periods Analyzed: {analysis.get('periods_analyzed')}")
    click.echo(f"Analysis Date: {analysis.get('analysis_date', '')[:10]}")
    
    # Display financial ratios
    ratios = analysis.get('financial_analysis', {})
    if ratios:
        click.echo(f"\n💡 Key Financial Ratios:")
        for ratio_name, ratio_value in ratios.items():
            ratio_display = ratio_name.replace('_', ' ').title()
            if ratio_value is not None:
                click.echo(f"  {ratio_display}: {ratio_value:.2f}%")
    
    # Display trend analysis
    trends = analysis.get('trend_analysis', {})
    if trends:
        click.echo(f"\n📈 Trend Analysis:")
        for trend_name, trend_value in trends.items():
            trend_display = trend_name.replace('_', ' ').title()
            if trend_value is not None:
                click.echo(f"  {trend_display}: {trend_value:+.2f}%")
    
    # Display interpretation
    _display_analysis_interpretation(ratios, trends)


def _display_analysis_interpretation(ratios: Dict, trends: Dict):
    """Display analysis interpretation."""
    
    click.echo(f"\n🧠 Analysis Interpretation:")
    
    # Interpret profit margin
    profit_margin = ratios.get('profit_margin')
    if profit_margin is not None:
        if profit_margin > 20:
            click.echo(f"  💰 Excellent profit margin ({profit_margin:.1f}%) - highly efficient operations")
        elif profit_margin > 10:
            click.echo(f"  ✅ Good profit margin ({profit_margin:.1f}%) - solid profitability")
        elif profit_margin > 5:
            click.echo(f"  ⚠️  Moderate profit margin ({profit_margin:.1f}%) - room for improvement")
        else:
            click.echo(f"  ❌ Low profit margin ({profit_margin:.1f}%) - efficiency concerns")
    
    # Interpret ROE
    roe = ratios.get('roe')
    if roe is not None:
        if roe > 15:
            click.echo(f"  🎯 Strong ROE ({roe:.1f}%) - excellent shareholder returns")
        elif roe > 10:
            click.echo(f"  ✅ Good ROE ({roe:.1f}%) - solid shareholder returns")
        elif roe > 5:
            click.echo(f"  ⚠️  Moderate ROE ({roe:.1f}%) - average returns")
        else:
            click.echo(f"  ❌ Low ROE ({roe:.1f}%) - poor shareholder returns")
    
    # Interpret debt to equity
    debt_to_equity = ratios.get('debt_to_equity')
    if debt_to_equity is not None:
        if debt_to_equity < 50:
            click.echo(f"  💪 Conservative debt levels ({debt_to_equity:.1f}%) - low financial risk")
        elif debt_to_equity < 100:
            click.echo(f"  ✅ Moderate debt levels ({debt_to_equity:.1f}%) - balanced capital structure")
        else:
            click.echo(f"  ⚠️  High debt levels ({debt_to_equity:.1f}%) - elevated financial risk")
    
    # Interpret revenue growth
    revenue_growth = trends.get('revenue_avg_growth')
    if revenue_growth is not None:
        if revenue_growth > 10:
            click.echo(f"  🚀 Strong revenue growth ({revenue_growth:+.1f}%) - expanding business")
        elif revenue_growth > 5:
            click.echo(f"  ✅ Solid revenue growth ({revenue_growth:+.1f}%) - healthy expansion")
        elif revenue_growth > 0:
            click.echo(f"  ⚠️  Slow revenue growth ({revenue_growth:+.1f}%) - limited expansion")
        else:
            click.echo(f"  ❌ Revenue decline ({revenue_growth:+.1f}%) - concerning trend")
    
    click.echo(f"\n💡 Note: Analysis based on SEC filings. Consider market conditions and industry context.")


@sec_cli.command('validate')
@click.argument('symbol')
def validate_data(symbol):
    """
    Validate SEC data availability and quality for a symbol.
    
    Examples:
        researchlab sec validate AAPL
        researchlab sec validate UNKNOWN
    """
    
    click.echo(f"🔍 Validating SEC data for {symbol}...")
    
    validation = asyncio.run(_validate_sec_data(symbol))
    
    _display_validation_results(validation)


async def _validate_sec_data(symbol: str):
    """Validate SEC data availability."""
    validation = {
        "symbol": symbol,
        "cik_found": False,
        "filings_available": False,
        "recent_filings_count": 0,
        "financial_data_parseable": False,
        "data_quality_score": 0,
        "issues": []
    }
    
    try:
        client = SECEDGARClient()
        
        # Check CIK
        cik = await client.get_company_cik(symbol)
        if cik:
            validation["cik_found"] = True
            validation["cik"] = cik
        else:
            validation["issues"].append(f"CIK not found for symbol {symbol}")
            return validation
        
        # Check filings
        filings = await client.get_company_filings(symbol, limit=10)
        if filings:
            validation["filings_available"] = True
            validation["recent_filings_count"] = len(filings)
            
            # Check data quality
            recent_10k = next((f for f in filings if f.form_type == "10-K"), None)
            if recent_10k:
                # Try to download and parse a document
                content = await client.download_filing_document(recent_10k)
                if content and len(content) > 10000:  # Reasonable size
                    validation["financial_data_parseable"] = True
                else:
                    validation["issues"].append("Filing document appears incomplete")
            else:
                validation["issues"].append("No recent 10-K filings found")
        else:
            validation["issues"].append("No filings found")
        
        # Calculate quality score
        score = 0
        if validation["cik_found"]:
            score += 25
        if validation["filings_available"]:
            score += 25
        if validation["recent_filings_count"] >= 5:
            score += 25
        if validation["financial_data_parseable"]:
            score += 25
        
        validation["data_quality_score"] = score
        
    except Exception as e:
        validation["issues"].append(f"Validation error: {str(e)}")
    
    return validation


def _display_validation_results(validation: Dict):
    """Display validation results."""
    
    click.echo(f"\n✅ SEC Data Validation - {validation['symbol']}")
    click.echo("=" * 50)
    
    score = validation["data_quality_score"]
    if score >= 75:
        click.echo(f"🟢 Data Quality: Excellent ({score}/100)")
    elif score >= 50:
        click.echo(f"🟡 Data Quality: Good ({score}/100)")
    elif score >= 25:
        click.echo(f"🟠 Data Quality: Fair ({score}/100)")
    else:
        click.echo(f"🔴 Data Quality: Poor ({score}/100)")
    
    # Details
    click.echo(f"\n📋 Validation Details:")
    click.echo(f"  CIK Found: {'✅' if validation['cik_found'] else '❌'}")
    if validation.get('cik'):
        click.echo(f"  CIK: {validation['cik']}")
    
    click.echo(f"  Filings Available: {'✅' if validation['filings_available'] else '❌'}")
    click.echo(f"  Recent Filings Count: {validation['recent_filings_count']}")
    click.echo(f"  Financial Data Parseable: {'✅' if validation['financial_data_parseable'] else '❌'}")
    
    # Issues
    issues = validation.get("issues", [])
    if issues:
        click.echo(f"\n⚠️  Issues Found:")
        for i, issue in enumerate(issues, 1):
            click.echo(f"  {i}. {issue}")
    
    # Recommendations
    if score < 75:
        click.echo(f"\n💡 Recommendations:")
        if not validation["cik_found"]:
            click.echo(f"  - Verify symbol is correct and company is SEC-registered")
        if validation["recent_filings_count"] < 5:
            click.echo(f"  - Company may have limited filing history")
        if not validation["financial_data_parseable"]:
            click.echo(f"  - Filing documents may have parsing issues")


@sec_cli.command('bulk')
@click.argument('symbols_file', type=click.Path(exists=True))
@click.option('--output-dir', type=click.Path(), help='Output directory for results')
@click.option('--format', type=click.Choice(['json', 'csv']), default='json')
@click.option('--max-concurrent', type=int, default=3, help='Maximum concurrent requests')
def bulk_download(symbols_file, output_dir, format, max_concurrent):
    """
    Bulk download SEC data for multiple symbols from file.
    
    Input file should contain one symbol per line.
    
    Examples:
        researchlab sec bulk symbols.txt --output-dir sec_data
        researchlab sec bulk sp500.txt --format csv --max-concurrent 5
    """
    
    click.echo(f"📦 Starting bulk SEC data download...")
    click.echo(f"Input file: {symbols_file}")
    click.echo(f"Max concurrent: {max_concurrent}")
    
    # Read symbols
    try:
        with open(symbols_file, 'r') as f:
            symbols = [line.strip().upper() for line in f if line.strip()]
    except Exception as e:
        click.echo(f"❌ Error reading symbols file: {e}")
        return 1
    
    if not symbols:
        click.echo(f"❌ No symbols found in file")
        return 1
    
    click.echo(f"Found {len(symbols)} symbols to process")
    
    # Create output directory
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Process symbols
    results = asyncio.run(_bulk_process_symbols(symbols, max_concurrent))
    
    # Save results
    if output_dir:
        _save_bulk_results(results, output_dir, format)
    
    # Summary
    successful = len([r for r in results if r.get('success', False)])
    click.echo(f"\n✅ Bulk processing complete:")
    click.echo(f"  Total symbols: {len(symbols)}")
    click.echo(f"  Successful: {successful}")
    click.echo(f"  Failed: {len(symbols) - successful}")


async def _bulk_process_symbols(symbols: List[str], max_concurrent: int):
    """Process multiple symbols concurrently."""
    import asyncio
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_symbol(symbol):
        async with semaphore:
            try:
                manager = SECEDGARManager()
                data = await manager.get_company_financial_data(symbol, periods=2)
                
                if "error" not in data:
                    return {"symbol": symbol, "success": True, "data": data}
                else:
                    return {"symbol": symbol, "success": False, "error": data["error"]}
            
            except Exception as e:
                return {"symbol": symbol, "success": False, "error": str(e)}
    
    tasks = [process_symbol(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks)
    
    return results


def _save_bulk_results(results: List[Dict], output_dir: str, format_type: str):
    """Save bulk processing results."""
    
    output_path = Path(output_dir)
    
    if format_type == 'json':
        # Save each symbol as separate JSON file
        for result in results:
            symbol = result['symbol']
            filename = f"{symbol.lower()}_sec_data.json"
            filepath = output_path / filename
            
            with open(filepath, 'w') as f:
                json.dump(result, f, indent=2, default=str)
        
        # Also save summary
        summary_file = output_path / "bulk_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
    
    elif format_type == 'csv':
        # Create CSV summary
        import csv
        
        csv_file = output_path / "sec_bulk_summary.csv"
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Symbol', 'Success', 'Company Name', 'CIK', 'Filings Count', 'Error'])
            
            for result in results:
                symbol = result['symbol']
                success = result.get('success', False)
                
                if success:
                    data = result.get('data', {})
                    company_name = data.get('company_name', '')
                    cik = data.get('cik', '')
                    filings_count = len(data.get('filings', []))
                    error = ''
                else:
                    company_name = ''
                    cik = ''
                    filings_count = 0
                    error = result.get('error', 'Unknown error')
                
                writer.writerow([symbol, success, company_name, cik, filings_count, error])
    
    click.echo(f"Results saved to {output_dir}")


# Add helpful aliases
@click.command()
@click.argument('symbol')
def quick_financials(symbol):
    """Quick financial summary (alias for 'sec financial')."""
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(get_financial_data, [symbol])
    click.echo(result.output)