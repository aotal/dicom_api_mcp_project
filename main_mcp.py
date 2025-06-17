# main_mcp_pure.py
import logging
import json
import threading
import atexit
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
import httpx

# --- Importaciones de tu proyecto ---
from config import settings
import pacs_operations
import dicom_scp
from models import (
    StudyResponse, 
    SeriesResponse, 
    InstanceMetadataResponse, 
    PixelDataResponse
)
from mcp_utils import parse_lut_explanation

# --- Importaciones de librerías de IA y DICOM ---
from mcp.server.fastmcp import FastMCP
import pydicom
from pydicom.dataset import Dataset as DicomDataset
from pydicom.tag import Tag
from pydicom.datadict import tag_for_keyword, keyword_for_tag
from pydicom.multival import MultiValue

# --- 1. Configuración del Logger y Contexto ---
logging.basicConfig(level=settings.logging.level, format=settings.logging.format, force=True)
logger = logging.getLogger(__name__)

@dataclass
class DicomToolContext:
    """Clase para contener la configuración que usarán las herramientas."""
    pacs_config: Dict[str, Any]
    move_destination_aet: str

# Variables globales para el contexto y el hilo del SCP
dicom_context: Optional[DicomToolContext] = None
scp_thread: Optional[threading.Thread] = None

# --- 2. Lógica de Inicio y Apagado ---

def _initialize_server():
    """Función de arranque: inicializa el contexto y el servidor SCP."""
    global dicom_context, scp_thread
    logger.info("Inicializando servidor MCP puro...")

    dicom_context = DicomToolContext(
        pacs_config={
            "PACS_IP": settings.gateway.pacs_node.ip,
            "PACS_PORT": settings.gateway.pacs_node.port,
            "PACS_AET": settings.gateway.pacs_node.aet,
            "AE_TITLE": settings.gateway.client_ae.aet
        },
        move_destination_aet=settings.gateway.local_scp.aet
    )
    logger.info("Contexto DICOM inicializado.")

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
    logger.info(f"Hilo del servidor C-STORE SCP iniciado (AET: {settings.gateway.local_scp.aet}).")

def _shutdown_scp_server():
    """Función de apagado: detiene el servidor SCP de forma segura."""
    logger.info("Señal de apagado recibida. Deteniendo servidor SCP...")
    if hasattr(dicom_scp, 'ae_scp') and dicom_scp.ae_scp and dicom_scp.ae_scp.is_running:
        dicom_scp.ae_scp.shutdown()

    if scp_thread and scp_thread.is_alive():
        scp_thread.join(timeout=5.0)
        if not scp_thread.is_alive():
            logger.info("Hilo del servidor SCP detenido limpiamente.")
        else:
            logger.warning("El hilo del servidor SCP no finalizó a tiempo.")

# --- 3. Ejecución del Arranque y Registro de Apagado ---
_initialize_server()
atexit.register(_shutdown_scp_server)

# --- 4. Definición del Servidor y las Herramientas MCP ---
mcp = FastMCP(
    "ServidorDeHerramientasDICOM",
    description="Un servidor que expone operaciones DICOM como herramientas para agentes de IA."
)

@mcp.tool()
async def query_studies(
    patient_id: Optional[str] = None,
    study_date: Optional[str] = None,
    accession_number: Optional[str] = None,
    patient_name: Optional[str] = None,
    additional_filters: Optional[Dict[str, str]] = None
) -> str:
    """
    Busca estudios DICOM en el PACS utilizando diversos criterios de búsqueda.

    :param patient_id: (Opcional) El ID del paciente (e.g., "12345").
    :param study_date: (Opcional) La fecha del estudio (YYYYMMDD o rango YYYYMMDD-YYYYMMDD).
    :param accession_number: (Opcional) El número de acceso del estudio.
    :param patient_name: (Opcional) El nombre del paciente, permite comodines (e.g., "Doe*").
    :param additional_filters: (Opcional) Un diccionario JSON con filtros de tags DICOM adicionales.
    :return: Un string JSON con la lista de estudios encontrados.
    """
    if not dicom_context:
        return json.dumps({"error": "El contexto DICOM no está inicializado."})
    
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "STUDY"
    for kw in ["StudyInstanceUID", "PatientID", "PatientName", "StudyDate", "StudyDescription", "ModalitiesInStudy", "AccessionNumber"]:
        setattr(identifier, kw, "")
    
    if patient_id: identifier.PatientID = patient_id
    if study_date: identifier.StudyDate = study_date
    if accession_number: identifier.AccessionNumber = accession_number
    if patient_name: identifier.PatientName = patient_name
    
    if additional_filters:
        for key, value in additional_filters.items():
            try:
                tag = Tag(key) if ',' in str(key) else Tag(tag_for_keyword(str(key)))
                keyword = keyword_for_tag(tag)
                if keyword: setattr(identifier, keyword, value)
                else: identifier[tag] = value
            except Exception:
                logger.warning(f"No se pudo procesar el filtro de estudio '{key}'.")
    
    logger.info(f"Ejecutando query_studies con el identificador:\n{identifier}")
    results = await pacs_operations.perform_c_find_async(identifier, dicom_context.pacs_config, query_model_uid='S')
    response_data = [StudyResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]
    return json.dumps(response_data, indent=2)


@mcp.tool()
async def query_series(
    study_instance_uid: str,
    additional_filters: Optional[Dict[str, str]] = None
) -> str:
    """
    Busca todas las series DICOM que pertenecen a un estudio específico.

    :param study_instance_uid: El identificador único (StudyInstanceUID) del estudio a consultar. Es un campo obligatorio.
    :param additional_filters: (Opcional) Un diccionario para aplicar filtros adicionales a nivel de serie, como la modalidad (e.g., {"Modality": "MR"}).
    :return: Un string en formato JSON con la lista de las series encontradas para el estudio dado.
    """
    if not dicom_context:
        return json.dumps({"error": "El contexto DICOM no está inicializado."})
    
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "SERIES"
    identifier.StudyInstanceUID = study_instance_uid
    for kw in ["SeriesInstanceUID", "Modality", "SeriesNumber", "SeriesDescription"]:
        setattr(identifier, kw, "")
    
    if additional_filters:
        for key, value in additional_filters.items():
            try:
                tag = Tag(key) if ',' in str(key) else Tag(tag_for_keyword(str(key)))
                keyword = keyword_for_tag(tag)
                if keyword: setattr(identifier, keyword, value)
                else: identifier[tag] = value
            except Exception:
                logger.warning(f"No se pudo procesar el filtro de serie '{key}'.")
    
    logger.info(f"Ejecutando query_series con el identificador:\n{identifier}")
    results = await pacs_operations.perform_c_find_async(identifier, dicom_context.pacs_config, query_model_uid='S')
    response_data = [SeriesResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]
    return json.dumps(response_data, indent=2)

# En main_mcp_pure.py

# En main_mcp_pure.py, reemplaza la versión anterior de query_instances_dicomweb
# Necesitarás estas importaciones si no están ya al principio del fichero:
# from pydicom.tag import Tag
# from pydicom.datadict import keyword_for_tag
# from models import InstanceMetadataResponse
import httpx

@mcp.tool()
async def query_instances_dicomweb(
    study_instance_uid: str,
    series_instance_uid: str,
    attribute_set_id: str = "QC_Convencional"
) -> str:
    """
    [MODERNO/RECOMENDADO] Busca y formatea metadatos de instancias usando DICOMweb (QIDO-RS)
    y un conjunto de atributos predefinido en el PACS.

    :param study_instance_uid: El UID del estudio a consultar.
    :param series_instance_uid: El UID de la serie a consultar.
    :param attribute_set_id: El ID del 'Attribute Set' configurado en el PACS.
    :return: Un string JSON con la lista de instancias en un formato limpio y legible,
             incluyendo un diccionario 'dicom_headers' con los metadatos solicitados.
    """
    pacs_web_port = 8080
    pacs_aet = "DCM4CHEE"
    base_url = f"http://jupyter.arnau.scs.es:{pacs_web_port}/dcm4chee-arc/aets/{pacs_aet}/rs"
    url = (
        f"{base_url}/studies/{study_instance_uid}"
        f"/series/{series_instance_uid}/instances"
        f"?includefield={attribute_set_id}"
    )

    logger.info(f"Ejecutando consulta DICOMweb (QIDO-RS): {url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={"Accept": "application/dicom+json"})
            response.raise_for_status()
            raw_instances_data = response.json()

            # --- INICIO DE LA NUEVA LÓGICA DE PARSEO ---
            parsed_response_list = []
            for instance_data in raw_instances_data:
                headers = {}
                # Itera sobre cada tag (ej. "00180060") en la respuesta JSON de la instancia
                for tag_hex, tag_content in instance_data.items():
                    try:
                        # Convierte el string del tag a un objeto Tag de pydicom
                        tag_obj = Tag(f"0x{tag_hex}")
                        # Busca el nombre del tag (ej. "KVP")
                        key_to_use = keyword_for_tag(tag_obj) or tag_hex
                        
                        # Extrae el valor. El valor siempre viene en un array "Value".
                        # Tomamos el primer elemento si existe.
                        value = tag_content.get("Value", [None])[0]
                        headers[key_to_use] = value
                    except:
                        # Si algo falla (ej. tag no estándar), usa el hexadecimal
                        headers[tag_hex] = tag_content.get("Value", [None])[0]

                # Extraer los campos principales para el modelo
                sop_instance_uid = headers.pop("SOPInstanceUID", "")
                instance_number = str(headers.pop("InstanceNumber", ""))

                # Crear el objeto de respuesta con el formato limpio y consistente
                instance_response = InstanceMetadataResponse(
                    SOPInstanceUID=sop_instance_uid,
                    InstanceNumber=instance_number,
                    dicom_headers=headers
                )
                parsed_response_list.append(instance_response.model_dump())

            return json.dumps(parsed_response_list, indent=2)
            # --- FIN DE LA NUEVA LÓGICA DE PARSEO ---

    except httpx.HTTPStatusError as e:
        error_msg = f"Error del servidor PACS (HTTP {e.response.status_code}): {e.response.text}"
        return json.dumps({"error": error_msg})
    except Exception as e:
        error_msg = f"Error de conexión o inesperado al contactar el servidor DICOMweb: {e}"
        return json.dumps({"error": error_msg})

@mcp.tool()
async def move_dicom_entity_to_local_server(
    study_instance_uid: str,
    series_instance_uid: Optional[str] = None,
    sop_instance_uid: Optional[str] = None
) -> str:
    """
    Solicita al PACS que mueva un estudio, serie o instancia completa a este servidor.
    Los archivos DICOM se recibirán y guardarán localmente para su posterior análisis.

    :param study_instance_uid: El UID del estudio a mover. Obligatorio.
    :param series_instance_uid: (Opcional) El UID de la serie a mover. Si se omite, se mueve el estudio completo.
    :param sop_instance_uid: (Opcional) El UID de la instancia específica a mover. Requiere 'series_instance_uid'.
    :return: Un string JSON con el resultado de la operación C-MOVE.
    """
    if not dicom_context:
        return json.dumps({"error": "El contexto DICOM no está inicializado."})

    identifier = DicomDataset()
    identifier.StudyInstanceUID = study_instance_uid

    if sop_instance_uid:
        if not series_instance_uid:
            return json.dumps({"error": "Se requiere 'series_instance_uid' para mover una instancia específica."})
        identifier.QueryRetrieveLevel = "IMAGE"
        identifier.SeriesInstanceUID = series_instance_uid
        identifier.SOPInstanceUID = sop_instance_uid
    elif series_instance_uid:
        identifier.QueryRetrieveLevel = "SERIES"
        identifier.SeriesInstanceUID = series_instance_uid
    else:
        identifier.QueryRetrieveLevel = "STUDY"
        
    logger.info(f"Ejecutando C-MOVE para QueryLevel='{identifier.QueryRetrieveLevel}'")
    move_responses = await pacs_operations.perform_c_move_async(
        identifier, dicom_context.pacs_config, dicom_context.move_destination_aet, query_model_uid='S'
    )
    
    final_status = move_responses[-1][0] if move_responses and move_responses[-1] else None
    if final_status and hasattr(final_status, 'Status'):
        response = {
            "status_code_hex": f"0x{final_status.Status:04X}",
            "completed_suboperations": final_status.get("NumberOfCompletedSuboperations", 0),
            "failed_suboperations": final_status.get("NumberOfFailedSuboperations", 0),
            "warning_suboperations": final_status.get("NumberOfWarningSuboperations", 0)
        }
    else:
        response = {"status_code_hex": "UNKNOWN", "message": "No se recibió respuesta de estado final del PACS."}

    return json.dumps(response, indent=2)

@mcp.tool()
async def get_local_instance_pixel_data(sop_instance_uid: str) -> str:
    """
    Recupera los datos de píxeles de una imagen DICOM que ya ha sido guardada localmente.
    Útil después de una operación 'move_dicom_entity_to_local_server' exitosa.

    :param sop_instance_uid: El SOP Instance UID de la imagen a procesar.
    :return: Un string JSON con metadatos de la imagen, incluyendo forma, tipo y una vista previa del array de píxeles.
    """
    filepath = settings.gateway.local_scp.storage_dir / (sop_instance_uid + ".dcm")
    if not filepath.is_file():
        return json.dumps({"error": f"Archivo DICOM no encontrado localmente en {filepath}"})
    
    try:
        ds = pydicom.dcmread(str(filepath), force=True)
        if not hasattr(ds, 'PixelData') or ds.PixelData is None:
             return json.dumps({"error": "El objeto DICOM no contiene datos de píxeles."})
        
        pixel_array = ds.pixel_array
        preview = None
        if pixel_array.ndim >= 2 and pixel_array.size > 0:
            if pixel_array.ndim == 2:
                rows_preview, cols_preview = min(pixel_array.shape[0], 5), min(pixel_array.shape[1], 5)
                preview = pixel_array[:rows_preview, :cols_preview].tolist()
            elif pixel_array.ndim == 3:
                if ds.get("SamplesPerPixel", 1) == 1:
                    rows_preview, cols_preview = min(pixel_array.shape[1], 5), min(pixel_array.shape[2], 5)
                    preview = pixel_array[0, :rows_preview, :cols_preview].tolist()
                elif ds.get("SamplesPerPixel", 1) > 1 and pixel_array.shape[-1] == ds.SamplesPerPixel:
                    rows_preview, cols_preview = min(pixel_array.shape[0], 5), min(pixel_array.shape[1], 5)
                    preview = pixel_array[:rows_preview, :cols_preview, 0].tolist()
        
        response = PixelDataResponse(
            sop_instance_uid=sop_instance_uid, rows=ds.Rows, columns=ds.Columns,
            pixel_array_shape=pixel_array.shape, pixel_array_dtype=str(pixel_array.dtype),
            pixel_array_preview=preview, message="Pixel data accessed from local file."
        )
        return response.model_dump_json(indent=2)
        
    except Exception as e:
        logger.error(f"Error procesando archivo local {filepath}: {e}", exc_info=True)
        return json.dumps({"error": f"Error interno procesando el archivo: {str(e)}"})