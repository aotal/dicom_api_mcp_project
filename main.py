# main.py (VERSIÓN FINAL 3.2 - Corregido el nombre del módulo)
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, AsyncIterator

import pydicom
from fastapi import FastAPI, HTTPException, Request
from pydicom.dataset import Dataset as DicomDataset
from pydicom.tag import Tag
from pydicom.datadict import tag_for_keyword, keyword_for_tag
from pydicom.multival import MultiValue

from config import settings
import pacs_operations # <--- CORRECCIÓN DE NOMBRE
import dicom_scp
from models import (
    StudyResponse, SeriesResponse, InstanceMetadataResponse, PixelDataResponse
)
from mcp_utils import parse_lut_explanation

# --- Configuración del Logger ---
logging.basicConfig(level=settings.logging.level, format=settings.logging.format, force=True)
logger = logging.getLogger(__name__)

# --- Contexto y Ciclo de Vida ---
@dataclass
class DicomToolContext:
    pacs_config: Dict[str, Any]
    move_destination_aet: str

scp_thread: Optional[threading.Thread] = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Dict[str, DicomToolContext]]:
    global scp_thread
    logger.info("Iniciando la aplicación y el servidor DICOM C-STORE SCP...")
    
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
    
    context = DicomToolContext(
        pacs_config={
            "PACS_IP": settings.gateway.pacs_node.ip, "PACS_PORT": settings.gateway.pacs_node.port,
            "PACS_AET": settings.gateway.pacs_node.aet, "AE_TITLE": settings.gateway.client_ae.aet
        },
        move_destination_aet=settings.gateway.local_scp.aet
    )
    
    try:
        yield {"dicom_context": context}
    finally:
        logger.info("Deteniendo la aplicación...")
        if hasattr(dicom_scp, 'ae_scp') and dicom_scp.ae_scp and dicom_scp.ae_scp.is_running:
            logger.info("Solicitando apagado del servidor SCP...")
            dicom_scp.ae_scp.shutdown()
        
        if scp_thread and scp_thread.is_alive():
            logger.info("Esperando que el hilo del SCP termine...")
            scp_thread.join(timeout=10.0)
            if scp_thread.is_alive():
                logger.warning("Advertencia: El hilo del servidor SCP no terminó limpiamente.")
        logger.info("Apagado del servidor completado.")

mcp = FastAPI(
    title="Servidor de Herramientas DICOM para Agentes de IA",
    version="3.2.0",
    description="Una API que expone operaciones DICOM como herramientas para ser consumidas por agentes inteligentes.",
    lifespan=lifespan
)


# --- Definición de Herramientas ---

@mcp.post("/tools/query_studies", response_model=List[StudyResponse], summary="Busca estudios en el PACS.")
async def query_studies(
    request: Request, patient_id: Optional[str] = None, study_date: Optional[str] = None,
    accession_number: Optional[str] = None, patient_name: Optional[str] = None,
    additional_filters: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    """Realiza una consulta C-FIND a nivel de ESTUDIO en el PACS."""
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
                logger.warning(f"No se pudo procesar el filtro de estudio '{key}'. Es probable que no sea un tag DICOM válido.")

    logger.info(f"Ejecutando query_studies con el identificador:\n{identifier}")
    pacs_config = request.state.dicom_context.pacs_config
    results = await pacs_operations.perform_c_find_async(identifier, pacs_config, query_model_uid='S')
    return [StudyResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]


@mcp.post("/tools/query_series", response_model=List[SeriesResponse], summary="Busca series dentro de un estudio.")
async def query_series(
    request: Request, study_instance_uid: str, additional_filters: Optional[Dict[str, str]] = None
) -> List[Dict[str, Any]]:
    """Busca series dentro de un estudio."""
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "SERIES"
    identifier.StudyInstanceUID = study_instance_uid
    for kw in ["SeriesInstanceUID", "Modality", "SeriesNumber", "SeriesDescription", "KVP"]:
        setattr(identifier, kw, "")

    if additional_filters:
        for key, value in additional_filters.items():
            try:
                tag = Tag(key) if ',' in str(key) else Tag(tag_for_keyword(str(key)))
                keyword = keyword_for_tag(tag)
                if keyword: setattr(identifier, keyword, value)
                else: identifier[tag] = value
            except Exception:
                logger.warning(f"No se pudo procesar el filtro de serie '{key}'. Es probable que no sea un tag DICOM válido.")
                
    logger.info(f"Ejecutando query_series con el identificador:\n{identifier}")
    pacs_config = request.state.dicom_context.pacs_config
    results = await pacs_operations.perform_c_find_async(identifier, pacs_config, query_model_uid='S')
    return [SeriesResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]


@mcp.post("/tools/query_instances", response_model=List[InstanceMetadataResponse], summary="Busca metadatos de instancias en una serie.")
async def query_instances(
    request: Request, study_instance_uid: str, series_instance_uid: str, fields_to_retrieve: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Busca metadatos de instancias en una serie."""
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "IMAGE"
    identifier.StudyInstanceUID = study_instance_uid
    identifier.SeriesInstanceUID = series_instance_uid
    identifier.SOPInstanceUID = ""
    identifier.InstanceNumber = ""

    requested_tags_for_response: Dict[str, Tag] = {}
    if fields_to_retrieve:
        for field_str in set(fields_to_retrieve):
            try:
                tag_from_field = Tag(tag_for_keyword(field_str)) if ',' not in field_str else Tag(field_str)
                requested_tags_for_response[str(tag_from_field)] = tag_from_field
                keyword = keyword_for_tag(tag_from_field)
                if keyword and not hasattr(identifier, keyword):
                    setattr(identifier, keyword, "")
            except Exception as e:
                logger.warning(f"No se pudo procesar el campo a recuperar '{field_str}': {e}")

    logger.info(f"Ejecutando query_instances con el identificador:\n{identifier}")
    pacs_config = request.state.dicom_context.pacs_config
    results = await pacs_operations.perform_c_find_async(identifier, pacs_config, query_model_uid='S')
    
    response_list: List[Dict] = []
    for res_ds in results:
        headers: Dict[str, Any] = {}
        tags_to_populate = requested_tags_for_response or {str(elem.tag): elem.tag for elem in res_ds}
        for tag_obj in tags_to_populate.values():
            if tag_obj in res_ds:
                element = res_ds[tag_obj]
                key_to_use = element.keyword or str(element.tag)
                if element.VR == 'SQ':
                    value_to_store = [
                        {(item_element.keyword or str(item_element.tag)): (parse_lut_explanation(item_element.value).model_dump() if item_element.tag == Tag(0x0028,0x3003) else (str(item_element.value) if item_element.value is not None else None)) for item_element in item_dataset}
                        for item_dataset in element.value
                    ]
                elif isinstance(element.value, MultiValue): value_to_store = [str(v) for v in element.value]
                else: value_to_store = str(element.value) if element.value is not None else ""
                headers[key_to_use] = value_to_store
        
        response_list.append(InstanceMetadataResponse(
            SOPInstanceUID=res_ds.get("SOPInstanceUID", ""),
            InstanceNumber=str(res_ds.get("InstanceNumber", "")),
            dicom_headers=headers
        ).model_dump())
    return response_list


@mcp.post("/tools/move_dicom_entity_to_local_server", summary="Mueve un estudio, serie o instancia al servidor local.")
async def move_dicom_entity_to_local_server(
    request: Request, study_instance_uid: str, series_instance_uid: Optional[str] = None, sop_instance_uid: Optional[str] = None
) -> Dict[str, Any]:
    """Inicia una operación DICOM C-MOVE para recuperar datos al servidor local."""
    identifier = DicomDataset()
    identifier.StudyInstanceUID = study_instance_uid

    if sop_instance_uid:
        if not series_instance_uid: raise HTTPException(status_code=400, detail="SeriesInstanceUID es requerido.")
        identifier.QueryRetrieveLevel = "IMAGE"
        identifier.SeriesInstanceUID = series_instance_uid
        identifier.SOPInstanceUID = sop_instance_uid
    elif series_instance_uid:
        identifier.QueryRetrieveLevel = "SERIES"
        identifier.SeriesInstanceUID = series_instance_uid
    else: identifier.QueryRetrieveLevel = "STUDY"
        
    logger.info(f"Ejecutando move_dicom_entity_to_local_server para QueryLevel='{identifier.QueryRetrieveLevel}'")
    context = request.state.dicom_context
    move_responses = await pacs_operations.perform_c_move_async(
        identifier, context.pacs_config, context.move_destination_aet, query_model_uid='S'
    )
    
    final_status = move_responses[-1][0] if move_responses and move_responses[-1] else None
    if final_status and hasattr(final_status, 'Status'):
        return {
            "status": f"0x{final_status.Status:04X}",
            "completed_suboperations": final_status.get("NumberOfCompletedSuboperations", 0),
            "failed_suboperations": final_status.get("NumberOfFailedSuboperations", 0),
            "warning_suboperations": final_status.get("NumberOfWarningSuboperations", 0)
        }
    return {"status": "UNKNOWN", "message": "No se recibió una respuesta de estado final del PACS."}


@mcp.post("/tools/get_local_instance_pixel_data", response_model=PixelDataResponse, summary="Obtiene datos de píxeles de una instancia ya recibida.")
async def get_local_instance_pixel_data(
    request: Request, sop_instance_uid: str
) -> Dict[str, Any]:
    """Recupera metadatos de píxeles de un archivo DICOM almacenado localmente."""
    filepath = settings.gateway.local_scp.storage_dir / (sop_instance_uid + ".dcm")
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail=f"Archivo DICOM no encontrado localmente en {filepath}")
    
    try:
        ds = pydicom.dcmread(str(filepath), force=True)
        if not hasattr(ds, 'PixelData') or ds.PixelData is None:
             raise HTTPException(status_code=404, detail="El objeto DICOM no contiene datos de píxeles.")
        
        pixel_array = ds.pixel_array
        logger.info(f"Array de píxeles obtenido del archivo {filepath}: forma={pixel_array.shape}, tipo={pixel_array.dtype}")
        
        # --- LÓGICA DE PREVIEW RESTAURADA Y COMPLETA ---
        preview = None
        if pixel_array.ndim >= 2 and pixel_array.size > 0:
            if pixel_array.ndim == 2:  # Imagen 2D (monocromo)
                rows_preview = min(pixel_array.shape[0], 5)
                cols_preview = min(pixel_array.shape[1], 5)
                preview = pixel_array[:rows_preview, :cols_preview].tolist()
            elif pixel_array.ndim == 3:  # Imagen 3D (multiframe o color)
                # Si es monocromo multiframe (ej. (frames, filas, cols))
                if ds.get("SamplesPerPixel", 1) == 1:
                    rows_preview = min(pixel_array.shape[1], 5)
                    cols_preview = min(pixel_array.shape[2], 5)
                    # Preview del primer frame
                    preview = pixel_array[0, :rows_preview, :cols_preview].tolist()
                # Si es color (ej. (filas, cols, samples))
                elif ds.get("SamplesPerPixel", 1) > 1 and pixel_array.shape[-1] == ds.SamplesPerPixel:
                    rows_preview = min(pixel_array.shape[0], 5)
                    cols_preview = min(pixel_array.shape[1], 5)
                    # Preview del primer canal (ej. Rojo)
                    preview = pixel_array[:rows_preview, :cols_preview, 0].tolist()
        
        return PixelDataResponse(
            sop_instance_uid=sop_instance_uid, rows=ds.Rows, columns=ds.Columns,
            pixel_array_shape=list(pixel_array.shape), pixel_array_dtype=str(pixel_array.dtype),
            pixel_array_preview=preview, message="Pixel data accessed from locally stored file."
        ).model_dump()
    except Exception as e:
        logger.error(f"Error procesando el archivo DICOM local {filepath}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno procesando el archivo: {e}")