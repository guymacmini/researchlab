"""Workflow management CLI commands."""

import click
import asyncio
import json
from datetime import datetime
from pathlib import Path

from src.core.workflow import ResearchWorkflowOrchestrator


@click.group()
def workflow_cli():
    """Workflow management commands."""
    pass


@workflow_cli.command('list')
@click.option('--active', is_flag=True, help='Show only active workflows')
@click.option('--limit', type=int, default=20, help='Maximum workflows to show')
@click.option('--format', type=click.Choice(['table', 'json']), default='table')
def list_workflows(active, limit, format):
    """
    List workflows.
    
    Examples:
        researchlab workflow list
        researchlab workflow list --active --limit 10
    """
    
    workflows = asyncio.run(_get_workflows(active, limit))
    
    if not workflows:
        click.echo("No workflows found")
        return
    
    if format == 'json':
        click.echo(json.dumps(workflows, indent=2, default=str))
    else:
        click.echo("📊 Workflows")
        click.echo(f"\n{'ID':<15} {'Status':<12} {'Stage':<20} {'Progress':<10} {'Started':<12}")
        click.echo("-" * 80)
        
        for workflow in workflows:
            wf_id = workflow['workflow_id'][:13] + '..'
            status = _format_workflow_status(workflow['status'])[:10]
            stage = workflow['current_stage'].replace('_', ' ').title()[:18]
            progress = f"{workflow['progress_percentage']:.1f}%"
            started = workflow['start_time'][:10] if isinstance(workflow['start_time'], str) else 'N/A'
            
            click.echo(f"{wf_id:<15} {status:<12} {stage:<20} {progress:<10} {started:<12}")


async def _get_workflows(active_only: bool, limit: int) -> list:
    """Get workflows list."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Get active workflows
        workflows = []
        for workflow_id, session in orchestrator.active_workflows.items():
            status = await session.get_status()
            
            if active_only and status['status'] not in ['running', 'pending']:
                continue
            
            workflows.append(status)
        
        # Sort by start time (newest first)
        workflows.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        
        return workflows[:limit]
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return []


def _format_workflow_status(status: str) -> str:
    """Format workflow status with emoji."""
    
    status_map = {
        'pending': '⏳ Pending',
        'running': '🔄 Running',
        'completed': '✅ Complete',
        'failed': '❌ Failed',
        'cancelled': '⏹️  Cancelled'
    }
    
    return status_map.get(status, f'❓ {status.title()}')


@workflow_cli.command('status')
@click.argument('workflow_id')
@click.option('--watch', '-w', is_flag=True, help='Watch status updates')
@click.option('--interval', type=int, default=5, help='Update interval in seconds')
def get_workflow_status(workflow_id, watch, interval):
    """
    Get workflow status.
    
    Examples:
        researchlab workflow status wf_12345
        researchlab workflow status wf_12345 --watch --interval 10
    """
    
    if watch:
        click.echo(f"👀 Watching workflow {workflow_id} (Ctrl+C to stop)")
        
        try:
            while True:
                status = asyncio.run(_get_workflow_status(workflow_id))
                if status:
                    _display_workflow_status(status, clear_screen=True)
                    
                    if status['status'] in ['completed', 'failed', 'cancelled']:
                        break
                        
                    click.echo(f"\nNext update in {interval} seconds...")
                    asyncio.run(asyncio.sleep(interval))
                else:
                    break
        except KeyboardInterrupt:
            click.echo("\n⏹️  Stopped watching")
    
    else:
        status = asyncio.run(_get_workflow_status(workflow_id))
        if status:
            _display_workflow_status(status)
        else:
            click.echo(f"❌ Workflow {workflow_id} not found")
            return 1


async def _get_workflow_status(workflow_id: str) -> dict:
    """Get workflow status."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        return await orchestrator.get_workflow_status(workflow_id)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _display_workflow_status(status: dict, clear_screen: bool = False):
    """Display formatted workflow status."""
    
    if clear_screen:
        click.clear()
    
    click.echo(f"\n🔄 Workflow Status")
    click.echo("=" * 40)
    click.echo(f"Workflow ID: {status.get('workflow_id', 'N/A')}")
    click.echo(f"Status: {_format_workflow_status(status.get('status', 'unknown'))}")
    click.echo(f"Progress: {status.get('progress_percentage', 0):.1f}%")
    
    # Progress bar
    progress = status.get('progress_percentage', 0)
    bar_width = 30
    filled = int(bar_width * progress / 100)
    bar = '█' * filled + '░' * (bar_width - filled)
    click.echo(f"Progress: [{bar}] {progress:.1f}%")
    
    click.echo(f"Current Stage: {status.get('current_stage', 'unknown').replace('_', ' ').title()}")
    click.echo(f"Current Operation: {status.get('current_operation', 'N/A')}")
    
    if status.get('start_time'):
        start_time = datetime.fromisoformat(status['start_time'])
        click.echo(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if status.get('completion_time'):
        completion_time = datetime.fromisoformat(status['completion_time'])
        click.echo(f"Completed: {completion_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Calculate duration
        if status.get('start_time'):
            start = datetime.fromisoformat(status['start_time'])
            duration = completion_time - start
            click.echo(f"Duration: {_format_duration(duration.total_seconds())}")
    
    # Agents progress
    agents_completed = status.get('agents_completed', [])
    if agents_completed:
        click.echo(f"\n🤖 Completed Agents ({len(agents_completed)}):")
        for agent in agents_completed:
            click.echo(f"  ✅ {agent.replace('_', ' ').title()}")
    
    # Confidence
    confidence = status.get('overall_confidence', 0)
    if confidence > 0:
        confidence_label = _format_confidence_label(confidence)
        click.echo(f"\n📊 Overall Confidence: {confidence:.2f} ({confidence_label})")
    
    # Errors
    errors = status.get('errors', [])
    if errors:
        click.echo(f"\n❌ Errors ({len(errors)}):")
        for i, error in enumerate(errors[:3]):
            click.echo(f"  {i+1}. {error}")
        if len(errors) > 3:
            click.echo(f"  ... and {len(errors) - 3} more")


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def _format_confidence_label(confidence: float) -> str:
    """Format confidence score label."""
    
    if confidence >= 0.8:
        return "🟢 High"
    elif confidence >= 0.6:
        return "🟡 Medium"
    elif confidence >= 0.4:
        return "🟠 Low"
    else:
        return "🔴 Very Low"


@workflow_cli.command('cancel')
@click.argument('workflow_id')
@click.confirmation_option(prompt='Are you sure you want to cancel this workflow?')
def cancel_workflow(workflow_id):
    """
    Cancel a running workflow.
    
    Examples:
        researchlab workflow cancel wf_12345
    """
    
    result = asyncio.run(_cancel_workflow(workflow_id))
    
    if result:
        click.echo(f"✅ Workflow {workflow_id} cancelled successfully")
    else:
        click.echo(f"❌ Failed to cancel workflow {workflow_id}")
        return 1


async def _cancel_workflow(workflow_id: str) -> bool:
    """Cancel workflow."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        return await orchestrator.cancel_workflow(workflow_id)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return False


@workflow_cli.command('results')
@click.argument('workflow_id')
@click.option('--format', type=click.Choice(['summary', 'json', 'detailed']), default='summary')
@click.option('--output', '-o', type=click.Path(), help='Save results to file')
def get_workflow_results(workflow_id, format, output):
    """
    Get workflow results.
    
    Examples:
        researchlab workflow results wf_12345
        researchlab workflow results wf_12345 --format json --output results.json
    """
    
    results = asyncio.run(_get_workflow_results(workflow_id))
    
    if not results:
        click.echo(f"❌ Results not available for workflow {workflow_id}")
        return 1
    
    if format == 'json':
        output_str = json.dumps(results, indent=2, default=str)
        if output:
            Path(output).write_text(output_str)
            click.echo(f"Results saved to {output}")
        else:
            click.echo(output_str)
    
    elif format == 'summary':
        _display_results_summary(results)
        
    else:  # detailed
        _display_results_detailed(results)


async def _get_workflow_results(workflow_id: str) -> dict:
    """Get workflow results."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        return await orchestrator.get_workflow_results(workflow_id)
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


def _display_results_summary(results: dict):
    """Display workflow results summary."""
    
    click.echo(f"\n📊 Workflow Results Summary")
    click.echo("=" * 40)
    
    workflow_id = results.get('workflow_id', 'N/A')
    click.echo(f"Workflow ID: {workflow_id}")
    
    # Metadata
    metadata = results.get('workflow_metadata', {})
    if metadata:
        agents_count = len(metadata.get('agents_executed', []))
        click.echo(f"Agents Executed: {agents_count}")
        
        total_confidence = metadata.get('total_confidence', 0)
        if total_confidence:
            click.echo(f"Overall Confidence: {total_confidence:.2f}")
        
        if 'execution_time' in metadata:
            click.echo(f"Execution Time: {_format_duration(metadata['execution_time'])}")
    
    # Companies analyzed
    companies = results.get('companies', [])
    if companies:
        company_names = [c.get('name', c.get('symbol', 'Unknown')) for c in companies]
        click.echo(f"Companies: {', '.join(company_names)}")
    
    # Analysis completeness
    click.echo(f"\n📋 Analysis Completeness:")
    
    analyses = [
        ('fundamental_analysis', 'Fundamental'),
        ('quantitative_analysis', 'Quantitative'),
        ('sentiment_analysis', 'Sentiment'),
        ('supply_chain_analysis', 'Supply Chain'),
        ('risk_analysis', 'Risk')
    ]
    
    for key, name in analyses:
        if results.get(key):
            click.echo(f"  ✅ {name}")
        else:
            click.echo(f"  ❌ {name}")


def _display_results_detailed(results: dict):
    """Display detailed workflow results."""
    
    _display_results_summary(results)
    
    click.echo(f"\n📋 Detailed Analysis Results")
    click.echo("=" * 40)
    
    # Show each analysis section
    sections = [
        ('research_plan', 'Research Plan'),
        ('fundamental_analysis', 'Fundamental Analysis'),
        ('quantitative_analysis', 'Quantitative Analysis'),
        ('sentiment_analysis', 'Sentiment Analysis'),
        ('supply_chain_analysis', 'Supply Chain Analysis'),
        ('risk_analysis', 'Risk Analysis')
    ]
    
    for key, name in sections:
        data = results.get(key)
        if data:
            click.echo(f"\n{name}:")
            click.echo("-" * len(name))
            
            if isinstance(data, dict):
                # Show key metrics
                for field, value in data.items():
                    if field in ['confidence', 'analysis_timestamp', 'methodology']:
                        if field == 'confidence':
                            click.echo(f"  Confidence: {value:.2f}")
                        elif field == 'analysis_timestamp':
                            click.echo(f"  Completed: {value}")
                        elif field == 'methodology' and isinstance(value, dict):
                            click.echo(f"  Methods: {len(value)}")
            
            # Truncate large data
            if len(str(data)) > 200:
                click.echo(f"  [Large dataset - {len(str(data))} characters]")


@workflow_cli.command('logs')
@click.argument('workflow_id')
@click.option('--follow', '-f', is_flag=True, help='Follow log output')
@click.option('--lines', type=int, default=50, help='Number of lines to show')
def get_workflow_logs(workflow_id, follow, lines):
    """
    Get workflow execution logs.
    
    Examples:
        researchlab workflow logs wf_12345
        researchlab workflow logs wf_12345 --follow --lines 100
    """
    
    click.echo(f"📝 Workflow Logs: {workflow_id}")
    click.echo("=" * 50)
    
    if follow:
        click.echo("Following logs (Ctrl+C to stop)...")
        try:
            # Mock log following
            import time
            for i in range(10):
                click.echo(f"[{datetime.now().strftime('%H:%M:%S')}] Workflow executing...")
                time.sleep(2)
        except KeyboardInterrupt:
            click.echo("\n⏹️  Stopped following logs")
    else:
        # Mock static logs
        logs = [
            f"[{datetime.now().strftime('%H:%M:%S')}] Workflow started",
            f"[{datetime.now().strftime('%H:%M:%S')}] Research Director initialized",
            f"[{datetime.now().strftime('%H:%M:%S')}] Fundamental analysis in progress",
            f"[{datetime.now().strftime('%H:%M:%S')}] Data fetching completed",
        ]
        
        for log in logs[-lines:]:
            click.echo(log)


@workflow_cli.command('system')
def get_system_status():
    """
    Get workflow system status.
    
    Examples:
        researchlab workflow system
    """
    
    status = asyncio.run(_get_system_status())
    
    click.echo(f"🏥 Workflow System Status")
    click.echo("=" * 30)
    
    if status:
        click.echo(f"Total Workflows: {status.get('total_workflows', 0)}")
        click.echo(f"Active Workflows: {status.get('active_workflows', 0)}")
        click.echo(f"Completed: {status.get('completed_workflows', 0)}")
        click.echo(f"Failed: {status.get('failed_workflows', 0)}")
        
        system_load = status.get('system_load', 0)
        load_indicator = "🟢" if system_load < 0.5 else "🟡" if system_load < 0.8 else "🔴"
        click.echo(f"System Load: {load_indicator} {system_load:.1%}")
        
        success_rate = status.get('success_rate', 0)
        click.echo(f"Success Rate: {success_rate:.1%}")
        
        avg_time = status.get('average_execution_time')
        if avg_time:
            click.echo(f"Avg Execution Time: {_format_duration(avg_time)}")
    
    else:
        click.echo("❌ Unable to get system status")


async def _get_system_status() -> dict:
    """Get system status."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Calculate system statistics
        total_workflows = len(orchestrator.active_workflows)
        active_workflows = sum(1 for session in orchestrator.active_workflows.values()
                             if session.status.value in ['running', 'pending'])
        completed_workflows = sum(1 for session in orchestrator.active_workflows.values()
                                if session.status.value == 'completed')
        failed_workflows = sum(1 for session in orchestrator.active_workflows.values()
                             if session.status.value == 'failed')
        
        # System load (simple calculation)
        max_concurrent = 10  # Configuration value
        system_load = active_workflows / max_concurrent
        
        # Success rate
        completed_or_failed = completed_workflows + failed_workflows
        success_rate = completed_workflows / completed_or_failed if completed_or_failed > 0 else 0
        
        return {
            'total_workflows': total_workflows,
            'active_workflows': active_workflows,
            'completed_workflows': completed_workflows,
            'failed_workflows': failed_workflows,
            'system_load': system_load,
            'success_rate': success_rate
        }
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None


@workflow_cli.command('cleanup')
@click.option('--max-age', type=int, default=24, help='Maximum age in hours')
@click.confirmation_option(prompt='This will remove old workflow data. Continue?')
def cleanup_workflows(max_age):
    """
    Clean up old workflow data.
    
    Examples:
        researchlab workflow cleanup --max-age 48
    """
    
    cleaned_count = asyncio.run(_cleanup_workflows(max_age))
    
    if cleaned_count >= 0:
        click.echo(f"🧹 Cleaned up {cleaned_count} old workflows")
    else:
        click.echo("❌ Failed to cleanup workflows")


async def _cleanup_workflows(max_age_hours: int) -> int:
    """Cleanup old workflows."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        initial_count = len(orchestrator.active_workflows)
        orchestrator.cleanup_completed_workflows(max_age_hours=max_age_hours)
        final_count = len(orchestrator.active_workflows)
        
        return initial_count - final_count
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return -1


@workflow_cli.command('stages')
def list_workflow_stages():
    """
    List available workflow stages and agents.
    
    Examples:
        researchlab workflow stages
    """
    
    stages_info = asyncio.run(_get_workflow_stages())
    
    if stages_info:
        click.echo("🔄 Workflow Stages")
        click.echo("=" * 20)
        
        stages = stages_info.get('workflow_stages', [])
        for i, stage in enumerate(stages, 1):
            click.echo(f"{i}. {stage.replace('_', ' ').title()}")
        
        click.echo(f"\n🤖 Available Agents")
        click.echo("=" * 20)
        
        agents = stages_info.get('agent_roles', [])
        for agent in agents:
            click.echo(f"• {agent.replace('_', ' ').title()}")
        
        click.echo(f"\n🔗 Agent Dependencies")
        click.echo("=" * 20)
        
        dependencies = stages_info.get('agent_dependencies', {})
        for agent, deps in dependencies.items():
            deps_str = ', '.join(deps) if deps else 'None'
            click.echo(f"{agent.replace('_', ' ').title()}: {deps_str}")


async def _get_workflow_stages() -> dict:
    """Get workflow stages information."""
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Get stages
        stages = [stage.value for stage in orchestrator.workflow_stages]
        
        # Get agent roles
        from src.agents.base import AgentRole
        agents = [role.value for role in AgentRole]
        
        # Get dependencies
        dependencies = {}
        for agent, deps in orchestrator.agent_dependencies.items():
            dependencies[agent.value] = [dep.value for dep in deps]
        
        return {
            'workflow_stages': stages,
            'agent_roles': agents,
            'agent_dependencies': dependencies
        }
        
    except Exception as e:
        click.echo(f"Error: {str(e)}")
        return None