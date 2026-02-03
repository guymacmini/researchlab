"""Companies API endpoints."""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from src.core.database import get_db_session
from src.data.models import Company
from .schemas import CompanyCreate, CompanyResponse

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    company_data: CompanyCreate,
    db: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Create a new company."""
    logger.info("creating_company", symbol=company_data.symbol)
    
    try:
        # Check if company already exists
        existing = await db.get(Company, company_data.symbol)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Company with symbol {company_data.symbol} already exists"
            )
        
        # Create new company
        company = Company(
            symbol=company_data.symbol.upper(),
            name=company_data.name,
            exchange=company_data.exchange,
            sector=company_data.sector,
            industry=company_data.industry,
            country=company_data.country,
        )
        
        db.add(company)
        await db.commit()
        await db.refresh(company)
        
        logger.info("company_created", symbol=company.symbol)
        return CompanyResponse.from_attributes(company)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_company_failed", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create company"
        )


@router.get("/{symbol}", response_model=CompanyResponse)
async def get_company(
    symbol: str,
    db: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Get a company by symbol."""
    logger.info("getting_company", symbol=symbol.upper())
    
    company = await db.get(Company, symbol.upper())
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return CompanyResponse.from_attributes(company)


@router.get("/", response_model=List[CompanyResponse])
async def list_companies(
    sector: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search by symbol or name"),
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
) -> List[CompanyResponse]:
    """List companies with optional filtering."""
    logger.info(
        "listing_companies",
        sector=sector,
        country=country,
        search=search,
        limit=limit,
        offset=offset
    )
    
    try:
        # Build query with filters
        query = select(Company)
        
        if sector:
            query = query.where(Company.sector == sector)
        
        if country:
            query = query.where(Company.country == country)
        
        if search:
            search_term = f"%{search.upper()}%"
            query = query.where(
                or_(
                    Company.symbol.like(search_term),
                    Company.name.ilike(search_term)
                )
            )
        
        if min_market_cap is not None:
            query = query.where(Company.market_cap >= min_market_cap)
        
        if max_market_cap is not None:
            query = query.where(Company.market_cap <= max_market_cap)
        
        # Add pagination
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        companies = result.scalars().all()
        
        return [CompanyResponse.from_attributes(company) for company in companies]
        
    except Exception as e:
        logger.error("list_companies_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list companies"
        )


@router.put("/{symbol}", response_model=CompanyResponse)
async def update_company(
    symbol: str,
    company_data: CompanyCreate,
    db: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Update a company."""
    logger.info("updating_company", symbol=symbol.upper())
    
    company = await db.get(Company, symbol.upper())
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    try:
        # Update fields
        company.name = company_data.name
        company.exchange = company_data.exchange
        company.sector = company_data.sector
        company.industry = company_data.industry
        company.country = company_data.country
        
        await db.commit()
        await db.refresh(company)
        
        logger.info("company_updated", symbol=company.symbol)
        return CompanyResponse.from_attributes(company)
        
    except Exception as e:
        logger.error("update_company_failed", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update company"
        )


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    symbol: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a company."""
    logger.info("deleting_company", symbol=symbol.upper())
    
    company = await db.get(Company, symbol.upper())
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    try:
        await db.delete(company)
        await db.commit()
        
        logger.info("company_deleted", symbol=symbol.upper())
        
    except Exception as e:
        logger.error("delete_company_failed", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete company"
        )