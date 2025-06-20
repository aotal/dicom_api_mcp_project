# config.py (Versión Híbrida para la migración incremental)

import logging
from pathlib import Path
from pydantic import BaseModel, DirectoryPath, FilePath, Field
from typing import Dict, Optional

# --- Modelos de Configuración con Pydantic ---

class LoggingSettings(BaseModel):
    level: int = logging.INFO
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# =======================================================================
# --- SECCIÓN PARA DIMSE (C-FIND, C-MOVE) - SE MANTIENE COMO ESTABA ---
# Estas clases son necesarias para las herramientas que aún no hemos migrado.
# =======================================================================
class PACSNode(BaseModel):
    """Configuración del nodo PACS remoto al que nos conectamos para DIMSE."""
    ip: str = "localhost"
    port: int = 11112
    aet: str = "DCM4CHEE"

class LocalSCP(BaseModel):
    """Configuración de nuestro servidor C-STORE SCP local para C-MOVE."""
    aet: str = "FASTAPI_SCP"
    port: int = 11115
    storage_dir: DirectoryPath = Path("./dicom_received")

class ClientAE(BaseModel):
    """Identidad de nuestra aplicación cuando actúa como cliente DIMSE (SCU)."""
    aet: str = "FASTAPI_CLIENT"

class DicomGatewayConfig(BaseModel):
    """Agrupa toda la configuración de comunicación DICOM DIMSE."""
    pacs_node: PACSNode = Field(default_factory=PACSNode)
    local_scp: LocalSCP = Field(default_factory=LocalSCP)
    client_ae: ClientAE = Field(default_factory=ClientAE)


# =================================================================
# --- INICIO: NUEVA SECCIÓN PARA DICOMweb (QIDO-RS, WADO-RS) ---
# Añadimos esta nueva clase para gestionar la configuración de la API web.
# =================================================================
class DicomWebServer(BaseModel):
    """Configuración del endpoint del servidor DICOMweb."""
    host: str = "localhost" # O "jupyter.arnau.scs.es" si es remoto
    port: int = 8080
    aet: str = "DCM4CHEE"

    @property
    def base_url(self) -> str:
        # La URL base para los servicios DICOMweb de dcm4chee
        return f"http://{self.host}:{self.port}/dcm4chee-arc"
# --- FIN: NUEVA SECCIÓN PARA DICOMweb ---


# --- Modelo Principal de Configuración (Ahora con ambas secciones) ---
class Settings(BaseModel):
    """El objeto de configuración principal y único."""
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    
    # Configuración para las herramientas antiguas (C-MOVE)
    gateway: DicomGatewayConfig = Field(default_factory=DicomGatewayConfig)
    
    # NUEVO: Configuración para las nuevas herramientas (DICOMweb)
    dicomweb: DicomWebServer = Field(default_factory=DicomWebServer)

# --- Instancia de Configuración Global ---
settings = Settings()

# --- Verificación de Rutas (opcional, pero buena práctica) ---
def check_and_create_dirs():
    """Asegura que los directorios necesarios existan."""
    logger_cfg = logging.getLogger(__name__)
    # Usamos la ruta del SCP que todavía es necesaria para C-MOVE
    dirs_to_create = [
        settings.gateway.local_scp.storage_dir,
    ]
    for dir_path in dirs_to_create:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger_cfg.info(f"Directorio asegurado: {dir_path}")
        except OSError as e:
            logger_cfg.error(f"Error creando el directorio {dir_path}: {e}")

# Ejecutar la comprobación al importar el módulo
check_and_create_dirs()