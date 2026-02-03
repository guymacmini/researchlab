"""Research project management API endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.data.models import ResearchProject, ResearchStatus
from src.agents.orchestrator import get_orchestrator, AgentOrchestrator
from src.agents.base import AgentRole
from src.core.workflow import ResearchWorkflowOrchestrator

router = APIRouter(prefix="/research", tags=["research"])


# Pydantic models for API
class CompanyInfo(BaseModel):
    """Company information for research."""
    symbol: str = Field(..., description="Stock ticker symbol")
    name: str = Field(..., description="Company name")
    sector: Optional[str] = Field(None, description="Industry sector")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "sector": "Technology",
                "market_cap": 3000000000000
            }
        }


class ResearchRequest(BaseModel):
    """Request to start new research project."""
    query: str = Field(..., description="Research question or thesis")
    investment_thesis: Optional[str] = Field(None, description="Investment thesis statement")
    companies: List[CompanyInfo] = Field(..., description="Companies to analyze")
    time_horizon: Optional[int] = Field(12, description="Investment time horizon in months")
    risk_tolerance: Optional[str] = Field("moderate", description="Risk tolerance (conservative, moderate, aggressive)")
    
    # Agent configuration
    agents: Optional[List[AgentRole]] = Field(None, description="Specific agents to use")
    priority: Optional[str] = Field("normal", description="Research priority (low, normal, high)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Is Apple a good long-term investment given AI trends?",
                "investment_thesis": "Apple will benefit from AI integration across its ecosystem",
                "companies": [
                    {
                        "symbol": "AAPL",
                        "name": "Apple Inc.",
                        "sector": "Technology"
                    }
                ],
                "time_horizon": 24,
                "risk_tolerance": "moderate"
            }
        }


class ResearchResponse(BaseModel):
    """Response after starting research."""
    project_id: str = Field(..., description="Unique project identifier")
    workflow_id: str = Field(..., description="Workflow execution identifier")
    status: str = Field(..., description="Current status")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    agents_count: int = Field(..., description="Number of agents assigned")
    
    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "proj_123e4567-e89b-12d3-a456-426614174000",
                "workflow_id": "wf_987fcdeb-51a2-43d7-8c9d-123456789abc",
                "status": "running",
                "estimated_completion": "2024-02-03T15:30:00Z",
                "agents_count": 5
            }
        }


class ResearchStatus(BaseModel):
    """Research project status."""
    project_id: str
    workflow_id: str
    status: str
    progress_percentage: float = Field(..., ge=0, le=100)
    current_stage: str
    current_operation: str
    start_time: datetime
    completion_time: Optional[datetime] = None
    agents_completed: List[str]
    errors: List[str]
    overall_confidence: float = Field(..., ge=0, le=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "proj_123",
                "workflow_id": "wf_456", 
                "status": "running",
                "progress_percentage": 65.0,
                "current_stage": "quantitative_analysis",
                "current_operation": "Running Quantitative Analyst analysis",
                "start_time": "2024-02-03T14:00:00Z",
                "agents_completed": ["research_director", "fundamental_analyst"],
                "errors": [],
                "overall_confidence": 0.75
            }
        }


class ResearchResults(BaseModel):
    """Complete research results."""
    project_id: str
    workflow_id: str
    query: str
    investment_thesis: str
    companies: List[CompanyInfo]
    
    # Analysis results
    fundamental_analysis: Dict[str, Any]
    sentiment_analysis: Dict[str, Any]
    supply_chain_analysis: Dict[str, Any]
    quantitative_analysis: Dict[str, Any]
    risk_analysis: Dict[str, Any]
    
    # Summary
    overall_confidence: float
    recommendation: str
    key_findings: List[str]
    risks: List[str]
    opportunities: List[str]
    
    # Metadata
    generated_at: datetime
    report_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "proj_123",
                "workflow_id": "wf_456",
                "query": "Is Apple a good investment?",
                "overall_confidence": 0.82,
                "recommendation": "BUY - Strong fundamentals with AI growth potential",
                "key_findings": [
                    "Strong revenue growth in services segment",
                    "Solid balance sheet with low debt-to-equity",
                    "AI integration driving innovation"
                ],
                "risks": [
                    "Regulatory pressure in multiple markets",
                    "Dependence on iPhone sales"
                ],
                "opportunities": [
                    "AI ecosystem expansion",
                    "Services revenue growth"
                ]
            }
        }


class ProjectSummary(BaseModel):
    """Brief project summary for listings."""
    project_id: str
    query: str
    status: str
    created_at: datetime
    completion_time: Optional[datetime] = None
    companies_count: int
    overall_confidence: Optional[float] = None


# API Endpoints
@router.post("/", response_model=ResearchResponse, summary="Start new research project")
async def start_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session)
) -> ResearchResponse:
    """
    Start a new research project with comprehensive analysis.
    
    This endpoint initiates a complete research workflow that includes:
    - Research Director planning and scope definition
    - Fundamental analysis of financials and metrics
    - Sentiment analysis from news and social media
    - Supply chain and competitive analysis
    - Quantitative analysis and risk assessment
    - Report generation and recommendations
    """
    
    try:
        # Generate unique IDs
        project_id = f"proj_{uuid.uuid4()}"
        
        # Create database record
        project = ResearchProject(
            id=project_id,
            query=request.query,
            investment_thesis=request.investment_thesis or "",
            status=ResearchStatus.PENDING,
            created_at=datetime.now(),
            metadata={
                "companies": [company.dict() for company in request.companies],
                "time_horizon": request.time_horizon,
                "risk_tolerance": request.risk_tolerance,
                "priority": request.priority
            }
        )
        
        db.add(project)
        await db.commit()
        
        # Start workflow
        workflow_orchestrator = ResearchWorkflowOrchestrator()
        
        workflow_request = {
            "project_id": project_id,
            "query": request.query,
            "investment_thesis": request.investment_thesis or "",
            "companies": [company.dict() for company in request.companies],
            "time_horizon": request.time_horizon,
            "risk_tolerance": request.risk_tolerance
        }
        
        workflow_id = await workflow_orchestrator.start_research_workflow(workflow_request)
        
        # Update project with workflow ID
        project.workflow_id = workflow_id
        await db.commit()
        
        # Estimate completion time (rough estimate based on agent count)
        agent_count = len(request.agents) if request.agents else 5  # Default agents
        estimated_minutes = agent_count * 10  # 10 minutes per agent
        estimated_completion = datetime.now().replace(
            minute=datetime.now().minute + estimated_minutes
        )
        
        return ResearchResponse(
            project_id=project_id,
            workflow_id=workflow_id,
            status="pending",
            estimated_completion=estimated_completion,
            agents_count=agent_count
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start research: {str(e)}")


@router.get("/{project_id}/status", response_model=ResearchStatus, summary="Get research status")
async def get_research_status(
    project_id: str,
    db: AsyncSession = Depends(get_db_session)
) -> ResearchStatus:
    """
    Get the current status of a research project.
    
    Returns detailed information about the research progress,
    including current stage, completion percentage, and any errors.
    """
    
    try:
        # Get project from database
        project = await db.get(ResearchProject, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        
        # Get workflow status
        if project.workflow_id:
            workflow_orchestrator = ResearchWorkflowOrchestrator()
            workflow_status = await workflow_orchestrator.get_workflow_status(project.workflow_id)
            
            return ResearchStatus(
                project_id=project_id,
                workflow_id=project.workflow_id,
                status=workflow_status.get('status', 'unknown'),
                progress_percentage=workflow_status.get('progress_percentage', 0.0),
                current_stage=workflow_status.get('current_stage', 'unknown'),
                current_operation=workflow_status.get('current_operation', ''),
                start_time=datetime.fromisoformat(workflow_status.get('start_time', datetime.now().isoformat())),
                completion_time=datetime.fromisoformat(workflow_status['completion_time']) if workflow_status.get('completion_time') else None,
                agents_completed=workflow_status.get('agents_completed', []),
                errors=workflow_status.get('errors', []),
                overall_confidence=workflow_status.get('overall_confidence', 0.0)
            )
        else:
            return ResearchStatus(
                project_id=project_id,
                workflow_id="",
                status=project.status.value,
                progress_percentage=0.0,
                current_stage="initialization",
                current_operation="Project created",
                start_time=project.created_at,
                agents_completed=[],
                errors=[],
                overall_confidence=0.0
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/{project_id}/results", response_model=ResearchResults, summary="Get research results")
async def get_research_results(
    project_id: str,
    db: AsyncSession = Depends(get_db_session)
) -> ResearchResults:
    """
    Get the complete results of a finished research project.
    
    Only available for completed research projects. Returns comprehensive
    analysis results, recommendations, and generated reports.
    """
    
    try:
        # Get project from database
        project = await db.get(ResearchProject, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        
        if project.status != ResearchStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Research project not completed yet")
        
        # Get workflow results
        if project.workflow_id:
            workflow_orchestrator = ResearchWorkflowOrchestrator()
            workflow_results = await workflow_orchestrator.get_workflow_results(project.workflow_id)
            
            if not workflow_results:
                raise HTTPException(status_code=404, detail="Research results not found")
            
            # Extract companies from metadata
            companies_data = project.metadata.get('companies', [])
            companies = [CompanyInfo(**company) for company in companies_data]
            
            # Generate summary insights
            recommendation, key_findings, risks, opportunities = _generate_summary_insights(workflow_results)
            
            return ResearchResults(
                project_id=project_id,
                workflow_id=project.workflow_id,
                query=project.query,
                investment_thesis=project.investment_thesis,
                companies=companies,
                fundamental_analysis=workflow_results.get('fundamental_analysis', {}),
                sentiment_analysis=workflow_results.get('sentiment_analysis', {}),
                supply_chain_analysis=workflow_results.get('supply_chain_analysis', {}),
                quantitative_analysis=workflow_results.get('quantitative_analysis', {}),
                risk_analysis=workflow_results.get('risk_analysis', {}),
                overall_confidence=workflow_results.get('workflow_metadata', {}).get('total_confidence', 0.0),
                recommendation=recommendation,
                key_findings=key_findings,
                risks=risks,
                opportunities=opportunities,
                generated_at=project.updated_at or project.created_at,
                report_url=workflow_results.get('report_url')
            )
        else:
            raise HTTPException(status_code=400, detail="No workflow results available")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")


@router.get("/", response_model=List[ProjectSummary], summary="List research projects")
async def list_research_projects(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of projects to return"),
    offset: int = Query(0, ge=0, description="Number of projects to skip"),
    db: AsyncSession = Depends(get_db_session)
) -> List[ProjectSummary]:
    """
    List research projects with optional filtering.
    
    Returns a paginated list of research projects with basic information.
    Use the project_id to get detailed status or results.
    """
    
    try:
        # Build query
        query_builder = db.query(ResearchProject)
        
        if status:
            try:
                status_enum = ResearchStatus(status)
                query_builder = query_builder.filter(ResearchProject.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        # Add pagination
        query_builder = query_builder.offset(offset).limit(limit)
        
        # Execute query (note: this is a simplified version, real implementation would use async properly)
        projects = []  # Would execute query here
        
        # Convert to response format
        project_summaries = []
        for project in projects:
            companies_count = len(project.metadata.get('companies', []))
            
            project_summaries.append(ProjectSummary(
                project_id=project.id,
                query=project.query,
                status=project.status.value,
                created_at=project.created_at,
                completion_time=project.updated_at if project.status == ResearchStatus.COMPLETED else None,
                companies_count=companies_count,
                overall_confidence=project.metadata.get('confidence')
            ))
        
        return project_summaries
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")


@router.delete("/{project_id}", summary="Cancel/delete research project")
async def cancel_research_project(
    project_id: str,
    db: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Cancel a running research project or delete a completed one.
    
    For running projects, this will cancel the workflow and mark the project
    as cancelled. For completed projects, this will delete the project record.
    """
    
    try:
        # Get project from database
        project = await db.get(ResearchProject, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        
        # Cancel workflow if running
        if project.workflow_id and project.status in [ResearchStatus.PENDING, ResearchStatus.IN_PROGRESS]:
            workflow_orchestrator = ResearchWorkflowOrchestrator()
            cancelled = await workflow_orchestrator.cancel_workflow(project.workflow_id)
            
            if cancelled:
                project.status = ResearchStatus.CANCELLED
                project.updated_at = datetime.now()
                await db.commit()
                return {"message": "Research project cancelled successfully"}
        
        # Delete completed or cancelled projects
        if project.status in [ResearchStatus.COMPLETED, ResearchStatus.CANCELLED, ResearchStatus.FAILED]:
            await db.delete(project)
            await db.commit()
            return {"message": "Research project deleted successfully"}
        
        raise HTTPException(status_code=400, detail="Cannot cancel project in current status")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel project: {str(e)}")


@router.post("/{project_id}/restart", response_model=ResearchResponse, summary="Restart failed research")
async def restart_research_project(
    project_id: str,
    db: AsyncSession = Depends(get_db_session)
) -> ResearchResponse:
    """
    Restart a failed research project.
    
    This creates a new workflow execution while preserving the original
    project parameters and requirements.
    """
    
    try:
        # Get project from database
        project = await db.get(ResearchProject, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        
        if project.status != ResearchStatus.FAILED:
            raise HTTPException(status_code=400, detail="Can only restart failed projects")
        
        # Start new workflow
        workflow_orchestrator = ResearchWorkflowOrchestrator()
        
        workflow_request = {
            "project_id": project_id,
            "query": project.query,
            "investment_thesis": project.investment_thesis,
            "companies": project.metadata.get('companies', []),
            "time_horizon": project.metadata.get('time_horizon', 12),
            "risk_tolerance": project.metadata.get('risk_tolerance', 'moderate')
        }
        
        new_workflow_id = await workflow_orchestrator.start_research_workflow(workflow_request)
        
        # Update project
        project.workflow_id = new_workflow_id
        project.status = ResearchStatus.PENDING
        project.updated_at = datetime.now()
        await db.commit()
        
        return ResearchResponse(
            project_id=project_id,
            workflow_id=new_workflow_id,
            status="pending",
            estimated_completion=None,
            agents_count=5  # Default agent count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart project: {str(e)}")


# Helper functions
def _generate_summary_insights(workflow_results: Dict[str, Any]) -> tuple[str, List[str], List[str], List[str]]:
    """Generate summary insights from workflow results."""
    
    # This is a simplified implementation - would use more sophisticated analysis
    recommendation = "HOLD - Requires further analysis"
    key_findings = ["Analysis completed successfully"]
    risks = ["Market volatility", "Regulatory changes"]
    opportunities = ["Growth potential", "Market expansion"]
    
    # Extract insights from different analyses
    fundamental = workflow_results.get('fundamental_analysis', {})
    quantitative = workflow_results.get('quantitative_analysis', {})
    risk_analysis = workflow_results.get('risk_analysis', {})
    
    # Generate recommendation based on confidence and analysis results
    overall_confidence = workflow_results.get('workflow_metadata', {}).get('total_confidence', 0.0)
    
    if overall_confidence > 0.8:
        recommendation = "BUY - High confidence in positive outlook"
    elif overall_confidence > 0.6:
        recommendation = "HOLD - Moderate confidence, monitor developments"
    elif overall_confidence > 0.4:
        recommendation = "HOLD - Mixed signals, requires careful monitoring"
    else:
        recommendation = "AVOID - Low confidence, significant concerns"
    
    # Extract key findings from analysis results
    if fundamental.get('company_analyses'):
        key_findings.append("Fundamental analysis completed for all target companies")
    
    if quantitative.get('trading_signals'):
        key_findings.append("Quantitative trading signals generated")
    
    if risk_analysis.get('risk_factors'):
        key_findings.append("Comprehensive risk assessment completed")
    
    return recommendation, key_findings, risks, opportunities