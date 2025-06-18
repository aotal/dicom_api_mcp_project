import logging
import threading
import atexit

from config import settings
import dicom_scp
import pacs_operations
# Import DicomToolContext for type hinting and dicom_context to be populated
from mcp_server.context import DicomToolContext
from mcp_server import context as mcp_context_module

logger = logging.getLogger(__name__)
scp_thread: Optional[threading.Thread] = None

def _initialize_server():
    global scp_thread
    logger.info("Inicializando servidor MCP (desde lifecycle)...")

    mcp_context_module.dicom_context = DicomToolContext(
        pacs_config={
            "PACS_IP": settings.gateway.pacs_node.ip,
            "PACS_PORT": settings.gateway.pacs_node.port,
            "PACS_AET": settings.gateway.pacs_node.aet,
            "AE_TITLE": settings.gateway.client_ae.aet
        },
        move_destination_aet=settings.gateway.local_scp.aet
    )
    logger.info("Contexto DICOM inicializado (desde lifecycle).")

    scp_thread = threading.Thread(
        target=dicom_scp.start_scp_server,
        args=(
            settings.gateway.local_scp.aet,
            settings.gateway.local_scp.port,
            settings.gateway.local_scp.storage_dir
        ),
        daemon=True
    )
    scp_thread.start()
    logger.info(f"Hilo del servidor C-STORE SCP iniciado (AET: {settings.gateway.local_scp.aet}) (desde lifecycle).")

def _shutdown_scp_server():
    logger.info("Señal de apagado recibida. Deteniendo servidor SCP (desde lifecycle)...")
    if hasattr(dicom_scp, 'ae_scp') and dicom_scp.ae_scp and hasattr(dicom_scp.ae_scp, 'is_running') and dicom_scp.ae_scp.is_running:
        dicom_scp.ae_scp.shutdown()

    if scp_thread and scp_thread.is_alive():
        scp_thread.join(timeout=5.0)
        if not scp_thread.is_alive():
            logger.info("Hilo del servidor SCP detenido limpiamente (desde lifecycle).")
        else:
            logger.warning("El hilo del servidor SCP no finalizó a tiempo (desde lifecycle).")

atexit.register(_shutdown_scp_server)
