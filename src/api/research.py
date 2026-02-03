"""Research project API endpoints."""

from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.data.models import ResearchProject, ResearchStatus
from .schemas import (
    ResearchProjectCreate,
    ResearchProjectResponse,
    ResearchProjectUpdate,
    ResearchScopeDefinition,
)

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=ResearchProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_research_project(
    project_data: ResearchProjectCreate,
    db: AsyncSession = Depends(get_db_session),
) -> ResearchProjectResponse:
    """Create a new research project."""
    logger.info("creating_research_project", query=project_data.query[:100])
    
    try:
        # Create new project
        project = ResearchProject(
            user_id=project_data.user_id,
            query=project_data.query,
            scope=project_data.scope.dict() if project_data.scope else {},
            status=ResearchStatus.PENDING.value,
        )
        
        db.add(project)
        await db.commit()
        await db.refresh(project)
        
        logger.info("research_project_created", project_id=project.id)
        return ResearchProjectResponse.from_orm(project)
        
    except Exception as e:
        logger.error("create_research_project_failed", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create research project"
        )


@router.get("/{project_id}", response_model=ResearchProjectResponse)
async def get_research_project(
    project_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ResearchProjectResponse:
    """Get a research project by ID."""
    logger.info("getting_research_project", project_id=project_id)
    
    # TODO: Implement proper query with relationships
    project = await db.get(ResearchProject, project_id)
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    return ResearchProjectResponse.from_orm(project)


@router.get("/", response_model=List[ResearchProjectResponse])
async def list_research_projects(
    user_id: Optional[str] = None,
    status_filter: Optional[ResearchStatus] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
) -> List[ResearchProjectResponse]:
    """List research projects with optional filtering."""
    logger.info("listing_research_projects", user_id=user_id, status=status_filter)
    
    # TODO: Implement proper query with filtering
    # For now, return empty list
    return []


@router.put("/{project_id}", response_model=ResearchProjectResponse)
async def update_research_project(
    project_id: str,
    update_data: ResearchProjectUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> ResearchProjectResponse:
    """Update a research project."""
    logger.info("updating_research_project", project_id=project_id)
    
    project = await db.get(ResearchProject, project_id)
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    # Update fields
    if update_data.status:
        project.status = update_data.status.value
    if update_data.executive_summary:
        project.executive_summary = update_data.executive_summary
    if update_data.key_findings:
        project.key_findings = update_data.key_findings
    
    await db.commit()
    await db.refresh(project)
    
    logger.info("research_project_updated", project_id=project_id)
    return ResearchProjectResponse.from_orm(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_research_project(
    project_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a research project."""
    logger.info("deleting_research_project", project_id=project_id)
    
    project = await db.get(ResearchProject, project_id)
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research project not found"
        )
    
    await db.delete(project)
    await db.commit()
    
    logger.info("research_project_deleted", project_id=project_id)