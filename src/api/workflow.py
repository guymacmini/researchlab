"""Workflow management API endpoints."""

from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.workflow import ResearchWorkflowOrchestrator, WorkflowStatus, WorkflowStage
from src.agents.base import AgentRole

router = APIRouter(prefix="/workflow", tags=["workflow"])


# Pydantic models
class WorkflowStatusResponse(BaseModel):
    """Workflow status response."""
    workflow_id: str
    status: str
    current_stage: str
    progress_percentage: float = Field(..., ge=0, le=100)
    current_operation: str
    start_time: datetime
    completion_time: Optional[datetime] = None
    agents_completed: List[str]
    errors: List[str]
    overall_confidence: float = Field(..., ge=0, le=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "wf_123e4567-e89b-12d3-a456-426614174000",
                "status": "running",
                "current_stage": "sentiment_analysis",
                "progress_percentage": 60.0,
                "current_operation": "Running Sentiment Analyst analysis",
                "start_time": "2024-02-03T14:00:00Z",
                "agents_completed": ["research_director", "fundamental_analyst"],
                "errors": [],
                "overall_confidence": 0.72
            }
        }


class WorkflowResults(BaseModel):
    """Complete workflow results."""
    workflow_id: str
    investment_thesis: str
    companies: List[Dict[str, Any]]
    research_plan: Dict[str, Any]
    
    # Agent results
    fundamental_analysis: Dict[str, Any]
    sentiment_analysis: Dict[str, Any]
    supply_chain_analysis: Dict[str, Any]
    quantitative_analysis: Dict[str, Any]
    risk_analysis: Dict[str, Any]
    
    # Metadata
    workflow_metadata: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "wf_456",
                "investment_thesis": "AI will drive growth",
                "companies": [
                    {"symbol": "AAPL", "name": "Apple Inc."}
                ],
                "fundamental_analysis": {
                    "company_analyses": {},
                    "methodology": {},
                    "confidence": 0.85
                },
                "workflow_metadata": {
                    "agents_executed": 5,
                    "total_confidence": 0.78,
                    "execution_time": 480.5
                }
            }
        }


class ActiveWorkflow(BaseModel):
    """Active workflow summary."""
    workflow_id: str
    status: str
    current_stage: str
    progress_percentage: float
    start_time: datetime
    agents_completed: int
    total_agents: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "wf_789",
                "status": "running",
                "current_stage": "risk_analysis", 
                "progress_percentage": 80.0,
                "start_time": "2024-02-03T14:30:00Z",
                "agents_completed": 4,
                "total_agents": 5
            }
        }


class WorkflowSystemStatus(BaseModel):
    """System-wide workflow status."""
    total_workflows: int
    active_workflows: int
    completed_workflows: int
    failed_workflows: int
    system_load: float = Field(..., ge=0, le=1, description="System load percentage")
    average_execution_time: Optional[float] = None
    success_rate: float = Field(..., ge=0, le=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_workflows": 150,
                "active_workflows": 3,
                "completed_workflows": 140,
                "failed_workflows": 7,
                "system_load": 0.25,
                "average_execution_time": 420.5,
                "success_rate": 0.953
            }
        }


# API Endpoints
@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse, 
           summary="Get workflow status")
async def get_workflow_status(workflow_id: str) -> WorkflowStatusResponse:
    """
    Get detailed status of a specific workflow.
    
    Returns comprehensive information about workflow execution including:
    - Current execution stage and progress
    - Completed agents and remaining work
    - Error information if any issues occurred
    - Overall confidence score from completed analyses
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        status = await orchestrator.get_workflow_status(workflow_id)
        
        if status.get('status') == 'cancelled' and 'error' in status:
            raise HTTPException(status_code=404, detail=status['error'])
        
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            status=status['status'],
            current_stage=status['current_stage'],
            progress_percentage=status['progress_percentage'],
            current_operation=status['current_operation'],
            start_time=datetime.fromisoformat(status['start_time']),
            completion_time=datetime.fromisoformat(status['completion_time']) if status.get('completion_time') else None,
            agents_completed=[agent.value for agent in status['agents_completed']] if status['agents_completed'] else [],
            errors=status['errors'],
            overall_confidence=status['overall_confidence']
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


@router.get("/{workflow_id}/results", response_model=WorkflowResults,
           summary="Get workflow results")
async def get_workflow_results(workflow_id: str) -> WorkflowResults:
    """
    Get complete results from a finished workflow.
    
    Only available for successfully completed workflows. Returns all
    analysis results from each agent and comprehensive research findings.
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        results = await orchestrator.get_workflow_results(workflow_id)
        
        if not results:
            # Check if workflow exists but isn't complete
            status = await orchestrator.get_workflow_status(workflow_id)
            if status.get('status') in ['running', 'pending']:
                raise HTTPException(status_code=400, detail="Workflow not completed yet")
            elif status.get('status') == 'failed':
                raise HTTPException(status_code=400, detail="Workflow failed - no results available")
            else:
                raise HTTPException(status_code=404, detail="Workflow results not found")
        
        return WorkflowResults(
            workflow_id=workflow_id,
            investment_thesis=results.get('investment_thesis', ''),
            companies=results.get('companies', []),
            research_plan=results.get('research_plan', {}),
            fundamental_analysis=results.get('fundamental_analysis', {}),
            sentiment_analysis=results.get('sentiment_analysis', {}),
            supply_chain_analysis=results.get('supply_chain_analysis', {}),
            quantitative_analysis=results.get('quantitative_analysis', {}),
            risk_analysis=results.get('risk_analysis', {}),
            workflow_metadata=results.get('workflow_metadata', {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workflow results: {str(e)}")


@router.post("/{workflow_id}/cancel", summary="Cancel running workflow")
async def cancel_workflow(workflow_id: str) -> Dict[str, str]:
    """
    Cancel a running workflow.
    
    Stops workflow execution and cancels any running agent tasks.
    The workflow status will be updated to 'cancelled'.
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        cancelled = await orchestrator.cancel_workflow(workflow_id)
        
        if not cancelled:
            # Check if workflow exists
            status = await orchestrator.get_workflow_status(workflow_id)
            if status.get('status') == 'cancelled' and 'error' in status:
                raise HTTPException(status_code=404, detail="Workflow not found")
            elif status.get('status') in ['completed', 'failed']:
                raise HTTPException(status_code=400, detail="Cannot cancel completed workflow")
            else:
                raise HTTPException(status_code=400, detail="Failed to cancel workflow")
        
        return {"message": "Workflow cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel workflow: {str(e)}")


@router.get("/active", response_model=List[ActiveWorkflow], 
           summary="List active workflows")
async def list_active_workflows(
    limit: int = Query(20, ge=1, le=100, description="Maximum workflows to return")
) -> List[ActiveWorkflow]:
    """
    List currently active (running or pending) workflows.
    
    Returns basic information about workflows that are currently executing
    or waiting to start. Useful for monitoring system activity.
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        active_workflows = []
        
        # Get all active workflow sessions
        for workflow_id, session in orchestrator.active_workflows.items():
            if session.status.value in ['running', 'pending']:
                status_info = await session.get_status()
                
                active_workflows.append(ActiveWorkflow(
                    workflow_id=workflow_id,
                    status=status_info['status'],
                    current_stage=status_info['current_stage'],
                    progress_percentage=status_info['progress_percentage'],
                    start_time=datetime.fromisoformat(status_info['start_time']),
                    agents_completed=len(status_info['agents_completed']),
                    total_agents=len(orchestrator.workflow_stages) - 2  # Exclude INIT and COMPLETED
                ))
        
        # Sort by start time (newest first) and apply limit
        active_workflows.sort(key=lambda x: x.start_time, reverse=True)
        return active_workflows[:limit]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list active workflows: {str(e)}")


@router.get("/system/status", response_model=WorkflowSystemStatus,
           summary="Get system workflow status")
async def get_system_workflow_status() -> WorkflowSystemStatus:
    """
    Get system-wide workflow statistics and health metrics.
    
    Returns aggregate information about workflow execution including
    success rates, average execution times, and current system load.
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Count workflows by status
        active_count = 0
        completed_count = 0
        failed_count = 0
        execution_times = []
        
        for workflow_id, session in orchestrator.active_workflows.items():
            if session.status.value == 'running' or session.status.value == 'pending':
                active_count += 1
            elif session.status.value == 'completed':
                completed_count += 1
                # Calculate execution time if available
                if session.completion_time:
                    execution_time = (session.completion_time - session.start_time).total_seconds()
                    execution_times.append(execution_time)
            elif session.status.value == 'failed':
                failed_count += 1
        
        total_workflows = active_count + completed_count + failed_count
        
        # Calculate metrics
        success_rate = completed_count / total_workflows if total_workflows > 0 else 0.0
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else None
        
        # Simple system load calculation (based on active workflows vs capacity)
        max_concurrent = 10  # Maximum concurrent workflows
        system_load = min(1.0, active_count / max_concurrent)
        
        return WorkflowSystemStatus(
            total_workflows=total_workflows,
            active_workflows=active_count,
            completed_workflows=completed_count,
            failed_workflows=failed_count,
            system_load=system_load,
            average_execution_time=avg_execution_time,
            success_rate=success_rate
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")


@router.get("/stages", summary="Get available workflow stages")
async def get_workflow_stages() -> Dict[str, List[str]]:
    """
    Get list of available workflow stages and agent roles.
    
    Returns the standard workflow execution sequence and available
    agent types that can be used in research projects.
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Get workflow stages (exclude internal stages)
        stages = [stage.value for stage in orchestrator.workflow_stages 
                 if stage.value not in ['initialization', 'completed', 'failed']]
        
        # Get available agent roles
        agent_roles = [role.value for role in AgentRole]
        
        # Get agent dependencies
        dependencies = {}
        for agent, deps in orchestrator.agent_dependencies.items():
            dependencies[agent.value] = [dep.value for dep in deps]
        
        return {
            "workflow_stages": stages,
            "agent_roles": agent_roles,
            "agent_dependencies": dependencies
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workflow stages: {str(e)}")


@router.post("/cleanup", summary="Cleanup old workflows")
async def cleanup_workflows(
    max_age_hours: int = Query(24, ge=1, le=168, description="Maximum age in hours")
) -> Dict[str, int]:
    """
    Clean up old completed workflows to free memory.
    
    Removes workflow sessions that have been completed or failed
    for longer than the specified age. This helps manage memory usage.
    """
    
    try:
        orchestrator = ResearchWorkflowOrchestrator()
        
        # Count workflows before cleanup
        initial_count = len(orchestrator.active_workflows)
        
        # Perform cleanup
        orchestrator.cleanup_completed_workflows(max_age_hours=max_age_hours)
        
        # Count workflows after cleanup
        final_count = len(orchestrator.active_workflows)
        cleaned_count = initial_count - final_count
        
        return {
            "cleaned_workflows": cleaned_count,
            "remaining_workflows": final_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup workflows: {str(e)}")