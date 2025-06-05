# config.py
import logging
from pathlib import Path
import os

# --- Base de la aplicación ---
BASE_PROJECT_DIR = Path(__file__).resolve().parent

# --- Configuración del Logger ---
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# --- Configuración de Conexión al PACS ---

# Para servicios DICOMweb (QIDO-RS, WADO-RS)
# Esta es la URL base del servicio RESTful de tu PACS.
PACS_DICOMWEB_URL = os.getenv(
    "PACS_DICOMWEB_URL", 
    "http://jupyter.arnau.scs.es:8080/dcm4chee-arc/aets/DCM4CHEE/rs"
)

# Para servicios DIMSE (C-FIND, C-MOVE, C-STORE)
PACS_AET = os.getenv("PACS_AET", "DCM4CHEE")
PACS_IP = os.getenv("PACS_IP", "jupyter.arnau.scs.es")
PACS_PORT = int(os.getenv("PACS_PORT", "11112")) # Puerto DIMSE

# --- Configuración de la Entidad de Aplicación (AE) de esta API ---

# Como SCU (Service Class User) cuando esta API inicia una conexión (C-FIND, C-MOVE)
CLIENT_AET = os.getenv("CLIENT_AET", "FASTAPI_CLIENT") 

# Como SCP (Service Class Provider) cuando esta API recibe archivos (C-STORE)
API_SCP_AET = os.getenv("API_SCP_AET", "FASTAPI_SCP")
API_SCP_PORT = int(os.getenv("API_SCP_PORT", "11115"))

# --- Configuración de Rutas Locales ---

# Directorio donde se guardan los archivos DICOM recibidos vía C-STORE
DICOM_RECEIVED_DIR = BASE_PROJECT_DIR / "received_dicom_files"

# Asegurarse de que el directorio de recepción exista al inicio
DICOM_RECEIVED_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
logger.info(f"Directorio de recepción DICOM: {DICOM_RECEIVED_DIR}")