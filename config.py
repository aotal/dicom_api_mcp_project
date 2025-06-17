# config.py
"""
Fichero de Configuración Central basado en Pydantic.

Separa la configuración en dos contextos principales:
1. DicomGatewayConfig: Parámetros para la comunicación con el PACS y el servidor SCP.
   Utilizado por las herramientas del agente de IA.
2. LocalProcessingConfig: Parámetros para flujos de trabajo de procesamiento de archivos locales
   (linealización, clasificación, etc.). Reservado para futuras herramientas.
"""
import logging
from pathlib import Path
from pydantic import BaseModel, DirectoryPath, FilePath, Field
from typing import Dict, Optional

# --- Modelos de Configuración con Pydantic ---

class LoggingSettings(BaseModel):
    level: int = logging.INFO
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

class PACSNode(BaseModel):
    """Configuración del nodo PACS remoto al que nos conectamos."""
    ip: str = "jupyter.arnau.scs.es" # dcm4chee en Docker usa localhost si se exponen puertos
    port: int = 11112
    aet: str = "DCM4CHEE"

class LocalSCP(BaseModel):
    """Configuración de nuestro servidor C-STORE SCP local."""
    aet: str = "FASTAPI_SCP"
    port: int = 11115
    storage_dir: DirectoryPath = Path("./dicom_received")

class ClientAE(BaseModel):
    """Identidad de nuestra aplicación cuando actúa como cliente (SCU)."""
    aet: str = "FASTAPI_CLIENT"

class DicomGatewayConfig(BaseModel):
    """Agrupa toda la configuración de comunicación DICOM."""
    pacs_node: PACSNode = Field(default_factory=PACSNode)
    local_scp: LocalSCP = Field(default_factory=LocalSCP)
    client_ae: ClientAE = Field(default_factory=ClientAE)

# --- Modelos para la Configuración de Procesamiento Local (reservado) ---

class PhysicalLinealization(BaseModel):
    """Parámetros para la linealización física."""
    enabled: bool = False
    csv_path: Optional[FilePath] = Path("data/linearizacion.csv")
    default_rqa_type: str = "RQA5"
    rqa_factors: Dict[str, float] = {
        "RQA3": 0.000085,
        "RQA5": 0.000123,
        "RQA7": 0.000250,
        "RQA9": 0.000456,
    }
    private_creator_id: str = "MIAPP_LINFO_V1"

class LocalProcessingConfig(BaseModel):
    """Agrupa configuraciones para el procesamiento de archivos locales."""
    base_project_dir: DirectoryPath = Path(__file__).resolve().parent
    input_dir: DirectoryPath = Path("input_dicom_files")
    output_dir: DirectoryPath = Path("output_processed_dicom")
    
    kerma_lut_csv_path: Optional[FilePath] = Path("data/linearizacion.csv")
    kerma_scaling_factor: float = 100.0

    linealization: PhysicalLinealization = Field(default_factory=PhysicalLinealization)
    
    classification_tag: str = "ImageComments"
    classification_prefix: str = "QC_Class:"

# --- Modelo Principal de Configuración ---

class Settings(BaseModel):
    """El objeto de configuración principal y único."""
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    gateway: DicomGatewayConfig = Field(default_factory=DicomGatewayConfig)
    processing: LocalProcessingConfig = Field(default_factory=LocalProcessingConfig)

# --- Instancia de Configuración Global ---
# Aquí se cargan y validan todas las configuraciones al iniciar la aplicación.
settings = Settings()

# --- Verificación de Rutas (opcional, pero buena práctica) ---
def check_and_create_dirs():
    """Asegura que los directorios necesarios existan."""
    logger = logging.getLogger(__name__)
    dirs_to_create = [
        settings.gateway.local_scp.storage_dir,
        settings.processing.input_dir,
        settings.processing.output_dir
    ]
    for dir_path in dirs_to_create:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directorio asegurado: {dir_path}")
        except OSError as e:
            logger.error(f"Error creando el directorio {dir_path}: {e}")

# Ejecutar la comprobación al importar el módulo
check_and_create_dirs()