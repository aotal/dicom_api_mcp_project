# main_mcp_pure.py (Modificado Incrementalmente)
import logging
import json
import threading
import atexit
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
import httpx

# --- Importaciones de tu proyecto ---
# Usamos el config.py de pydantic-settings que ya configuramos
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

# --- INICIO: NUEVA FUNCIÓN AUXILIAR DICOMweb ---
# Añadimos la función de búsqueda QIDO-RS aquí mismo para probar.
async def query_pacs_qido(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Realiza una consulta QIDO-RS (búsqueda) al PACS."""
    # Nótese que usamos la nueva configuración de settings.pacs
    qido_url = f"{settings.pacs.base_url}/aets/{settings.pacs.aet}/rs/studies"
    headers = {"Accept": "application/dicom+json"}
    logger.info(f"Ejecutando consulta QIDO-RS a: {qido_url} con params: {params}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(qido_url, params=params, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Error en la consulta QIDO-RS: {e.response.status_code} - {e.response.text}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Error de conexión durante la consulta QIDO-RS: {e}")
        return []
# --- FIN: NUEVA FUNCIÓN AUXILIAR DICOMweb ---


@dataclass
class DicomToolContext:
    """Clase para contener la configuración que usarán las herramientas."""
    pacs_config: Dict[str, Any]
    move_destination_aet: str

# El resto de la infraestructura C-MOVE se mantiene intacta por ahora
dicom_context: Optional[DicomToolContext] = None
scp_thread: Optional[threading.Thread] = None

def _initialize_server():
    """Función de arranque: inicializa el contexto y el servidor SCP."""
    global dicom_context, scp_thread
    logger.info("Inicializando servidor MCP puro...")

    # Usamos la configuración anidada del nuevo config.py
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

_initialize_server()
atexit.register(_shutdown_scp_server)

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
    Busca estudios DICOM en el PACS. [AHORA USA DICOMweb/QIDO-RS]
    """
    # --- INICIO: LÓGICA MODIFICADA ---
    logger.info(f"Ejecutando query_studies con la nueva lógica DICOMweb (QIDO-RS)")
    
    params = {"includefield": "all"}
    if patient_name:
        params["PatientName"] = f"*{patient_name}*"
    if patient_id:
        params["PatientID"] = patient_id
    if accession_number:
        params["AccessionNumber"] = accession_number
    if study_date:
        params["StudyDate"] = study_date
    if additional_filters:
        params.update(additional_filters)

    if not any([patient_id, study_date, accession_number, patient_name]):
        return json.dumps({"error": "Se requiere al menos un criterio de búsqueda."})

    results = await query_pacs_qido(params)
    
    if not results:
        return json.dumps({"error": "No se encontraron estudios para los criterios especificados."})

    # La respuesta de QIDO-RS ya es JSON, así que la devolvemos directamente.
    # Podríamos formatearla para que sea más legible si quisiéramos.
    return json.dumps(results, indent=2)
    # --- FIN: LÓGICA MODIFICADA ---


    # --- INICIO: LÓGICA ANTIGUA (C-FIND) COMENTADA ---
    # if not dicom_context:
    #     return json.dumps({"error": "El contexto DICOM no está inicializado."})
    
    # identifier = DicomDataset()
    # identifier.QueryRetrieveLevel = "STUDY"
    # for kw in ["StudyInstanceUID", "PatientID", "PatientName", "StudyDate", "StudyDescription", "ModalitiesInStudy", "AccessionNumber"]:
    #     setattr(identifier, kw, "")
    
    # if patient_id: identifier.PatientID = patient_id
    # if study_date: identifier.StudyDate = study_date
    # if accession_number: identifier.AccessionNumber = accession_number
    # if patient_name: identifier.PatientName = patient_name
    
    # if additional_filters:
    #     for key, value in additional_filters.items():
    #         try:
    #             tag = Tag(key) if ',' in str(key) else Tag(tag_for_keyword(str(key)))
    #             keyword = keyword_for_tag(tag)
    #             if keyword: setattr(identifier, keyword, value)
    #             else: identifier[tag] = value
    #         except Exception:
    #             logger.warning(f"No se pudo procesar el filtro de estudio '{key}'.")
    
    # logger.info(f"Ejecutando query_studies con el identificador:\n{identifier}")
    # results = await pacs_operations.perform_c_find_async(identifier, dicom_context.pacs_config, query_model_uid='S')
    # response_data = [StudyResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]
    # return json.dumps(response_data, indent=2)
    # --- FIN: LÓGICA ANTIGUA (C-FIND) COMENTADA ---


# ===================================================================
# EL RESTO DE LAS HERRAMIENTAS (query_series, move_dicom_entity, etc.)
# PERMANECEN EXACTAMENTE IGUALES, USANDO LA LÓGICA ANTIGUA DE C-MOVE
# ===================================================================

@mcp.tool()
async def query_series(
    study_instance_uid: str,
    additional_filters: Optional[Dict[str, str]] = None
) -> str:
    """Busca todas las series DICOM que pertenecen a un estudio específico."""
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
    
    logger.info(f"Ejecutando query_series con el identificador (C-FIND):\n{identifier}")
    results = await pacs_operations.perform_c_find_async(identifier, dicom_context.pacs_config, query_model_uid='S')
    response_data = [SeriesResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]
    return json.dumps(response_data, indent=2)

@mcp.tool()
async def query_instances_dicomweb(
    study_instance_uid: str,
    series_instance_uid: str,
    attribute_set_id: str = "QC_Convencional"
) -> str:
    """[MODERNO/RECOMENDADO] Busca y formatea metadatos de instancias usando DICOMweb (QIDO-RS)"""
    # Esta herramienta ya usaba DICOMweb, así que no necesita cambios.
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

            parsed_response_list = []
            for instance_data in raw_instances_data:
                headers = {}
                for tag_hex, tag_content in instance_data.items():
                    try:
                        tag_obj = Tag(f"0x{tag_hex}")
                        key_to_use = keyword_for_tag(tag_obj) or tag_hex
                        value = tag_content.get("Value", [None])[0]
                        headers[key_to_use] = value
                    except:
                        headers[tag_hex] = tag_content.get("Value", [None])[0]

                sop_instance_uid = headers.pop("SOPInstanceUID", "")
                instance_number = str(headers.pop("InstanceNumber", ""))

                instance_response = InstanceMetadataResponse(
                    SOPInstanceUID=sop_instance_uid,
                    InstanceNumber=instance_number,
                    dicom_headers=headers
                )
                parsed_response_list.append(instance_response.model_dump())

            return json.dumps(parsed_response_list, indent=2)

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
    """Solicita al PACS que mueva un estudio, serie o instancia completa a este servidor."""
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
    """Recupera los datos de píxeles de una imagen DICOM que ya ha sido guardada localmente."""
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