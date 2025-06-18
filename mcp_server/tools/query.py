# Tools for querying DICOM data
import json
import logging
from typing import Optional, Dict, Any, List
import httpx

from pydicom.dataset import Dataset as DicomDataset
from pydicom.tag import Tag
from pydicom.datadict import tag_for_keyword, keyword_for_tag

from models import StudyResponse, SeriesResponse, InstanceMetadataResponse
import pacs_operations
from mcp_server.context import dicom_context

logger = logging.getLogger(__name__)

# Copied and adapted from main_mcp.py
async def query_studies(
    patient_id: Optional[str] = None,
    study_date: Optional[str] = None,
    accession_number: Optional[str] = None,
    patient_name: Optional[str] = None,
    additional_filters: Optional[Dict[str, str]] = None
) -> str:
    """Busca estudios DICOM en el PACS utilizando diversos criterios de búsqueda."""
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
    logger.info(f"Ejecutando query_series con el identificador:\n{identifier}")
    results = await pacs_operations.perform_c_find_async(identifier, dicom_context.pacs_config, query_model_uid='S')
    response_data = [SeriesResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]
    return json.dumps(response_data, indent=2)

async def query_instances_dicomweb(
    study_instance_uid: str,
    series_instance_uid: str,
    attribute_set_id: str = "QC_Convencional"
) -> str:
    """[MODERNO/RECOMENDADO] Busca y formatea metadatos de instancias usando DICOMweb (QIDO-RS)"""
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
