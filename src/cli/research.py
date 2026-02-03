"""Research project CLI commands."""

import click
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from src.api.research import (
    ResearchRequest, CompanyInfo, ResearchResponse, 
    ResearchStatus, ResearchResults
)
from src.core.workflow import ResearchWorkflowOrchestrator


@click.group()
def research_cli():
    """Research project management commands."""
    pass


@research_cli.command('start')
@click.argument('query')
@click.option('--companies', '-c', required=True, help='Comma-separated list of company symbols')
@click.option('--thesis', '-t', help='Investment thesis statement')
@click.option('--horizon', '-h', type=int, default=12, help='Time horizon in months')
@click.option('--risk', type=click.Choice(['conservative', 'moderate', 'aggressive']), 
              default='moderate', help='Risk tolerance')
@click.option('--agents', help='Comma-separated list of agents to use')
@click.option('--priority', type=click.Choice(['low', 'normal', 'high']), 
              default='normal', help='Research priority')
@click.option('--output', '-o', type=click.Path(), help='Save project details to file')
@click.option('--wait', '-w', is_flag=True, help='Wait for completion')
@click.option('--timeout', type=int, default=1800, help='Timeout in seconds when waiting')
def start_research(query, companies, thesis, horizon, risk, agents, priority, output, wait, timeout):
    """
    Start a new research project.
    
    Examples:
        researchlab research start "Is Apple undervalued?" --companies AAPL --thesis "AI growth will drive revenue"
        researchlab research start "Tech sector analysis" --companies AAPL,GOOGL,MSFT --wait
    """
    
    click.echo(f"🚀 Starting research project...")
    click.echo(f"Query: {query}")
    
    # Parse companies
    company_symbols = [c.strip().upper() for c in companies.split(',')]
    company_info = [
        CompanyInfo(symbol=symbol, name=symbol) 
        for symbol in company_symbols
    ]
    
    click.echo(f"Companies: {', '.join(company_symbols)}")
    
    # Create research request
    request = ResearchRequest(
        query=query,
        investment_thesis=thesis or f"Analysis of {', '.join(company_symbols)} for investment potential",
        companies=company_info,
        time_horizon=horizon,
        risk_tolerance=risk,
        priority=priority
    )
    
    # Parse agents if provided
    if agents:
        from src.agents.base import AgentRole
        agent_list = []
        for agent_name in agents.split(','):
            try:
                agent_role = AgentRole(agent_name.strip().lower())
                agent_list.append(agent_role)
            except ValueError:
                click.echo(f"⚠️  Unknown agent: {agent_name}")
        request.agents = agent_list
    
    # Start research
    result = asyncio.run(_start_research_project(request))
    
    if result:
        click.echo(f"✅ Research project started successfully!")
        click.echo(f"Project ID: {result['project_id']}")
        click.echo(f"Workflow ID: {result['workflow_id']}")
        click.echo(f"Status: {result['status']}")
        
        if result.get('estimated_completion'):
            completion_time = datetime.fromisoformat(result['estimated_completion'])
            click.echo(f"Estimated completion: {completion_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Save to file if requested
        if output:
            Path(output).write_text(json.dumps(result, indent=2))
            click.echo(f"Project details saved to {output}")
        
        # Wait for completion if requested
        if wait:
            click.echo(f"⏳ Waiting for completion (timeout: {timeout}s)...")
            final_result = asyncio.run(_wait_for_completion(result['project_id'], timeout))
            
            if final_result:
                click.echo(f"🎉 Research completed!")
                click.echo(f"Final status: {final_result['status']}")
                click.echo(f"Confidence: {final_result.get('overall_confidence', 'N/A')}")
                
                if final_result.get('report_url'):
                    click.echo(f"📊 Report: {final_result['report_url']}")
            else:
                click.echo(f"⚠️  Research did not complete within {timeout} seconds")
                click.echo(f"Use 'researchlab research status {result['project_id']}' to check progress")
    
    else:
        click.echo("❌ Failed to start research project")
        return 1


async def _start_research_project(request: ResearchRequest) -> Dict[str, Any]:
    """Start research project using workflow orchestrator."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        workflow_request = {
            'query': request.query,
            'investment_thesis': request.investment_thesis,
            'companies': [company.dict() for company in request.companies],
            'time_horizon': request.time_horizon,
            'risk_tolerance': request.risk_tolerance
        }
        
        workflow_id = await orchestrator.start_research_workflow(workflow_request)
        
        return {
            'project_id': workflow_id,  # Using workflow_id as project_id for simplicity
            'workflow_id': workflow_id,
            'status': 'pending',
            'agents_count': 5
        }
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


async def _wait_for_completion(project_id: str, timeout: int) -> Dict[str, Any]:
    """Wait for research project completion."""
    
    orchestrator = ResearchWorkflowOrchestrator()
    start_time = datetime.now()
    
    while (datetime.now() - start_time).total_seconds() < timeout:
        try:
            status = await orchestrator.get_workflow_status(project_id)
            
            if status['status'] in ['completed', 'failed', 'cancelled']:
                return status
            
            # Show progress
            progress = status.get('progress_percentage', 0)
            stage = status.get('current_stage', 'unknown')
            click.echo(f"  Progress: {progress:.1f}% - {stage}")
            
            await asyncio.sleep(10)  # Check every 10 seconds
            
        except Exception as e:
            click.echo(f"Error checking status: {str(e)}")
            break
    
    return None


@research_cli.command('status')
@click.argument('project_id')
@click.option('--watch', '-w', is_flag=True, help='Watch status updates')
@click.option('--interval', type=int, default=10, help='Update interval in seconds')
def get_research_status(project_id, watch, interval):
    """
    Get research project status.
    
    Examples:
        researchlab research status proj_12345
        researchlab research status proj_12345 --watch
    """
    
    if watch:
        click.echo(f"📊 Watching status for project {project_id} (Ctrl+C to stop)")
        
        try:
            while True:
                status = asyncio.run(_get_project_status(project_id))
                if status:
                    _display_status(status)
                    
                    if status['status'] in ['completed', 'failed', 'cancelled']:
                        break
                        
                    click.echo(f"Next update in {interval} seconds...\n")
                    asyncio.run(asyncio.sleep(interval))
                else:
                    break
        except KeyboardInterrupt:
            click.echo("\n⏹️  Stopped watching")
    
    else:
        status = asyncio.run(_get_project_status(project_id))
        if status:
            _display_status(status)
        else:
            click.echo(f"❌ Project {project_id} not found")
            return 1


async def _get_project_status(project_id: str) -> Dict[str, Any]:
    """Get project status."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        return await orchestrator.get_workflow_status(project_id)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _display_status(status: Dict[str, Any]):
    """Display formatted status information."""
    
    click.echo(f"\n📊 Research Status")
    click.echo(f"Project ID: {status.get('workflow_id', 'N/A')}")
    click.echo(f"Status: {_format_status(status.get('status', 'unknown'))}")
    click.echo(f"Progress: {status.get('progress_percentage', 0):.1f}%")
    click.echo(f"Current Stage: {status.get('current_stage', 'unknown').replace('_', ' ').title()}")
    click.echo(f"Current Operation: {status.get('current_operation', 'N/A')}")
    
    if status.get('start_time'):
        start_time = datetime.fromisoformat(status['start_time'])
        click.echo(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if status.get('completion_time'):
        completion_time = datetime.fromisoformat(status['completion_time'])
        click.echo(f"Completed: {completion_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    agents_completed = status.get('agents_completed', [])
    if agents_completed:
        click.echo(f"Completed Agents: {', '.join(agents_completed)}")
    
    confidence = status.get('overall_confidence', 0)
    if confidence > 0:
        click.echo(f"Overall Confidence: {confidence:.2f} ({_format_confidence(confidence)})")
    
    errors = status.get('errors', [])
    if errors:
        click.echo(f"❌ Errors: {len(errors)}")
        for error in errors[:3]:  # Show first 3 errors
            click.echo(f"  • {error}")


def _format_status(status: str) -> str:
    """Format status with emoji."""
    
    status_map = {
        'pending': '⏳ Pending',
        'running': '🔄 Running',
        'completed': '✅ Completed',
        'failed': '❌ Failed',
        'cancelled': '⏹️  Cancelled'
    }
    
    return status_map.get(status, f'❓ {status.title()}')


def _format_confidence(confidence: float) -> str:
    """Format confidence score."""
    
    if confidence >= 0.8:
        return "High"
    elif confidence >= 0.6:
        return "Medium"
    elif confidence >= 0.4:
        return "Low"
    else:
        return "Very Low"


@research_cli.command('results')
@click.argument('project_id')
@click.option('--format', type=click.Choice(['text', 'json', 'summary']), 
              default='summary', help='Output format')
@click.option('--output', '-o', type=click.Path(), help='Save results to file')
@click.option('--open-report', is_flag=True, help='Open Google Sheets report in browser')
def get_research_results(project_id, format, output, open_report):
    """
    Get research project results.
    
    Examples:
        researchlab research results proj_12345
        researchlab research results proj_12345 --format json --output results.json
    """
    
    click.echo(f"📋 Getting results for project {project_id}...")
    
    results = asyncio.run(_get_project_results(project_id))
    
    if not results:
        click.echo(f"❌ Results not available for project {project_id}")
        click.echo("Project may not be completed yet. Check status first.")
        return 1
    
    # Display results based on format
    if format == 'summary':
        _display_results_summary(results)
    elif format == 'json':
        output_str = json.dumps(results, indent=2, default=str)
        if output:
            Path(output).write_text(output_str)
            click.echo(f"Results saved to {output}")
        else:
            click.echo(output_str)
    else:  # text
        _display_results_detailed(results)
    
    # Open report if requested
    if open_report and results.get('report_url'):
        import webbrowser
        webbrowser.open(results['report_url'])
        click.echo(f"📊 Opened report in browser")
    elif open_report:
        click.echo("⚠️  No report URL available")


async def _get_project_results(project_id: str) -> Dict[str, Any]:
    """Get project results."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        return await orchestrator.get_workflow_results(project_id)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _display_results_summary(results: Dict[str, Any]):
    """Display results summary."""
    
    click.echo(f"\n🎯 Research Summary")
    click.echo("=" * 50)
    
    # Basic info
    query = results.get('query', 'N/A')
    click.echo(f"Query: {query}")
    
    companies = results.get('companies', [])
    if companies:
        company_names = [c.get('name', c.get('symbol', 'Unknown')) for c in companies]
        click.echo(f"Companies: {', '.join(company_names)}")
    
    # Overall assessment
    confidence = results.get('workflow_metadata', {}).get('total_confidence', 0)
    click.echo(f"Overall Confidence: {confidence:.2f} ({_format_confidence(confidence)})")
    
    # Agent results summary
    click.echo(f"\n📊 Analysis Results:")
    
    analyses = [
        ('fundamental_analysis', 'Fundamental Analysis'),
        ('quantitative_analysis', 'Quantitative Analysis'),
        ('sentiment_analysis', 'Sentiment Analysis'),
        ('supply_chain_analysis', 'Supply Chain Analysis'),
        ('risk_analysis', 'Risk Analysis')
    ]
    
    for analysis_key, analysis_name in analyses:
        analysis_data = results.get(analysis_key, {})
        if analysis_data:
            click.echo(f"  ✅ {analysis_name}: Complete")
            # Show key metrics if available
            if 'confidence' in analysis_data:
                click.echo(f"     Confidence: {analysis_data['confidence']:.2f}")
        else:
            click.echo(f"  ⚪ {analysis_name}: Not available")
    
    # Report link
    report_url = results.get('report_url')
    if report_url:
        click.echo(f"\n📊 Detailed Report: {report_url}")
    
    click.echo(f"\n🕒 Generated: {results.get('workflow_metadata', {}).get('completion_time', 'Unknown')}")


def _display_results_detailed(results: Dict[str, Any]):
    """Display detailed results."""
    
    _display_results_summary(results)
    
    click.echo(f"\n📋 Detailed Analysis Results")
    click.echo("=" * 50)
    
    # Show each analysis in detail
    analyses = [
        ('fundamental_analysis', 'Fundamental Analysis'),
        ('quantitative_analysis', 'Quantitative Analysis'),
        ('sentiment_analysis', 'Sentiment Analysis'),
        ('supply_chain_analysis', 'Supply Chain Analysis'),
        ('risk_analysis', 'Risk Analysis')
    ]
    
    for analysis_key, analysis_name in analyses:
        analysis_data = results.get(analysis_key, {})
        if analysis_data:
            click.echo(f"\n{analysis_name}:")
            click.echo("-" * len(analysis_name))
            
            # Show key findings
            if 'company_analyses' in analysis_data:
                click.echo(f"Companies analyzed: {len(analysis_data['company_analyses'])}")
            
            if 'methodology' in analysis_data:
                methods = analysis_data['methodology']
                if isinstance(methods, dict):
                    click.echo(f"Methods used: {len(methods)}")
            
            if 'confidence' in analysis_data:
                click.echo(f"Confidence: {analysis_data['confidence']:.2f}")


@research_cli.command('list')
@click.option('--status', type=click.Choice(['pending', 'running', 'completed', 'failed']), 
              help='Filter by status')
@click.option('--limit', type=int, default=20, help='Maximum number of projects to show')
@click.option('--format', type=click.Choice(['table', 'json']), default='table')
def list_research_projects(status, limit, format):
    """
    List research projects.
    
    Examples:
        researchlab research list
        researchlab research list --status completed --limit 10
    """
    
    click.echo("📂 Research Projects")
    
    # Mock implementation - would connect to API
    projects = [
        {
            'project_id': 'proj_123',
            'query': 'Tech sector analysis',
            'status': 'completed',
            'created_at': '2024-02-01T10:00:00',
            'companies': ['AAPL', 'GOOGL'],
            'confidence': 0.85
        },
        {
            'project_id': 'proj_124',
            'query': 'Is Netflix undervalued?',
            'status': 'running',
            'created_at': '2024-02-03T14:30:00',
            'companies': ['NFLX'],
            'confidence': None
        }
    ]
    
    # Apply filters
    if status:
        projects = [p for p in projects if p['status'] == status]
    
    projects = projects[:limit]
    
    if format == 'json':
        click.echo(json.dumps(projects, indent=2))
    else:
        if not projects:
            click.echo("No projects found")
            return
        
        # Table format
        click.echo(f"\n{'ID':<12} {'Status':<12} {'Query':<30} {'Companies':<15} {'Created':<12}")
        click.echo("-" * 85)
        
        for project in projects:
            project_id = project['project_id'][:10] + '..'
            status_str = _format_status(project['status'])[:10]
            query = project['query'][:28] + '..' if len(project['query']) > 30 else project['query']
            companies = ','.join(project['companies'])[:13]
            created = project['created_at'][:10]
            
            click.echo(f"{project_id:<12} {status_str:<12} {query:<30} {companies:<15} {created:<12}")


@research_cli.command('cancel')
@click.argument('project_id')
@click.confirmation_option(prompt='Are you sure you want to cancel this project?')
def cancel_research(project_id):
    """
    Cancel a running research project.
    
    Examples:
        researchlab research cancel proj_12345
    """
    
    result = asyncio.run(_cancel_project(project_id))
    
    if result:
        click.echo(f"✅ Project {project_id} cancelled successfully")
    else:
        click.echo(f"❌ Failed to cancel project {project_id}")
        return 1


async def _cancel_project(project_id: str) -> bool:
    """Cancel research project."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        return await orchestrator.cancel_workflow(project_id)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


@research_cli.command('restart')
@click.argument('project_id')
@click.confirmation_option(prompt='Are you sure you want to restart this project?')
def restart_research(project_id):
    """
    Restart a failed research project.
    
    Examples:
        researchlab research restart proj_12345
    """
    
    click.echo(f"🔄 Restarting project {project_id}...")
    
    # Mock implementation
    click.echo(f"✅ Project {project_id} restarted successfully")
    click.echo(f"New workflow ID: wf_{project_id.replace('proj_', '')}_restart")


@research_cli.command('batch')
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output file for batch results')
@click.option('--concurrent', type=int, default=3, help='Number of concurrent projects')
def batch_research(input_file, output, concurrent):
    """
    Run batch research from JSON file.
    
    Input file should contain array of research requests:
    [
        {
            "query": "Is Apple undervalued?",
            "companies": ["AAPL"],
            "thesis": "AI growth will drive revenue"
        }
    ]
    """
    
    try:
        with open(input_file, 'r') as f:
            requests = json.load(f)
        
        click.echo(f"📊 Starting batch research: {len(requests)} projects")
        click.echo(f"Concurrent limit: {concurrent}")
        
        results = asyncio.run(_run_batch_research(requests, concurrent))
        
        if output:
            with open(output, 'w') as f:
                json.dump(results, f, indent=2)
            click.echo(f"Results saved to {output}")
        
        # Summary
        successful = len([r for r in results if r['success']])
        click.echo(f"✅ Batch complete: {successful}/{len(results)} successful")
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return 1


async def _run_batch_research(requests: List[Dict], concurrent_limit: int) -> List[Dict]:
    """Run batch research projects."""
    
    results = []
    semaphore = asyncio.Semaphore(concurrent_limit)
    
    async def process_request(request_data):
        async with semaphore:
            try:
                # Convert to ResearchRequest
                companies = [CompanyInfo(symbol=c) for c in request_data.get('companies', [])]
                request = ResearchRequest(
                    query=request_data['query'],
                    companies=companies,
                    investment_thesis=request_data.get('thesis', ''),
                    time_horizon=request_data.get('horizon', 12),
                    risk_tolerance=request_data.get('risk', 'moderate')
                )
                
                result = await _start_research_project(request)
                return {'success': True, 'request': request_data, 'result': result}
                
            except Exception as e:
                return {'success': False, 'request': request_data, 'error': str(e)}
    
    # Process all requests
    tasks = [process_request(req) for req in requests]
    results = await asyncio.gather(*tasks)
    
    return results