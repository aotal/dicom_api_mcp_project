# server.py
from mcp.server.fastmcp import FastMCP
from tools import dicom_tools

# 1. Crear una instancia del servidor MCP
mcp = FastMCP("Demo")

# 2. Registrar las herramientas desde tools.py
dicom_tools(mcp)



# Para ejecutar el servidor, necesitarías añadir la lógica correspondiente,
# por ejemplo:
# if __name__ == "__main__":
#     mcp.run()