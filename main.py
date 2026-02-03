#!/usr/bin/env python3
"""Main entry point for ResearchLab application."""

import uvicorn

from src.core.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "src.core.app:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        log_level=settings.app.log_level.lower(),
    )