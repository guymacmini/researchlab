"""API endpoints for ResearchLab."""

from .research import router as research_router
from .workflow import router as workflow_router
from .news import router as news_router

__all__ = [
    "research_router",
    "workflow_router", 
    "news_router",
]