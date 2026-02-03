"""Agent execution and monitoring API endpoints."""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.database import get_db_session
from src.data.models import AgentAnalysis, ResearchProject
from src.agents.base import AgentRole
from .schemas import (
    AgentExecutionRequest,
    AgentExecutionStatus,
    AgentAnalysisResponse,
)

logger = structlog.get_logger()
router = APIRouter()


@router.get("/roles", response_model=List[str])
async def list_agent_roles() -> List[str]:
    """List available agent roles."""
    return [role.value for role in AgentRole]


@router.post("/execute", response_model=AgentExecutionStatus)
async def execute_agents(
    request: AgentExecutionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AgentExecutionStatus:
    """Execute agents for a research project."""
    logger.info(
        "executing_agents",
        project_id=request.project_id,
        agents=request.agent_roles
    )
    
    # Verify project exists
    project = await db.get(ResearchProject, request.project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    # Validate agent roles
    valid_roles = {role.value for role in AgentRole}
    invalid_roles = set(request.agent_roles) - valid_roles
    if invalid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent roles: {', '.join(invalid_roles)}"
        )
    
    # TODO: Implement actual agent execution
    # For now, return a mock status
    logger.info("agent_execution_requested", project_id=request.project_id)
    
    return AgentExecutionStatus(
        project_id=request.project_id,
        total_agents=len(request.agent_roles),
        completed_agents=0,
        failed_agents=0,
        in_progress_agents=len(request.agent_roles),
        estimated_remaining_time=300,  # 5 minutes
    )


@router.get("/{project_id}/status", response_model=AgentExecutionStatus)
async def get_execution_status(
    project_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> AgentExecutionStatus:
    """Get agent execution status for a project."""
    logger.info("getting_execution_status", project_id=project_id)
    
    # Verify project exists
    project = await db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    # Query agent analyses for this project
    query = select(AgentAnalysis).where(AgentAnalysis.project_id == project_id)
    result = await db.execute(query)
    analyses = result.scalars().all()
    
    # Calculate status
    total_agents = len(analyses)
    completed_agents = sum(1 for a in analyses if a.success)
    failed_agents = sum(1 for a in analyses if not a.success)
    in_progress_agents = 0  # TODO: Track in-progress agents
    
    return AgentExecutionStatus(
        project_id=project_id,
        total_agents=total_agents,
        completed_agents=completed_agents,
        failed_agents=failed_agents,
        in_progress_agents=in_progress_agents,
        estimated_remaining_time=None,
    )


@router.get("/{project_id}/results", response_model=List[AgentAnalysisResponse])
async def get_agent_results(
    project_id: str,
    agent_role: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
) -> List[AgentAnalysisResponse]:
    """Get agent analysis results for a project."""
    logger.info(
        "getting_agent_results",
        project_id=project_id,
        agent_role=agent_role
    )
    
    # Verify project exists
    project = await db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    # Build query
    query = select(AgentAnalysis).where(AgentAnalysis.project_id == project_id)
    
    if agent_role:
        if agent_role not in {role.value for role in AgentRole}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid agent role: {agent_role}"
            )
        query = query.where(AgentAnalysis.agent_role == agent_role)
    
    # Execute query
    result = await db.execute(query)
    analyses = result.scalars().all()
    
    return [AgentAnalysisResponse.from_attributes(analysis) for analysis in analyses]


@router.get("/{project_id}/results/{agent_role}", response_model=AgentAnalysisResponse)
async def get_agent_result(
    project_id: str,
    agent_role: str,
    db: AsyncSession = Depends(get_db_session),
) -> AgentAnalysisResponse:
    """Get a specific agent analysis result."""
    logger.info(
        "getting_agent_result",
        project_id=project_id,
        agent_role=agent_role
    )
    
    # Validate agent role
    if agent_role not in {role.value for role in AgentRole}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent role: {agent_role}"
        )
    
    # Query for specific agent result
    query = select(AgentAnalysis).where(
        AgentAnalysis.project_id == project_id,
        AgentAnalysis.agent_role == agent_role
    )
    result = await db.execute(query)
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent analysis not found for {agent_role} in project {project_id}"
        )
    
    return AgentAnalysisResponse.from_attributes(analysis)


@router.delete("/{project_id}/results", status_code=status.HTTP_204_NO_CONTENT)
async def clear_agent_results(
    project_id: str,
    agent_role: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Clear agent analysis results for a project."""
    logger.info(
        "clearing_agent_results",
        project_id=project_id,
        agent_role=agent_role
    )
    
    # Verify project exists
    project = await db.get(ResearchProject, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    try:
        # Build delete query
        query = select(AgentAnalysis).where(AgentAnalysis.project_id == project_id)
        
        if agent_role:
            if agent_role not in {role.value for role in AgentRole}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid agent role: {agent_role}"
                )
            query = query.where(AgentAnalysis.agent_role == agent_role)
        
        # Delete analyses
        result = await db.execute(query)
        analyses = result.scalars().all()
        
        for analysis in analyses:
            await db.delete(analysis)
        
        await db.commit()
        
        logger.info(
            "agent_results_cleared",
            project_id=project_id,
            agent_role=agent_role,
            count=len(analyses)
        )
        
    except Exception as e:
        logger.error("clear_agent_results_failed", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear agent results"
        )