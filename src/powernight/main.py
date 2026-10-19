"""
PowerNight Main Entry Point

Consolidated entry point for the PowerNight application.
Handles both CLI and application startup.
"""

import sys
import os
from pathlib import Path

# Add src to Python path for imports
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from powernight.cli import cli
from powernight.app import PowerNightApp
from powernight.utils.logging import setup_logging, get_logger


def main():
    """Main entry point for PowerNight application."""
    # Setup logging first
    setup_logging()
    logger = get_logger()
    
    logger.main_logger.info("Starting PowerNight application")
    
    try:
        # If running as CLI, use click interface
        if len(sys.argv) > 1 and not os.environ.get("POWERNIGHT_WEB_APP"):
            cli()
        else:
            # Run as web application
            app = PowerNightApp()
            sys.exit(app.run())
    except KeyboardInterrupt:
        logger.main_logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.main_logger.error(f"Application failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()