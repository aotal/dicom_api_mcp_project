# api_main.py
import logging
import re 
import io
# import httpx # No es necesario para C-FIND/C-MOVE, sí para WADO
import os
import json # <--- AÑADIDO PARA PARSEAR FILTROS JSON
from fastapi import FastAPI, HTTPException, Query
from typing import Any, List, Optional, Dict, Tuple
import threading
from contextlib import asynccontextmanager

from models import (
    StudyResponse, 
    SeriesResponse, 
    InstanceMetadataResponse, 
    LUTExplanationModel,
    PixelDataResponse,
    MoveRequest 
)

import pydicom
from pydicom.tag import Tag
from pydicom.dataset import Dataset as DicomDataset
from pydicom.datadict import dictionary_VR, tag_for_keyword, keyword_for_tag #Añadido keyword_for_tag
from pydicom.dataelem import DataElement
from pydicom.multival import MultiValue

import pacs_operations
import config
import dicom_scp

# --- Configuración del Logger ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

# --- Lifespan Manager para iniciar/detener el SCP ---
scp_thread: Optional[threading.Thread] = None

@asynccontextmanager
async def lifespan(app: FastAPI): # Renombrado el parámetro para claridad
    global scp_thread
    logger.info("Iniciando aplicación FastAPI y servidor DICOM C-STORE SCP...")
    print("[FastAPI App] Iniciando aplicación y servidor DICOM C-STORE SCP...")
    
    scp_thread = threading.Thread(target=dicom_scp.start_scp_server, daemon=True)
    scp_thread.start()
    
    yield 

    logger.info("Deteniendo aplicación FastAPI...")
    print("[FastAPI App] Deteniendo aplicación FastAPI...")
    
    if hasattr(dicom_scp, 'ae_scp') and dicom_scp.ae_scp and dicom_scp.ae_scp.is_running:
         print("[FastAPI App] Solicitando apagado del servidor SCP...")
         dicom_scp.ae_scp.shutdown() 
    
    if scp_thread and scp_thread.is_alive():
        print("[FastAPI App] Esperando que el hilo del SCP termine...")
        scp_thread.join(timeout=10.0) 
        if scp_thread.is_alive():
             logger.warning("[FastAPI App] Advertencia: El hilo del servidor SCP no terminó limpiamente.")
    print("[FastAPI App] Apagado completado.")


app = FastAPI(
    title="API de Consultas PACS DICOM (con C-STORE SCP y Filtros Dinámicos)", 
    version="1.2.0", 
    lifespan=lifespan
)

# --- Funciones Auxiliares ---
def _parse_range_to_floats(range_str: Optional[str]) -> Optional[Tuple[float, float]]:
    if not range_str: return None
    try:
        parts = range_str.strip().split('-')
        if len(parts) == 1: val = float(parts[0].strip()); return (val, val) 
        elif len(parts) == 2: return (float(parts[0].strip()), float(parts[1].strip()))
        else: logger.warning(f"Formato de rango inesperado: '{range_str}'."); return None
    except ValueError: logger.warning(f"Error al convertir valores del rango '{range_str}' a flotantes."); return None

def parse_lut_explanation(explanation_str_raw: Optional[Any]) -> LUTExplanationModel:
    if explanation_str_raw is None: return LUTExplanationModel(FullText=None)
    text = str(explanation_str_raw)
    explanation_part = text 
    in_calib_range_parsed: Optional[Tuple[float, float]] = None
    out_lut_range_parsed: Optional[Tuple[float, float]] = None
    regex_pattern = r"^(.*?)(?:InCalibRange:\s*([0-9\.\-]+))?\s*(?:OutLUTRange:\s*([0-9\.\-]+))?$"
    match = re.fullmatch(regex_pattern, text.strip())
    if match:
        explanation_part = match.group(1).strip() if match.group(1) else ""
        in_calib_range_str = match.group(2); out_lut_range_str = match.group(3)
        if in_calib_range_str: in_calib_range_parsed = _parse_range_to_floats(in_calib_range_str.strip())
        if out_lut_range_str: out_lut_range_parsed = _parse_range_to_floats(out_lut_range_str.strip())
        if in_calib_range_parsed is None and "InCalibRange:" in explanation_part:
            temp_parts = explanation_part.split("InCalibRange:", 1); explanation_part = temp_parts[0].strip()
            if len(temp_parts) > 1: temp_in_calib_parts = temp_parts[1].split("OutLUTRange:", 1); in_calib_range_parsed = _parse_range_to_floats(temp_in_calib_parts[0].strip())
        if out_lut_range_parsed is None and "OutLUTRange:" in explanation_part:
            temp_parts = explanation_part.split("OutLUTRange:", 1)
            if "InCalibRange:" not in temp_parts[0]: explanation_part = temp_parts[0].strip()
            if len(temp_parts) > 1: out_lut_range_parsed = _parse_range_to_floats(temp_parts[1].strip())
    else: logger.warning(f"Regex principal no coincidió para LUTExplanation: '{text}'."); explanation_part = text
    return LUTExplanationModel(FullText=text, Explanation=explanation_part if explanation_part else None, InCalibRange=in_calib_range_parsed, OutLUTRange=out_lut_range_parsed)

# --- Endpoints ---
@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Consultas PACS DICOM"}

@app.get("/studies", response_model=List[StudyResponse])
async def find_studies_endpoint(
    PatientID_param: Optional[str] = Query(None, alias="PatientID", description="Patient ID to filter by."),
    StudyDate_param: Optional[str] = Query(None, alias="StudyDate", description="Study Date (YYYYMMDD or YYYYMMDD-YYYYMMDD range)."),
    AccessionNumber_param: Optional[str] = Query(None, alias="AccessionNumber", description="Accession Number."),
    ModalitiesInStudy_param: Optional[str] = Query(None, alias="ModalitiesInStudy", description="Modalities in Study (e.g., CT, MR)."),
    PatientName_param: Optional[str] = Query(None, alias="PatientName", description="Patient's Name for filtering."),
    filters: Optional[str] = Query(None, description="JSON string for DICOM tag filtering, e.g., '{\"PatientName\":\"DOE^*J*\", \"(0008,0060)\":\"CT\"}'")
):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "STUDY"

    # Campos que siempre queremos que se devuelvan con valor vacío si no se usan como filtro
    fields_to_return = {
        "StudyInstanceUID": "", "PatientID": "", "PatientName": "", "StudyDate": "",
        "StudyDescription": "", "ModalitiesInStudy": "", "AccessionNumber": ""
    }
    for kw, val in fields_to_return.items():
        setattr(identifier, kw, val)

    # Aplicar parámetros de consulta específicos (tienen precedencia o se combinan)
    if PatientID_param is not None: identifier.PatientID = PatientID_param
    if StudyDate_param is not None: identifier.StudyDate = StudyDate_param
    if AccessionNumber_param is not None: identifier.AccessionNumber = AccessionNumber_param
    if ModalitiesInStudy_param is not None: identifier.ModalitiesInStudy = ModalitiesInStudy_param
    if PatientName_param is not None: identifier.PatientName = PatientName_param
    
    # Aplicar filtros genéricos del JSON
    if filters:
        try:
            filter_dict = json.loads(filters)
            for key, value in filter_dict.items():
                tag_obj: Optional[Tag] = None
                try:
                    if ',' in key: 
                        group_str, elem_str = key.strip("() ").split(',') # Limpiar espacios y paréntesis
                        tag_obj = Tag(int(group_str, 16), int(elem_str, 16))
                    else: 
                        tag_val_from_kw = tag_for_keyword(key)
                        if tag_val_from_kw:
                            tag_obj = Tag(tag_val_from_kw)
                        else:
                            logger.warning(f"Keyword DICOM '{key}' en 'filters' no reconocido. Omitiendo.")
                            continue
                    
                    # Usar pydicom para manejar la asignación y el VR si es posible
                    setattr(identifier, keyword_for_tag(tag_obj) if keyword_for_tag(tag_obj) else str(tag_obj), value)
                    print(f"[find_studies_endpoint] Aplicando filtro: Tag {tag_obj} ({keyword_for_tag(tag_obj) or key}) = '{value}'")

                except ValueError:
                    logger.warning(f"Formato de tag inválido '{key}' en 'filters'. Omitiendo.")
                except Exception as e_filter_tag:
                    logger.error(f"Error procesando tag de filtro '{key}': {e_filter_tag}", exc_info=True)
        
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Parámetro 'filters' con JSON inválido.")
    
    pacs_config_dict = {
        "PACS_IP": config.PACS_IP, "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET, "AE_TITLE": config.CLIENT_AET
    }
    try:
        results_datasets = await pacs_operations.perform_c_find_async(
            identifier, pacs_config_dict, query_model_uid='S'
        )
        response_studies: List[StudyResponse] = []
        for res_ds in results_datasets:
            response_studies.append(StudyResponse(
                StudyInstanceUID=res_ds.get("StudyInstanceUID", ""),
                PatientID=res_ds.get("PatientID", ""),
                PatientName=str(res_ds.get("PatientName", "")), 
                StudyDate=res_ds.get("StudyDate", ""),
                StudyDescription=res_ds.get("StudyDescription", ""),
                ModalitiesInStudy=res_ds.get("ModalitiesInStudy", ""),
                AccessionNumber=res_ds.get("AccessionNumber", "")
            ))
        return response_studies
    except Exception as e:
        logger.error(f"Error en C-FIND de estudios: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during PACS query: {str(e)}")

@app.get("/studies/{study_instance_uid}/series", response_model=List[SeriesResponse])
async def find_series_in_study(
    study_instance_uid: str,
    # Aquí también podrías añadir el parámetro 'filters'
    filters: Optional[str] = Query(None, description="JSON string for DICOM tag filtering, e.g., '{\"Modality\":\"CT\", \"(0018,0015)\":\"CHEST\"}'")
):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "SERIES"
    identifier.StudyInstanceUID = study_instance_uid # Requerido para nivel SERIES
    
    # Campos que siempre queremos que se devuelvan con valor vacío
    identifier.SeriesInstanceUID = ""
    identifier.Modality = ""
    identifier.SeriesNumber = "" 
    identifier.SeriesDescription = ""

    # Aplicar filtros genéricos del JSON (lógica similar a find_studies_endpoint)
    if filters:
        try:
            filter_dict = json.loads(filters)
            for key, value in filter_dict.items():
                tag_obj: Optional[Tag] = None
                try:
                    if ',' in key: 
                        group_str, elem_str = key.strip("() ").split(',')
                        tag_obj = Tag(int(group_str, 16), int(elem_str, 16))
                    else: 
                        tag_val_from_kw = tag_for_keyword(key)
                        if tag_val_from_kw:
                            tag_obj = Tag(tag_val_from_kw)
                        else:
                            logger.warning(f"Keyword DICOM '{key}' en 'filters' para series no reconocido. Omitiendo.")
                            continue
                    setattr(identifier, keyword_for_tag(tag_obj) if keyword_for_tag(tag_obj) else str(tag_obj), value)
                    print(f"[find_series_in_study] Aplicando filtro: Tag {tag_obj} ({keyword_for_tag(tag_obj) or key}) = '{value}'")
                except ValueError:
                    logger.warning(f"Formato de tag inválido '{key}' en 'filters' para series. Omitiendo.")
                except Exception as e_filter_tag:
                    logger.error(f"Error procesando tag de filtro para series '{key}': {e_filter_tag}", exc_info=True)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Parámetro 'filters' con JSON inválido para series.")

    pacs_config_dict = {
        "PACS_IP": config.PACS_IP, "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET, "AE_TITLE": config.CLIENT_AET
    }
    try:
        results_datasets = await pacs_operations.perform_c_find_async(
            identifier, pacs_config_dict, query_model_uid='S' 
        )
        response_list: List[SeriesResponse] = []
        for res_ds in results_datasets:
            series_number_raw = res_ds.get("SeriesNumber")
            series_number_for_pydantic: Optional[str] = None
            if series_number_raw is not None:
                try: series_number_for_pydantic = str(int(series_number_raw))
                except (ValueError, TypeError): series_number_for_pydantic = str(series_number_raw)
            response_list.append(SeriesResponse(
                StudyInstanceUID=res_ds.get("StudyInstanceUID", study_instance_uid),
                SeriesInstanceUID=res_ds.get("SeriesInstanceUID", ""),
                Modality=res_ds.get("Modality", ""),
                SeriesNumber=series_number_for_pydantic,
                SeriesDescription=res_ds.get("SeriesDescription", ""),
            ))
        return response_list
    except Exception as e:
        logger.error(f"Error en C-FIND de series: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al consultar series: {str(e)}")

@app.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances", response_model=List[InstanceMetadataResponse])
async def find_instances_in_series(
    study_instance_uid: str,
    series_instance_uid: str,
    fields: Optional[List[str]] = Query(None, description="Lista de keywords DICOM o (gggg,eeee) a recuperar. E.g., 'PatientName' o '0010,0020'."),
    filters: Optional[str] = Query(None, description="JSON string for DICOM tag filtering, e.g., '{\"InstanceNumber\":\"1\", \"(0020,4000)\":\"FDT\"}'")
):
    print(f"[find_instances_in_series] Recibido fields: {fields}")
    print(f"[find_instances_in_series] Recibido filters: {filters}")

    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "IMAGE"
    identifier.StudyInstanceUID = study_instance_uid
    identifier.SeriesInstanceUID = series_instance_uid
    
    # Campos que siempre queremos que se devuelvan si 'fields' no se especifica,
    # o además de los especificados en 'fields'
    identifier.SOPInstanceUID = ""
    identifier.InstanceNumber = ""

    # Aplicar filtros genéricos del JSON
    if filters:
        try:
            filter_dict = json.loads(filters)
            for key, value in filter_dict.items():
                tag_obj: Optional[Tag] = None
                try:
                    if ',' in key: 
                        group_str, elem_str = key.strip("() ").split(',')
                        tag_obj = Tag(int(group_str, 16), int(elem_str, 16))
                    else: 
                        tag_val_from_kw = tag_for_keyword(key)
                        if tag_val_from_kw:
                            tag_obj = Tag(tag_val_from_kw)
                        else:
                            logger.warning(f"Keyword DICOM '{key}' en 'filters' para instancias no reconocido. Omitiendo.")
                            continue
                    setattr(identifier, keyword_for_tag(tag_obj) if keyword_for_tag(tag_obj) else str(tag_obj), value)
                    print(f"[find_instances_in_series] Aplicando filtro: Tag {tag_obj} ({keyword_for_tag(tag_obj) or key}) = '{value}'")
                except ValueError:
                    logger.warning(f"Formato de tag inválido '{key}' en 'filters' para instancias. Omitiendo.")
                except Exception as e_filter_tag:
                    logger.error(f"Error procesando tag de filtro para instancias '{key}': {e_filter_tag}", exc_info=True)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Parámetro 'filters' con JSON inválido para instancias.")

    requested_tags_for_response: Dict[str, Tag] = {}
    if fields:
        for field_str in fields:
            # ... (lógica existente para procesar 'fields' y poblar 'requested_tags_for_response' y 'identifier' con valor vacío para retorno)
            tag_to_add: Optional[Tag] = None
            try:
                if ',' in field_str:
                    group, elem = field_str.split(',')
                    tag_to_add = Tag(int(group, 16), int(elem, 16))
                else:
                    tag_val_from_keyword = tag_for_keyword(field_str)
                    if tag_val_from_keyword: tag_to_add = Tag(tag_val_from_keyword)
                    else: logger.warning(f"Keyword DICOM '{field_str}' en 'fields' no reconocida. Omitiendo."); continue
                if tag_to_add:
                    if tag_to_add not in identifier: # Solo añadir si no está ya como filtro
                        identifier[tag_to_add] = "" # Para solicitar el retorno
                    requested_tags_for_response[str(tag_to_add)] = tag_to_add
            except ValueError as ve: logger.warning(f"Formato de tag DICOM inválido para field '{field_str}': {ve}. Omitiendo.")
            except Exception as e_tag: logger.warning(f"Error procesando field '{field_str}' como tag DICOM: {e_tag}. Omitiendo.")
    
    print(f"[find_instances_in_series] Identificador C-FIND final para instancias:\n{identifier}")
    print(f"[find_instances_in_series] Tags solicitados para respuesta (requested_tags_for_response): {requested_tags_for_response}")
    
    pacs_config_dict = {
        "PACS_IP": config.PACS_IP, "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET, "AE_TITLE": config.CLIENT_AET
    }
    try:
        results_datasets = await pacs_operations.perform_c_find_async(
            identifier, pacs_config_dict, query_model_uid='S'
        )
        response_list: List[InstanceMetadataResponse] = []
        for res_ds in results_datasets:
            headers: Dict[str, Any] = {}
            sop_instance_uid_val = res_ds.get("SOPInstanceUID", "")
            instance_number_raw = res_ds.get("InstanceNumber")
            instance_number_val: Optional[str] = None
            if instance_number_raw is not None:
                try: instance_number_val = str(int(instance_number_raw))
                except (ValueError, TypeError): instance_number_val = str(instance_number_raw)
            
            # Si 'fields' no se especificó, 'requested_tags_for_response' estará vacío.
            # En ese caso, podríamos querer devolver un conjunto mínimo o todos los tags devueltos.
            # Por ahora, si está vacío, 'headers' quedará vacío.
            # Si 'fields' SÍ se especificó, se llenan los headers como antes.
            tags_to_process_in_response = requested_tags_for_response
            if not fields: # Si no se pidieron campos específicos, devolver todos los que vinieron
                tags_to_process_in_response = {str(tag_val): tag_val for tag_val in res_ds}


            for tag_key_str, tag_obj in tags_to_process_in_response.items():
                if tag_obj in res_ds:
                    element = res_ds[tag_obj]
                    key_to_use = element.keyword if element.keyword and isinstance(element.keyword, str) else keyword_for_tag(tag_obj) or str(tag_obj)
                    value_to_store: Any = None
                    if element.VR == 'SQ': 
                        sequence_items = []
                        if isinstance(element.value, pydicom.sequence.Sequence):
                            for item_dataset in element.value: 
                                item_data: Dict[str, Any] = {}
                                for item_element in item_dataset: 
                                    item_key_in_seq = item_element.keyword if item_element.keyword and isinstance(item_element.keyword, str) else str(item_element.tag)
                                    item_val_in_seq: Any = None
                                    if item_element.tag == Tag(0x0028, 0x3006): 
                                        item_data[item_key_in_seq] = f"Binary LUT data (length {len(item_element.value) if item_element.value is not None else 0}), not included"
                                        continue
                                    if item_element.tag == Tag(0x0028,0x3003): 
                                        item_val_in_seq = parse_lut_explanation(item_element.value)
                                    elif item_element.VR == 'PN': item_val_in_seq = str(item_element.value) if item_element.value is not None else ""
                                    elif item_element.VR in ['DA', 'DT', 'TM']: item_val_in_seq = str(item_element.value) if item_element.value is not None else ""
                                    elif item_element.VR == 'IS':
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [str(int(v)) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = str(int(item_element.value))
                                        else: item_val_in_seq = None
                                    elif item_element.VR == 'DS':
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [str(float(v)) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = str(float(item_element.value))
                                        else: item_val_in_seq = None
                                    elif item_element.VR in ['US', 'SS', 'SL', 'UL']:
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [int(v) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = int(item_element.value)
                                        else: item_val_in_seq = None
                                    elif item_element.VR in ['FL', 'FD']:
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [float(v) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = float(item_element.value)
                                        else: item_val_in_seq = None
                                    elif item_element.value is None: item_val_in_seq = None
                                    else: item_val_in_seq = str(item_element.value)
                                    item_data[item_key_in_seq] = item_val_in_seq
                                sequence_items.append(item_data)
                        value_to_store = sequence_items
                    elif element.VR == 'PN': value_to_store = str(element.value) if element.value is not None else ""
                    elif element.VR in ['DA', 'DT', 'TM']: value_to_store = str(element.value) if element.value is not None else ""
                    elif element.VR == 'IS':
                        if isinstance(element.value, MultiValue): value_to_store = [str(int(v)) for v in element.value]
                        elif element.value is not None: value_to_store = str(int(element.value))
                        else: value_to_store = None
                    elif element.VR == 'DS':
                        if isinstance(element.value, MultiValue): value_to_store = [str(float(v)) for v in element.value]
                        elif element.value is not None: value_to_store = str(float(element.value))
                        else: value_to_store = None
                    elif element.VR in ['US', 'SS', 'SL', 'UL']:
                        if isinstance(element.value, MultiValue): value_to_store = [int(v) for v in element.value]
                        elif element.value is not None: value_to_store = int(element.value)
                        else: value_to_store = None
                    elif element.VR in ['FL', 'FD']:
                        if isinstance(element.value, MultiValue): value_to_store = [float(v) for v in element.value]
                        elif element.value is not None: value_to_store = float(element.value)
                        else: value_to_store = None
                    elif element.value is None: value_to_store = None
                    else: value_to_store = str(element.value)
                    headers[key_to_use] = value_to_store
                # else: # Si no se pidió explícitamente en 'fields' Y 'fields' no estaba vacío, no lo añadimos
                #     if fields: # Solo omitir si 'fields' fue especificado y este tag no estaba en él
                #          continue
                #     # Si 'fields' está vacío, y este tag_obj vino de res_ds, añadirlo
                #     # (Esta lógica se cubre con la reasignación de tags_to_process_in_response)
                #     pass
            
            response_list.append(InstanceMetadataResponse(
                SOPInstanceUID=sop_instance_uid_val,
                InstanceNumber=instance_number_val,
                dicom_headers=headers
            ))
        return response_list
    except Exception as e:
        logger.error(f"Error en C-FIND de instancias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al consultar instancias: {str(e)}")

# --- Endpoints para C-MOVE y Acceso a Píxeles Recibidos ---
@app.post("/retrieve-instance", status_code=202, summary="Solicita al PACS mover instancias a esta API")
async def retrieve_instance_via_cmove(item: MoveRequest):
    identifier = DicomDataset()
    identifier.StudyInstanceUID = item.study_instance_uid
    if item.sop_instance_uid:
        if not item.series_instance_uid:
            raise HTTPException(status_code=400, detail="SeriesInstanceUID es requerido para mover una instancia específica.")
        identifier.QueryRetrieveLevel = "IMAGE"
        identifier.SeriesInstanceUID = item.series_instance_uid
        identifier.SOPInstanceUID = item.sop_instance_uid
    elif item.series_instance_uid:
        identifier.QueryRetrieveLevel = "SERIES"
        identifier.SeriesInstanceUID = item.series_instance_uid
        identifier.SOPInstanceUID = "" 
    elif item.study_instance_uid:
        identifier.QueryRetrieveLevel = "STUDY"
        identifier.SeriesInstanceUID = "" 
        identifier.SOPInstanceUID = ""    
    else:
        raise HTTPException(status_code=400, detail="Se requiere al menos StudyInstanceUID.")

    pacs_config_dict = {
        "PACS_IP": config.PACS_IP, "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET, "AE_TITLE": config.CLIENT_AET 
    }
    move_destination = config.API_SCP_AET
    try:
        move_responses = await pacs_operations.perform_c_move_async(
            identifier, pacs_config_dict, move_destination_aet=move_destination, query_model_uid='S'
        )
        final_status_ds = move_responses[-1][0] if move_responses else None
        if final_status_ds and hasattr(final_status_ds, 'Status'):
            status_val = final_status_ds.Status
            if status_val == 0x0000:
                num_completed = final_status_ds.get("NumberOfCompletedSuboperations", 0)
                return {"message": f"Solicitud C-MOVE aceptada por el PACS. Sub-operaciones completadas (según PACS): {num_completed}."}
            else:
                logger.error(f"C-MOVE falló o tuvo advertencias. Estado final del PACS: 0x{status_val:04X}")
                raise HTTPException(status_code=500, detail=f"C-MOVE falló o tuvo advertencias. Estado final del PACS: 0x{status_val:04X}")
        else:
            logger.error("No se recibió una respuesta de estado final válida o completa del C-MOVE.")
            raise HTTPException(status_code=500, detail="Respuesta C-MOVE incompleta o no exitosa del PACS.")
    except ConnectionError as e:
        logger.error(f"Error de conexión C-MOVE: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Error de conexión al PACS para C-MOVE: {str(e)}")
    except Exception as e:
        logger.error(f"Error al solicitar C-MOVE: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor durante C-MOVE: {str(e)}")

@app.get("/retrieved-instances/{sop_instance_uid}/pixeldata", response_model=PixelDataResponse, summary="Obtiene datos de píxeles de una instancia recibida localmente")
async def get_retrieved_instance_pixeldata(sop_instance_uid: str):
    filepath = os.path.join(config.DICOM_RECEIVED_DIR, sop_instance_uid + ".dcm")
    print(f"[get_retrieved_instance_pixeldata] Buscando archivo: {filepath}")
    if not os.path.exists(filepath):
        logger.warning(f"Archivo DICOM no encontrado en el directorio de recepción: {filepath}")
        raise HTTPException(status_code=404, detail="Archivo DICOM no encontrado. Es posible que C-MOVE no haya completado, fallado, o aún no haya llegado.")
    try:
        ds = pydicom.dcmread(filepath, force=True)
        if not hasattr(ds, 'PixelData') or ds.PixelData is None:
            raise HTTPException(status_code=404, detail="El objeto DICOM no contiene datos de píxeles (PixelData) válidos.")
        pixel_array = ds.pixel_array
        logger.info(f"Array de píxeles obtenido del archivo {filepath}: forma={pixel_array.shape}, tipo={pixel_array.dtype}")
        print(f"[get_retrieved_instance_pixeldata] Array de píxeles obtenido: forma={pixel_array.shape}, tipo={pixel_array.dtype}")
        preview = None
        if pixel_array.ndim >= 2 and pixel_array.size > 0:
            rows_preview = min(pixel_array.shape[0], 5)
            cols_preview = min(pixel_array.shape[1], 5)
            if pixel_array.ndim == 2:
                preview = pixel_array[:rows_preview, :cols_preview].tolist()
            elif pixel_array.ndim == 3:
                preview = pixel_array[0, :rows_preview, :cols_preview].tolist()
        return PixelDataResponse(
            sop_instance_uid=sop_instance_uid,
            rows=ds.Rows,
            columns=ds.Columns,
            pixel_array_shape=pixel_array.shape,
            pixel_array_dtype=str(pixel_array.dtype),
            pixel_array_preview=preview,
            message="Pixel data accessed from locally stored C-MOVE file. Preview shown."
        )
    except Exception as e:
        logger.error(f"Error procesando archivo DICOM almacenado {filepath}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al procesar archivo DICOM almacenado: {str(e)}")

# --- FIN: NUEVOS ENDPOINTS ---