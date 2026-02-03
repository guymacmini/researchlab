"""End-to-end research workflow orchestration."""

import asyncio
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from enum import Enum
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import DatabaseManager
from src.data.models import ResearchProject, ResearchStatus
from src.agents.base import AgentRole, AgentResult
from src.agents.orchestrator import AgentOrchestrator
from src.output.google_sheets import GoogleSheetsOutputManager

logger = structlog.get_logger()


class WorkflowStage(Enum):
    """Research workflow stages."""
    INITIALIZATION = "initialization"
    RESEARCH_PLANNING = "research_planning"
    DATA_COLLECTION = "data_collection"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    SUPPLY_CHAIN_ANALYSIS = "supply_chain_analysis"
    RISK_ANALYSIS = "risk_analysis"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchWorkflowOrchestrator:
    """Orchestrates the complete end-to-end research workflow."""
    
    def __init__(self):
        self.agent_orchestrator = AgentOrchestrator()
        self.sheets_output = GoogleSheetsOutputManager()
        self.db_manager = DatabaseManager()
        self.logger = logger.bind(component="research_workflow")
        
        # Define the standard workflow sequence
        self.workflow_stages = [
            WorkflowStage.INITIALIZATION,
            WorkflowStage.RESEARCH_PLANNING,
            WorkflowStage.DATA_COLLECTION,
            WorkflowStage.FUNDAMENTAL_ANALYSIS,
            WorkflowStage.SENTIMENT_ANALYSIS,
            WorkflowStage.SUPPLY_CHAIN_ANALYSIS,
            WorkflowStage.RISK_ANALYSIS,
            WorkflowStage.REPORT_GENERATION,
            WorkflowStage.COMPLETED
        ]
        
        # Agent execution order and dependencies
        self.agent_dependencies = {
            AgentRole.RESEARCH_DIRECTOR: [],  # No dependencies
            AgentRole.FUNDAMENTAL_ANALYST: [AgentRole.RESEARCH_DIRECTOR],
            AgentRole.SENTIMENT_ANALYST: [AgentRole.RESEARCH_DIRECTOR],
            AgentRole.SUPPLY_CHAIN_ANALYST: [AgentRole.RESEARCH_DIRECTOR],
            AgentRole.RISK_ANALYST: [
                AgentRole.FUNDAMENTAL_ANALYST,
                AgentRole.SENTIMENT_ANALYST,
                AgentRole.SUPPLY_CHAIN_ANALYST
            ]
        }
        
        # Active workflow sessions
        self.active_workflows: Dict[str, 'WorkflowSession'] = {}
        
    async def start_research_workflow(self, research_request: Dict[str, Any]) -> str:
        """Start a new end-to-end research workflow."""
        
        workflow_id = str(uuid.uuid4())
        
        try:
            # Create workflow session
            workflow = WorkflowSession(
                workflow_id=workflow_id,
                research_request=research_request,
                orchestrator=self
            )
            
            self.active_workflows[workflow_id] = workflow
            
            # Start workflow execution
            asyncio.create_task(workflow.execute())
            
            self.logger.info("research_workflow_started", 
                           workflow_id=workflow_id,
                           query=research_request.get('query', 'Unknown'))
            
            return workflow_id
            
        except Exception as e:
            self.logger.error("workflow_start_failed", 
                            workflow_id=workflow_id, error=str(e))
            raise
    
    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get current status of a research workflow."""
        
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {
                'workflow_id': workflow_id,
                'status': WorkflowStatus.CANCELLED.value,
                'error': 'Workflow not found'
            }
        
        return await workflow.get_status()
    
    async def get_workflow_results(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get results from a completed workflow."""
        
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return None
        
        return await workflow.get_results()
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow."""
        
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return False
        
        return await workflow.cancel()
    
    def cleanup_completed_workflows(self, max_age_hours: int = 24):
        """Clean up old completed workflows."""
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        workflows_to_remove = []
        for workflow_id, workflow in self.active_workflows.items():
            if (workflow.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED] and
                workflow.completion_time and workflow.completion_time < cutoff_time):
                workflows_to_remove.append(workflow_id)
        
        for workflow_id in workflows_to_remove:
            del self.active_workflows[workflow_id]
            
        if workflows_to_remove:
            self.logger.info("workflows_cleaned_up", count=len(workflows_to_remove))


class WorkflowSession:
    """Individual research workflow session."""
    
    def __init__(self, workflow_id: str, research_request: Dict[str, Any], 
                 orchestrator: ResearchWorkflowOrchestrator):
        self.workflow_id = workflow_id
        self.research_request = research_request
        self.orchestrator = orchestrator
        
        # Session state
        self.status = WorkflowStatus.PENDING
        self.current_stage = WorkflowStage.INITIALIZATION
        self.start_time = datetime.now()
        self.completion_time: Optional[datetime] = None
        
        # Results storage
        self.stage_results: Dict[WorkflowStage, Dict[str, Any]] = {}
        self.agent_results: Dict[AgentRole, AgentResult] = {}
        self.errors: List[str] = []
        
        # Progress tracking
        self.progress_percentage = 0.0
        self.current_operation = "Initializing workflow"
        
        self.logger = logger.bind(workflow_id=workflow_id)
        
        # Cancellation support
        self._cancelled = False
        self._cancel_event = asyncio.Event()
        
    async def execute(self) -> None:
        """Execute the complete research workflow."""
        
        try:
            self.status = WorkflowStatus.RUNNING
            self.logger.info("workflow_execution_started")
            
            # Execute each stage in sequence
            for i, stage in enumerate(self.orchestrator.workflow_stages[:-1]):  # Exclude COMPLETED
                if self._cancelled:
                    self.status = WorkflowStatus.CANCELLED
                    return
                
                self.current_stage = stage
                self.progress_percentage = (i / len(self.orchestrator.workflow_stages)) * 100
                
                self.logger.info("workflow_stage_started", stage=stage.value)
                
                stage_result = await self._execute_stage(stage)
                self.stage_results[stage] = stage_result
                
                if not stage_result.get('success', False):
                    self.status = WorkflowStatus.FAILED
                    self.errors.append(f"Stage {stage.value} failed: {stage_result.get('error', 'Unknown error')}")
                    self.completion_time = datetime.now()
                    return
            
            # Mark as completed
            self.current_stage = WorkflowStage.COMPLETED
            self.progress_percentage = 100.0
            self.status = WorkflowStatus.COMPLETED
            self.completion_time = datetime.now()
            self.current_operation = "Workflow completed successfully"
            
            self.logger.info("workflow_execution_completed", 
                           duration_seconds=(self.completion_time - self.start_time).total_seconds())
            
        except Exception as e:
            self.status = WorkflowStatus.FAILED
            self.errors.append(f"Workflow execution failed: {str(e)}")
            self.completion_time = datetime.now()
            
            self.logger.error("workflow_execution_failed", error=str(e))
    
    async def _execute_stage(self, stage: WorkflowStage) -> Dict[str, Any]:
        """Execute a specific workflow stage."""
        
        try:
            if stage == WorkflowStage.INITIALIZATION:
                return await self._execute_initialization()
            elif stage == WorkflowStage.RESEARCH_PLANNING:
                return await self._execute_research_planning()
            elif stage == WorkflowStage.DATA_COLLECTION:
                return await self._execute_data_collection()
            elif stage == WorkflowStage.FUNDAMENTAL_ANALYSIS:
                return await self._execute_agent_analysis(AgentRole.FUNDAMENTAL_ANALYST)
            elif stage == WorkflowStage.SENTIMENT_ANALYSIS:
                return await self._execute_agent_analysis(AgentRole.SENTIMENT_ANALYST)
            elif stage == WorkflowStage.SUPPLY_CHAIN_ANALYSIS:
                return await self._execute_agent_analysis(AgentRole.SUPPLY_CHAIN_ANALYST)
            elif stage == WorkflowStage.RISK_ANALYSIS:
                return await self._execute_agent_analysis(AgentRole.RISK_ANALYST)
            elif stage == WorkflowStage.REPORT_GENERATION:
                return await self._execute_report_generation()
            else:
                return {'success': False, 'error': f'Unknown stage: {stage.value}'}
                
        except Exception as e:
            self.logger.error("stage_execution_failed", stage=stage.value, error=str(e))
            return {'success': False, 'error': str(e)}
    
    async def _execute_initialization(self) -> Dict[str, Any]:
        """Initialize the workflow and validate inputs."""
        
        self.current_operation = "Initializing workflow and validating inputs"
        
        # Validate required fields
        required_fields = ['query', 'companies']
        for field in required_fields:
            if field not in self.research_request:
                return {
                    'success': False,
                    'error': f'Missing required field: {field}'
                }
        
        companies = self.research_request.get('companies', [])
        if not companies:
            return {
                'success': False,
                'error': 'No companies provided for analysis'
            }
        
        # Initialize database project record if needed
        try:
            async with self.orchestrator.db_manager.get_session() as session:
                # Create or update research project
                project = ResearchProject(
                    id=self.research_request.get('project_id', self.workflow_id),
                    query=self.research_request['query'],
                    status=ResearchStatus.IN_PROGRESS,
                    created_at=self.start_time
                )
                session.add(project)
                await session.commit()
                
        except Exception as e:
            self.logger.warning("database_initialization_failed", error=str(e))
            # Continue without database - not critical for workflow
        
        return {
            'success': True,
            'companies_count': len(companies),
            'project_id': self.research_request.get('project_id', self.workflow_id)
        }
    
    async def _execute_research_planning(self) -> Dict[str, Any]:
        """Execute research planning using Research Director agent."""
        
        self.current_operation = "Planning research scope and approach"
        
        try:
            # Execute Research Director analysis
            result = await self._execute_single_agent(AgentRole.RESEARCH_DIRECTOR)
            
            if result and result.success:
                # Store research plan for other agents
                self.research_request['research_plan'] = result.data
                return {
                    'success': True,
                    'research_plan': result.data,
                    'confidence': result.confidence
                }
            else:
                return {
                    'success': False,
                    'error': 'Research Director analysis failed',
                    'details': result.errors if result else ['No result returned']
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Research planning failed: {str(e)}'
            }
    
    async def _execute_data_collection(self) -> Dict[str, Any]:
        """Execute data collection phase."""
        
        self.current_operation = "Collecting market data and company information"
        
        # This stage prepares data context for subsequent agents
        # In a real implementation, this might involve:
        # - Pre-fetching company profiles
        # - Gathering historical data
        # - Preparing data caches
        
        try:
            companies = self.research_request.get('companies', [])
            
            # Simulate data collection
            collected_data = {
                'companies_prepared': len(companies),
                'data_sources': ['finnhub', 'alpha_vantage'],
                'collection_timestamp': datetime.now().isoformat()
            }
            
            # Add collected data to request context
            self.research_request['collected_data'] = collected_data
            
            return {
                'success': True,
                'collected_data': collected_data
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Data collection failed: {str(e)}'
            }
    
    async def _execute_agent_analysis(self, agent_role: AgentRole) -> Dict[str, Any]:
        """Execute analysis for a specific agent."""
        
        self.current_operation = f"Running {agent_role.value.replace('_', ' ').title()} analysis"
        
        try:
            # Check dependencies
            dependencies = self.orchestrator.agent_dependencies.get(agent_role, [])
            for dep_agent in dependencies:
                if dep_agent not in self.agent_results:
                    return {
                        'success': False,
                        'error': f'Dependency {dep_agent.value} not completed'
                    }
            
            # Execute agent analysis
            result = await self._execute_single_agent(agent_role)
            
            if result and result.success:
                self.agent_results[agent_role] = result
                
                # Add agent results to context for subsequent agents
                self._update_context_with_results(agent_role, result)
                
                return {
                    'success': True,
                    'agent_result': {
                        'confidence': result.confidence,
                        'data_summary': self._summarize_agent_data(result.data),
                        'reasoning': result.reasoning
                    }
                }
            else:
                return {
                    'success': False,
                    'error': f'{agent_role.value} analysis failed',
                    'details': result.errors if result else ['No result returned']
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'{agent_role.value} execution failed: {str(e)}'
            }
    
    async def _execute_single_agent(self, agent_role: AgentRole) -> Optional[AgentResult]:
        """Execute a single agent with current context."""
        
        try:
            # Get agent from orchestrator
            agent = self.orchestrator.agent_orchestrator.agents.get(agent_role)
            if not agent:
                self.logger.error("agent_not_found", agent_role=agent_role.value)
                return None
            
            # Validate inputs
            if not await agent.validate_inputs(self.research_request):
                self.logger.error("agent_input_validation_failed", agent_role=agent_role.value)
                return None
            
            # Execute agent analysis
            result = await agent.analyze(self.research_request)
            
            return result
            
        except Exception as e:
            self.logger.error("agent_execution_error", 
                            agent_role=agent_role.value, error=str(e))
            return None
    
    async def _execute_report_generation(self) -> Dict[str, Any]:
        """Generate final research report."""
        
        self.current_operation = "Generating research report"
        
        try:
            # Compile all results
            research_results = {
                'workflow_id': self.workflow_id,
                'investment_thesis': self.research_request.get('investment_thesis', ''),
                'companies': self.research_request.get('companies', []),
                'research_plan': self.research_request.get('research_plan', {}),
                'fundamental_analysis': self.agent_results.get(AgentRole.FUNDAMENTAL_ANALYST, {}).data if AgentRole.FUNDAMENTAL_ANALYST in self.agent_results else {},
                'sentiment_analysis': self.agent_results.get(AgentRole.SENTIMENT_ANALYST, {}).data if AgentRole.SENTIMENT_ANALYST in self.agent_results else {},
                'supply_chain_analysis': self.agent_results.get(AgentRole.SUPPLY_CHAIN_ANALYST, {}).data if AgentRole.SUPPLY_CHAIN_ANALYST in self.agent_results else {},
                'risk_analysis': self.agent_results.get(AgentRole.RISK_ANALYST, {}).data if AgentRole.RISK_ANALYST in self.agent_results else {},
                'workflow_metadata': {
                    'start_time': self.start_time.isoformat(),
                    'completion_time': datetime.now().isoformat(),
                    'agents_executed': list(self.agent_results.keys()),
                    'total_confidence': self._calculate_overall_confidence()
                }
            }
            
            # Generate Google Sheets report
            project_name = f"Research_{self.workflow_id[:8]}"
            report_url = await self.orchestrator.sheets_output.create_research_report(
                research_results, project_name
            )
            
            if report_url:
                return {
                    'success': True,
                    'report_url': report_url,
                    'research_results': research_results,
                    'agents_executed': len(self.agent_results),
                    'overall_confidence': self._calculate_overall_confidence()
                }
            else:
                # Fallback: return results without Google Sheets
                return {
                    'success': True,
                    'report_url': None,
                    'research_results': research_results,
                    'agents_executed': len(self.agent_results),
                    'overall_confidence': self._calculate_overall_confidence(),
                    'note': 'Google Sheets report generation unavailable'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Report generation failed: {str(e)}'
            }
    
    def _update_context_with_results(self, agent_role: AgentRole, result: AgentResult):
        """Update research context with agent results for subsequent agents."""
        
        if agent_role == AgentRole.FUNDAMENTAL_ANALYST:
            self.research_request['fundamental_analysis'] = result.data
        elif agent_role == AgentRole.SENTIMENT_ANALYST:
            self.research_request['sentiment_analysis'] = result.data
        elif agent_role == AgentRole.SUPPLY_CHAIN_ANALYST:
            self.research_request['supply_chain_analysis'] = result.data
        elif agent_role == AgentRole.RISK_ANALYST:
            self.research_request['risk_analysis'] = result.data
    
    def _summarize_agent_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of agent data for logging/status."""
        
        summary = {}
        
        # Extract key metrics
        if 'company_analyses' in data:
            summary['companies_analyzed'] = len(data['company_analyses'])
        
        if 'analysis_timestamp' in data:
            summary['analysis_timestamp'] = data['analysis_timestamp']
        
        if 'methodology' in data:
            summary['methodology_count'] = len(data['methodology'])
        
        return summary
    
    def _calculate_overall_confidence(self) -> float:
        """Calculate overall workflow confidence from agent results."""
        
        if not self.agent_results:
            return 0.0
        
        confidences = [result.confidence for result in self.agent_results.values()]
        return sum(confidences) / len(confidences)
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current workflow status."""
        
        return {
            'workflow_id': self.workflow_id,
            'status': self.status.value,
            'current_stage': self.current_stage.value,
            'progress_percentage': self.progress_percentage,
            'current_operation': self.current_operation,
            'start_time': self.start_time.isoformat(),
            'completion_time': self.completion_time.isoformat() if self.completion_time else None,
            'agents_completed': list(self.agent_results.keys()),
            'errors': self.errors,
            'overall_confidence': self._calculate_overall_confidence() if self.agent_results else 0.0
        }
    
    async def get_results(self) -> Optional[Dict[str, Any]]:
        """Get workflow results if completed."""
        
        if self.status != WorkflowStatus.COMPLETED:
            return None
        
        return self.stage_results.get(WorkflowStage.REPORT_GENERATION, {}).get('research_results')
    
    async def cancel(self) -> bool:
        """Cancel the workflow execution."""
        
        self._cancelled = True
        self._cancel_event.set()
        
        if self.status == WorkflowStatus.RUNNING:
            self.status = WorkflowStatus.CANCELLED
            self.completion_time = datetime.now()
            self.current_operation = "Workflow cancelled by user"
            
            self.logger.info("workflow_cancelled")
            return True
        
        return False