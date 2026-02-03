#!/usr/bin/env python3
"""
ResearchLab CLI Entry Point

This is the main entry point for the ResearchLab command-line interface.
Run with: python cli.py [command] [options]
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path so we can import modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

try:
    from src.cli.main import cli
    
    if __name__ == "__main__":
        cli()

except ImportError as e:
    print(f"❌ Error importing CLI modules: {e}")
    print("Make sure you're in the project root directory and all dependencies are installed.")
    print("Try: pip install -e .")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error starting CLI: {e}")
    sys.exit(1)