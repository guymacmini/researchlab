"""Command-line interface for ResearchLab."""

from .main import cli
from .research import research_cli
from .workflow import workflow_cli
from .news import news_cli
from .config import config_cli
from .sec import sec_cli

__all__ = [
    "cli",
    "research_cli",
    "workflow_cli", 
    "news_cli",
    "config_cli",
    "sec_cli",
]