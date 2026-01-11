#!/usr/bin/env python3
"""
Upwork Automation Tool
A simple Python tool that automates Upwork job applications by extracting saved jobs,
generating AI cover letters, and submitting applications through browser automation.

Usage:
    python main.py refresh           # Get saved jobs from Upwork
    python main.py list             # Show available jobs  
    python main.py apply 1,3,5      # Apply to jobs by numbers
    python main.py status           # Show application history
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.cli import cli
from src.config import setup_logging

def main():
    """Main entry point for the application"""
    try:
        # Setup logging
        setup_logging()
        
        # Get logger
        logger = logging.getLogger(__name__)
        logger.info("Starting Upwork Automation Tool")
        
        # Run CLI interface
        cli()
        
    except KeyboardInterrupt:
        print("\n\nApplication interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
