# Main entry point for the application.
# This script now delegates to the refactored MCP server.

import logging

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting MCP application via main_mcp.py stub...")
    try:
        # Importing mcp_server.main will execute its top-level code,
        # which includes server initialization and MCP setup.
        from mcp_server import main as mcp_main_module
        logger.info("Successfully imported mcp_server.main. MCP server should be running/ready.")
        # If mcp_server.main.py needs an explicit run command that is not already called,
        # it would be invoked here, e.g.:
        # if hasattr(mcp_main_module, 'run_server'):
        #     mcp_main_module.run_server()
        # For now, assuming import is enough or mcp_server.main handles its execution flow.
    except ImportError as e:
        logger.error(f"Failed to import mcp_server.main: {e}")
        logger.error("Please ensure the mcp_server package is correctly structured and in PYTHONPATH.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during MCP server startup via stub: {e}", exc_info=True)
else:
    # This case might occur if main_mcp.py is imported by another module, though it's less likely
    # now that it's primarily a stub.
    logger.info("main_mcp.py was imported. For direct execution, run as script.")