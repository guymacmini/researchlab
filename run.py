#!/usr/bin/env python3
"""
ResearchLab LITE - Simple AI Investment Research

One command to start everything:
    python run.py

Make sure you have:
1. Added your API keys to .env file
2. Installed requirements: pip install -r requirements-lite.txt
"""

import os
import sys
import asyncio
import webbrowser
from pathlib import Path

import uvicorn
import structlog

# Add src to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.lite.config import settings
from src.lite.app import app


def setup_logging():
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=True)
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def check_environment():
    """Check if environment is properly configured."""
    logger = structlog.get_logger()
    
    # Check if .env file exists
    env_files = [".env", ".env.lite"]
    env_file = None
    
    for file in env_files:
        if Path(file).exists():
            env_file = file
            break
    
    if not env_file:
        print("❌ No .env file found!")
        print("\n📋 SETUP REQUIRED:")
        print("1. Copy .env.lite to .env:")
        print("   cp .env.lite .env")
        print("\n2. Edit .env and add your API keys:")
        print("   ANTHROPIC_API_KEY=sk-ant-your_real_key_here")
        print("   FINNHUB_API_KEY=your_real_finnhub_key_here")
        print("\n3. Get your free API keys:")
        print("   • Anthropic: https://console.anthropic.com/")
        print("   • Finnhub: https://finnhub.io/dashboard")
        sys.exit(1)
    
    logger.info("Environment file found", file=env_file)
    
    # Validate API keys
    try:
        settings.validate_required_keys()
        logger.info("✅ API keys validated successfully")
    except ValueError as e:
        print(f"❌ {e}")
        print("\n📝 Please update your .env file with valid API keys:")
        print("   • ANTHROPIC_API_KEY=sk-ant-your_real_key_here")
        print("   • FINNHUB_API_KEY=your_real_finnhub_key_here")
        print("\n🔗 Get your free API keys:")
        print("   • Anthropic: https://console.anthropic.com/")
        print("   • Finnhub: https://finnhub.io/dashboard")
        sys.exit(1)
    
    return True


def print_startup_info():
    """Print startup information and instructions."""
    print("\n" + "="*60)
    print("🚀 ResearchLab LITE Starting...")
    print("="*60)
    print(f"📊 Version: {settings.version}")
    print(f"🌐 URL: http://{settings.host}:{settings.port}")
    print(f"📁 Database: {settings.database_file}")
    print("="*60)
    print("✨ Features:")
    print("  • AI-powered stock analysis")
    print("  • Real-time financial data")  
    print("  • Simple web interface")
    print("  • Research history")
    print("="*60)
    print("🎯 Usage:")
    print("  1. Open browser to the URL above")
    print("  2. Enter any research query")
    print("  3. Get instant AI analysis!")
    print("="*60)


async def open_browser():
    """Open browser after a short delay."""
    await asyncio.sleep(2)  # Wait for server to start
    url = f"http://{settings.host}:{settings.port}"
    try:
        webbrowser.open(url)
        print(f"🌐 Browser opened to {url}")
    except Exception:
        print(f"💡 Open your browser to: {url}")


def main():
    """Main entry point."""
    setup_logging()
    logger = structlog.get_logger()
    
    print("🔍 Checking environment...")
    check_environment()
    
    print_startup_info()
    
    # Browser opening moved to after server start hint
    url = f"http://{settings.host}:{settings.port}"
    print(f"\n🌐 Open your browser to: {url}\n")
    
    # Start the server
    logger.info("Starting uvicorn server")
    
    try:
        uvicorn.run(
            "run:app",
            host=settings.host,
            port=settings.port,
            reload=settings.debug,
            log_level="info",
            access_log=False  # Keep logs clean
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down ResearchLab LITE...")
        print("Thanks for using ResearchLab LITE! 🚀")
    except Exception as e:
        logger.error("Failed to start server", error=str(e))
        print(f"\n❌ Server failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()