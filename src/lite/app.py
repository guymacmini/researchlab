"""Simplified FastAPI app for ResearchLab LITE."""

from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
import json

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import structlog

from .config import settings
from .database import init_database, close_database, get_db, Research
from .agent import agent, ConversationState

logger = structlog.get_logger()

# Pydantic models
class ResearchQuery(BaseModel):
    query: str
    include_clarifying_questions: bool = True


class ConversationStart(BaseModel):
    query: str
    session_id: Optional[str] = None


class ConversationContinue(BaseModel):
    session_id: str
    answers: Dict[str, str]


class ResearchResponse(BaseModel):
    id: int
    query: str
    status: str
    results: Optional[Dict[str, Any]] = None
    clarifying_questions: Optional[List[str]] = None


class ConversationResponse(BaseModel):
    conversation_id: str
    state: str
    original_query: str
    message: Optional[str] = None
    clarifying_questions: Optional[List[str]] = None
    analysis: Optional[Dict[str, Any]] = None
    timestamp: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting ResearchLab LITE")
    
    # Validate API keys
    try:
        settings.validate_required_keys()
        logger.info("API keys validated successfully")
    except ValueError as e:
        logger.error("API key validation failed", error=str(e))
        raise
    
    # Initialize database
    await init_database()
    logger.info("Application started successfully")
    
    yield
    
    logger.info("Shutting down ResearchLab LITE")
    await close_database()


def create_lite_app() -> FastAPI:
    """Create simplified FastAPI application."""
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Lightweight AI-powered investment research tool",
        lifespan=lifespan,
        debug=settings.debug
    )
    
    # Mount static files and templates
    templates = Jinja2Templates(directory="src/lite/templates")
    
    # Add datetime filter
    def format_datetime(value, format="%Y-%m-%d %H:%M"):
        from datetime import datetime
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            # Unix timestamp
            try:
                value = datetime.fromtimestamp(value)
            except:
                return str(value)
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except:
                return value
        if hasattr(value, 'strftime'):
            return value.strftime(format)
        return str(value)
    
    templates.env.filters["datetime"] = format_datetime
    
    # API Routes
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Home page with web interface."""
        return templates.TemplateResponse("index.html", {"request": request})
    
    @app.get("/api/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok", "version": settings.version}
    
    @app.post("/api/conversation/start", response_model=ConversationResponse)
    async def start_conversation(query_data: ConversationStart):
        """Start a new research conversation."""
        try:
            import uuid
            session_id = query_data.session_id or str(uuid.uuid4())
            
            logger.info("Starting conversation", query=query_data.query, session_id=session_id)
            
            result = await agent.start_conversation(query_data.query, session_id)
            
            return ConversationResponse(**result)
            
        except Exception as e:
            logger.error("Failed to start conversation", query=query_data.query, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to start conversation: {str(e)}")
    
    @app.post("/api/conversation/continue", response_model=ConversationResponse)
    async def continue_conversation(continue_data: ConversationContinue):
        """Continue conversation with answers to clarifying questions."""
        try:
            logger.info("Continuing conversation", session_id=continue_data.session_id)
            
            result = await agent.continue_conversation(continue_data.session_id, continue_data.answers)
            
            return ConversationResponse(**result)
            
        except Exception as e:
            logger.error("Failed to continue conversation", session_id=continue_data.session_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to continue conversation: {str(e)}")

    @app.post("/api/research", response_model=ResearchResponse)
    async def start_research(query_data: ResearchQuery):
        """Legacy endpoint - start a research query directly."""
        try:
            logger.info("Starting direct research (legacy)", query=query_data.query)
            
            # Generate clarifying questions if requested
            clarifying_questions = None
            if query_data.include_clarifying_questions:
                clarifying_questions = await agent.get_clarifying_questions(query_data.query)
            
            # Perform research
            results = await agent.research_company(query_data.query)
            
            return ResearchResponse(
                id=results["id"],
                query=query_data.query,
                status="completed",
                results=results,
                clarifying_questions=clarifying_questions
            )
            
        except Exception as e:
            logger.error("Research failed", query=query_data.query, error=str(e))
            raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")
    
    @app.get("/api/research/{research_id}", response_model=ResearchResponse)
    async def get_research(research_id: int):
        """Get research results by ID."""
        async with get_db() as db:
            result = await db.get(Research, research_id)
            
            if not result:
                raise HTTPException(status_code=404, detail="Research not found")
            
            results_data = None
            if result.results:
                try:
                    results_data = json.loads(result.results)
                except json.JSONDecodeError:
                    pass
            
            return ResearchResponse(
                id=result.id,
                query=result.query,
                status=result.status,
                results=results_data
            )
    
    @app.get("/api/research")
    async def list_research(limit: int = 10, offset: int = 0):
        """List recent research queries."""
        async with get_db() as db:
            from sqlalchemy import select
            # Get recent research
            result = await db.execute(
                select(Research.id, Research.query, Research.status, Research.created_at)
                .order_by(Research.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.fetchall()
            
            return {
                "research": [
                    {
                        "id": row[0],
                        "query": row[1],
                        "status": row[2],
                        "created_at": row[3].isoformat() if row[3] else None
                    }
                    for row in rows
                ],
                "limit": limit,
                "offset": offset
            }
    
    # Simple web interface routes
    @app.post("/research", response_class=HTMLResponse)
    async def web_research(request: Request, query: str = Form(...)):
        """Web interface research submission - now using conversation flow."""
        try:
            import uuid
            session_id = str(uuid.uuid4())
            
            # Start conversation
            result = await agent.start_conversation(query, session_id)
            
            # Check if we need clarifying questions
            if result.get("state") == ConversationState.CLARIFYING_QUESTIONS.value:
                return templates.TemplateResponse("clarifying_questions.html", {
                    "request": request,
                    "conversation_id": result["conversation_id"],
                    "original_query": result["original_query"],
                    "clarifying_questions": result["clarifying_questions"],
                    "message": result.get("message", "")
                })
            else:
                # Direct analysis (specific company query)
                return templates.TemplateResponse("results.html", {
                    "request": request,
                    "query": query,
                    "results": result,
                    "conversation_id": session_id
                })
            
        except Exception as e:
            logger.error("Web research failed", query=query, error=str(e))
            return templates.TemplateResponse("error.html", {
                "request": request,
                "query": query,
                "error": str(e)
            })
    
    @app.post("/research/continue", response_class=HTMLResponse)
    async def web_continue_research(request: Request):
        """Continue research conversation with answers."""
        try:
            form_data = await request.form()
            conversation_id = form_data.get("conversation_id")
            
            if not conversation_id:
                raise ValueError("Missing conversation ID")
            
            # Extract answers from form
            answers = {}
            for key, value in form_data.items():
                if key.startswith("answer_"):
                    question_index = key.replace("answer_", "")
                    question = form_data.get(f"question_{question_index}")
                    if question and value:
                        answers[question] = value
            
            # Continue conversation
            result = await agent.continue_conversation(conversation_id, answers)
            
            return templates.TemplateResponse("thematic_results.html", {
                "request": request,
                "conversation_id": conversation_id,
                "original_query": result["original_query"], 
                "answers": result["answers"],
                "companies_analyzed": result["companies_analyzed"],
                "analysis": result["analysis"],
                "timestamp": result["timestamp"]
            })
            
        except Exception as e:
            logger.error("Failed to continue web research", error=str(e))
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": str(e)
            })
    
    @app.get("/research/{research_id}", response_class=HTMLResponse) 
    async def web_research_detail(request: Request, research_id: int):
        """Web interface research detail view."""
        try:
            async with get_db() as db:
                result = await db.get(Research, research_id)
                
                if not result:
                    raise HTTPException(status_code=404, detail="Research not found")
                
                results_data = None
                if result.results:
                    try:
                        results_data = json.loads(result.results)
                    except json.JSONDecodeError:
                        pass
                
                return templates.TemplateResponse("results.html", {
                    "request": request,
                    "query": result.query,
                    "results": results_data,
                    "research_id": research_id
                })
                
        except Exception as e:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": str(e)
            })
    
    @app.get("/history", response_class=HTMLResponse)
    async def web_history(request: Request):
        """Web interface research history."""
        async with get_db() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Research.id, Research.query, Research.status, Research.created_at)
                .order_by(Research.created_at.desc())
                .limit(50)
            )
            rows = result.fetchall()
            
            research_history = [
                {
                    "id": row[0],
                    "query": row[1],
                    "status": row[2], 
                    "created_at": row[3]
                }
                for row in rows
            ]
            
            return templates.TemplateResponse("history.html", {
                "request": request,
                "research_history": research_history
            })
    
    return app


# Create app instance
app = create_lite_app()