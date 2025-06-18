# Main entry point for the MCP Server
import logging

from config import settings # For logger configuration
from mcp.server.fastmcp import FastMCP

# Initialize server context and SCP listener
# Importing lifecycle will also register the atexit shutdown hook
from mcp_server.lifecycle import _initialize_server
from mcp_server.context import dicom_context # To ensure context is available if needed by tools directly (though it's passed via mcp)

# Import tool functions
from mcp_server.tools.query import query_studies, query_series, query_instances_dicomweb
from mcp_server.tools.store import move_dicom_entity_to_local_server, get_local_instance_pixel_data

# --- 1. Configuración del Logger ---
logging.basicConfig(level=settings.logging.level, format=settings.logging.format, force=True)
logger = logging.getLogger(__name__)
logger.info("MCP Server Main starting up...")

# --- 2. Initialize Server (Context, SCP) ---
_initialize_server()
logger.info("MCP Server Initialization complete.")

# --- 3. Define the MCP Server Instance ---
mcp = FastMCP(
    "ServidorDeHerramientasDICOM",
    description="Un servidor que expone operaciones DICOM como herramientas para agentes de IA."
)
logger.info(f"FastMCP server '{mcp.name}' created.")

# --- 4. Register Tools ---
# Decorate and register each imported tool function

# Query Tools
mcp.tool()(query_studies) # Register by calling the decorator and passing the function
mcp.tool()(query_series)
mcp.tool()(query_instances_dicomweb)
logger.info("Query tools registered.")

# Store Tools
mcp.tool()(move_dicom_entity_to_local_server)
mcp.tool()(get_local_instance_pixel_data)
logger.info("Store tools registered.")

# The FastMCP server might have a run() method or similar
# For now, setting up the instance and tools is the goal.
# If FastMCP runs itself upon instantiation or via a global registry, this might be enough.
# Otherwise, a mcp.run() or similar call would be needed here for an active server.
logger.info("MCP Server setup complete. Ready to serve tools.")
