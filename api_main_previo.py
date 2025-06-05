# api_main.py
import logging
import re 
import io
import os
import json # Para parsear filtros JSON
from fastapi import FastAPI, HTTPException, Query
from starlette.responses import FileResponse # Para favicon
from typing import Any, List, Optional, Dict, Tuple, Union # Añadido Union
import threading
from contextlib import asynccontextmanager

from models import (
    StudyResponse, 
    SeriesResponse, 
    InstanceMetadataResponse, 
    LUTExplanationModel,
    PixelDataResponse,
    MoveRequest, # Modelo original para C-MOVE singular/jerárquico
    BulkMoveRequest # Modelo para C-MOVE de múltiples instancias específicas
)

import pydicom
from pydicom.tag import Tag
from pydicom.datadict import keyword_for_tag, tag_for_keyword, dictionary_VR
from pydicom.dataset import Dataset as DicomDataset
from pydicom.datadict import dictionary_VR # Necesario para la lógica de 'fields'
from pydicom.dataelem import DataElement
from pydicom.multival import MultiValue

import pacs_operations
import config
import dicom_scp

# --- Configuración del Logger ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers(): # Evitar añadir múltiples handlers si se importa o recarga
    # Configuración básica si no hay handlers. Considera usar la de utils.py para consistencia.
    logging.basicConfig(
        level=config.LOG_LEVEL, # Usar nivel de config.py
        format=config.LOG_FORMAT, # Usar formato de config.py
        force=True # Para asegurar que se reconfigure si se llama varias veces
    )

# --- Lifespan Manager para iniciar/detener el SCP ---
scp_thread: Optional[threading.Thread] = None

@asynccontextmanager
async def lifespan(app_lifespan: FastAPI): # Renombrado el parámetro para claridad
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
    version="1.3.0", # Versión incrementada para reflejar cambios
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
    else: 
        logger.debug(f"Regex principal no coincidió para LUTExplanation: '{text}'. Usando texto completo como explicación.")
        explanation_part = text # Mantener el texto original si el regex no capta nada
    return LUTExplanationModel(FullText=text, Explanation=explanation_part if explanation_part else None, InCalibRange=in_calib_range_parsed, OutLUTRange=out_lut_range_parsed)

# --- Endpoints ---
@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Consultas PACS DICOM"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Asegúrate de tener un archivo xray.ico en el mismo directorio que api_main.py o proporciona la ruta completa.
    # Si el archivo está en un subdirectorio 'static', por ejemplo:
    # return FileResponse("static/xray.ico")
    # Por ahora, asumimos que está en el directorio raíz del proyecto.
    # Es mejor usar una ruta absoluta o relativa al script actual para robustez.
    favicon_path = os.path.join(os.path.dirname(__file__), "xray.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    else:
        # Devolver un 404 si no se encuentra, o no hacer nada si es opcional.
        # FastAPI por defecto devuelve 404 si no hay ruta.
        logger.warning(f"Favicon no encontrado en: {favicon_path}")
        raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/studies", response_model=List[StudyResponse])
async def find_studies_endpoint(
    # Parámetros de consulta específicos que son comunes
    PatientID_param: Optional[str] = Query(None, alias="PatientID", description="Patient ID to filter by."),
    StudyDate_param: Optional[str] = Query(None, alias="StudyDate", description="Study Date (YYYYMMDD or YYYYMMDD-YYYYMMDD range)."),
    AccessionNumber_param: Optional[str] = Query(None, alias="AccessionNumber", description="Accession Number."),
    ModalitiesInStudy_param: Optional[str] = Query(None, alias="ModalitiesInStudy", description="Modalities in Study (e.g., CT, MR)."),
    PatientName_param: Optional[str] = Query(None, alias="PatientName", description="Patient's Name for filtering."),
    # Parámetro de filtros genéricos
    filters: Optional[str] = Query(None, description="JSON string for additional DICOM tag filtering, e.g., '{\"ReferringPhysicianName\":\"DOE^J\", \"(0008,0090)\":\"DOE^J\"}'")
):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "STUDY"

    # Campos que siempre queremos que se devuelvan con valor vacío si no se usan como filtro,
    # para que pynetdicom los solicite.
    base_return_fields = {
        "StudyInstanceUID": "", "PatientID": "", "PatientName": "", "StudyDate": "",
        "StudyDescription": "", "ModalitiesInStudy": "", "AccessionNumber": ""
    }
    for kw, val in base_return_fields.items():
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
                original_key_for_log = key
                try:
                    if isinstance(key, str) and ',' in key: 
                        group_str, elem_str = key.strip("() ").split(',')
                        tag_obj = Tag(int(group_str, 16), int(elem_str, 16))
                    else: 
                        tag_val_from_kw = tag_for_keyword(str(key))
                        if tag_val_from_kw:
                            tag_obj = Tag(tag_val_from_kw)
                        else:
                            logger.warning(f"Keyword DICOM '{original_key_for_log}' en 'filters' para estudios no reconocido. Omitiendo.")
                            continue
                    
                    dicom_keyword = keyword_for_tag(tag_obj)
                    if dicom_keyword:
                        setattr(identifier, dicom_keyword, value)
                    else:
                        identifier[tag_obj] = value
                    logger.info(f"[find_studies_endpoint] Aplicando filtro: Tag {tag_obj} ({original_key_for_log}) = '{value}'")

                except ValueError:
                    logger.warning(f"Formato de tag inválido '{original_key_for_log}' en 'filters' para estudios. Omitiendo.")
                except Exception as e_filter_tag:
                    logger.error(f"Error procesando tag de filtro para estudios '{original_key_for_log}': {e_filter_tag}", exc_info=True)
        
        except json.JSONDecodeError as e_json:
            logger.error(f"Error decodificando JSON en 'filters' para estudios: {filters}. Error: {e_json}")
            raise HTTPException(status_code=400, detail=f"Parámetro 'filters' con JSON inválido: {e_json}")
    
    logger.debug(f"[find_studies_endpoint] Identificador C-FIND final:\n{identifier}")
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
    filters: Optional[str] = Query(None, description="JSON string for DICOM tag filtering, e.g., '{\"Modality\":\"CT\", \"(0018,0015)\":\"CHEST\"}'")
):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "SERIES"
    identifier.StudyInstanceUID = study_instance_uid
    
    base_return_fields = {
        "SeriesInstanceUID": "", "Modality": "", "SeriesNumber": "", "SeriesDescription": ""
        # "KVP": "" # Si quieres KVP a nivel de serie, y el PACS lo soporta
    }
    for kw, val in base_return_fields.items():
        setattr(identifier, kw, val)

    if filters:
        try:
            filter_dict = json.loads(filters)
            for key, value in filter_dict.items():
                tag_obj: Optional[Tag] = None
                original_key_for_log = key
                try:
                    if isinstance(key, str) and ',' in key: 
                        group_str, elem_str = key.strip("() ").split(',')
                        tag_obj = Tag(int(group_str, 16), int(elem_str, 16))
                    else: 
                        tag_val_from_kw = tag_for_keyword(str(key))
                        if tag_val_from_kw:
                            tag_obj = Tag(tag_val_from_kw)
                        else:
                            logger.warning(f"Keyword DICOM '{original_key_for_log}' en 'filters' para series no reconocido. Omitiendo.")
                            continue
                    
                    dicom_keyword = keyword_for_tag(tag_obj)
                    if dicom_keyword:
                        setattr(identifier, dicom_keyword, value)
                    else:
                        identifier[tag_obj] = value
                    logger.info(f"[find_series_in_study] Aplicando filtro: Tag {tag_obj} ({original_key_for_log}) = '{value}'")

                except ValueError:
                    logger.warning(f"Formato de tag inválido '{original_key_for_log}' en 'filters' para series. Omitiendo.")
                except Exception as e_filter_tag:
                    logger.error(f"Error procesando tag de filtro para series '{original_key_for_log}': {e_filter_tag}", exc_info=True)
        except json.JSONDecodeError as e_json:
            logger.error(f"Error decodificando JSON en 'filters' para series: {filters}. Error: {e_json}")
            raise HTTPException(status_code=400, detail=f"Parámetro 'filters' con JSON inválido para series: {e_json}")

    logger.debug(f"[find_series_in_study] Identificador C-FIND final:\n{identifier}")
    logger.info(f"----------------------------------------------------------------")
    logger.info(f"IDENTIFICADOR C-FIND FINAL QUE SE ENVÍA AL PACS:")
    logger.info(f"StudyInstanceUID: {identifier.get('StudyInstanceUID', 'NO PRESENTE')}")
    logger.info(f"SeriesInstanceUID: {identifier.get('SeriesInstanceUID', 'NO PRESENTE')}")
    logger.info(f"QueryRetrieveLevel: {identifier.get('QueryRetrieveLevel', 'NO PRESENTE')}")
    logger.info(f"SOPInstanceUID: '{identifier.get('SOPInstanceUID', 'NO PRESENTE')}'")
    logger.info(f"InstanceNumber: '{identifier.get('InstanceNumber', 'NO PRESENTE')}'")
    
    # Mostrar los campos que se usaron para filtrar o solicitar
    logger.info(f"Contenido completo del identificador a enviar:")
    for elem in identifier:
        # Para una mejor visualización, puedes optar por no loguear tags binarios largos aquí
        # o limitar la longitud del valor.
        value_to_log = elem.value
        if isinstance(value_to_log, bytes) and len(value_to_log) > 64: # Evitar logs muy largos para datos binarios
            value_to_log = f"<bytes de longitud {len(elem.value)}>"
        
        if elem.keyword: # Mostrar campos con keyword
            logger.info(f"    {elem.keyword} ({elem.tag}): VR='{elem.VR}', Value='{value_to_log}'")
        else: # Mostrar campos sin keyword (ej. privados)
            logger.info(f"    ({elem.tag}): VR='{elem.VR}', Value='{value_to_log}'")
    logger.info(f"----------------------------------------------------------------")    
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
                try: series_number_for_pydantic = str(int(str(series_number_raw))) # Asegurar que es string antes de int
                except (ValueError, TypeError): series_number_for_pydantic = str(series_number_raw)
            
            # KVP es un tag de nivel de instancia, pero algunos PACS pueden devolverlo a nivel de serie si es consistente.
            # Lo incluimos en el modelo SeriesResponse, pero puede ser None.
            kvp_val = res_ds.get("KVP") 
            kvp_for_pydantic: Optional[str] = None
            if kvp_val is not None:
                 kvp_for_pydantic = str(kvp_val)


            response_list.append(SeriesResponse(
                StudyInstanceUID=res_ds.get("StudyInstanceUID", study_instance_uid),
                SeriesInstanceUID=res_ds.get("SeriesInstanceUID", ""),
                Modality=res_ds.get("Modality", ""),
                SeriesNumber=series_number_for_pydantic,
                SeriesDescription=res_ds.get("SeriesDescription", ""),
                KVP=kvp_for_pydantic # Añadido al modelo de respuesta si lo necesitas
            ))
        return response_list
    except Exception as e:
        logger.error(f"Error en C-FIND de series: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al consultar series: {str(e)}")


# api_main.py
# ... (importaciones existentes, asegúrate de tener json, Tag, keyword_for_tag, tag_for_keyword, DicomDataset) ...

@app.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances", response_model=List[InstanceMetadataResponse])
async def find_instances_in_series(
    study_instance_uid: str,
    series_instance_uid: str,
    fields: Optional[List[str]] = Query(None, description="Lista de keywords DICOM o (gggg,eeee) a recuperar. E.g., 'PatientName', 'KVP', '(0020,4000)'."),
    filters: Optional[str] = Query(None, description="JSON string for DICOM tag filtering, e.g., '{\"KVP\":\"70\", \"ImageComments\":\"Processed*\"}'")
):
    logger.debug(f"[find_instances_in_series] StudyUID: {study_instance_uid}, SeriesUID: {series_instance_uid}")
    logger.debug(f"[find_instances_in_series] Recibido fields: {fields}")
    logger.debug(f"[find_instances_in_series] Recibido filters: {filters}")

    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "IMAGE"
    identifier.StudyInstanceUID = study_instance_uid
    identifier.SeriesInstanceUID = series_instance_uid
    
    # Claves que siempre se solicitan (con valor vacío para universal matching y retorno)
    # a menos que se especifiquen en 'filters' con un valor concreto.
    identifier.SOPInstanceUID = ""
    identifier.InstanceNumber = ""

    # 1. Procesar FILTROS y añadirlos al IDENTIFIER con sus VALORES ESPECÍFICOS
    if filters:
        try:
            filter_dict = json.loads(filters)
            logger.debug(f"[find_instances_in_series] Filtros parseados: {filter_dict}")
            for key, value in filter_dict.items():
                tag_obj: Optional[Tag] = None
                original_key_for_log = str(key) # Guardar para logging
                try:
                    if ',' in original_key_for_log: 
                        group_str, elem_str = original_key_for_log.strip("() ").split(',')
                        tag_obj = Tag(int(group_str, 16), int(elem_str, 16))
                    else: 
                        tag_val_from_kw = tag_for_keyword(original_key_for_log)
                        if tag_val_from_kw:
                            tag_obj = Tag(tag_val_from_kw)
                        else:
                            logger.warning(f"Keyword DICOM '{original_key_for_log}' en 'filters' no reconocido. Omitiendo.")
                            continue
                    
                    if tag_obj:
                        dicom_keyword = keyword_for_tag(tag_obj)
                        if dicom_keyword:
                            setattr(identifier, dicom_keyword, value)
                        else:
                            identifier[tag_obj] = value # Para tags sin keyword (ej. privados)
                        logger.info(f"[find_instances_in_series] Aplicando filtro al 'identifier': Tag {tag_obj} ({original_key_for_log}) = '{value}'")

                except ValueError as ve_filter:
                    logger.warning(f"Formato de tag inválido '{original_key_for_log}' en 'filters': {ve_filter}. Omitiendo.")
                except Exception as e_filter_tag:
                    logger.error(f"Error procesando tag de filtro '{original_key_for_log}': {e_filter_tag}", exc_info=True)
        except json.JSONDecodeError as e_json:
            logger.error(f"Error decodificando JSON en 'filters': {filters}. Error: {e_json}")
            raise HTTPException(status_code=400, detail=f"Parámetro 'filters' con JSON inválido: {e_json}")

    # 2. Procesar FIELDS para solicitar su retorno y añadirlos al IDENTIFIER con VALOR VACÍO
    #    SOLAMENTE si no fueron ya establecidos por un filtro con un valor específico.
    requested_tags_for_response: Dict[str, Tag] = {} # Almacena Tag objects para la construcción de la respuesta
    if fields:
        logger.debug(f"[find_instances_in_series] Procesando 'fields' para solicitar retorno: {fields}")
        for field_str_raw in fields:
            field_str = str(field_str_raw)
            tag_from_field: Optional[Tag] = None
            try:
                if ',' in field_str:
                    group_str, elem_str = field_str.strip("() ").split(',')
                    tag_from_field = Tag(int(group_str, 16), int(elem_str, 16))
                else:
                    tag_val_from_keyword = tag_for_keyword(field_str)
                    if tag_val_from_keyword:
                        tag_from_field = Tag(tag_val_from_keyword)
                    else:
                        logger.warning(f"Keyword DICOM '{field_str}' en 'fields' no reconocida. Omitiendo de 'requested_tags_for_response'.")
                        continue
                
                if tag_from_field:
                    requested_tags_for_response[str(tag_from_field)] = tag_from_field
                    
                    # Si el tag NO está en el identifier (no fue un filtro) O SI está pero con valor vacío (queremos asegurar que se pida)
                    # NO queremos sobreescribir un valor de filtro específico (ej. KVP="70") con un valor vacío.
                    if tag_from_field not in identifier or identifier.get(tag_from_field, "") == "":
                        dicom_keyword_for_field = keyword_for_tag(tag_from_field)
                        if dicom_keyword_for_field:
                            # Asegurarse de que el atributo exista antes de intentar acceder a su valor
                            if not hasattr(identifier, dicom_keyword_for_field) or getattr(identifier, dicom_keyword_for_field) == "":
                                setattr(identifier, dicom_keyword_for_field, "")
                        else:
                             if tag_from_field not in identifier or identifier[tag_from_field] == "":
                                identifier[tag_from_field] = ""
                        logger.debug(f"Campo '{field_str}' (Tag: {tag_from_field}) añadido/asegurado en 'identifier' con valor vacío para solicitar su retorno.")
            
            except ValueError as ve_field:
                logger.warning(f"Formato de tag DICOM inválido para field '{field_str}': {ve_field}. Omitiendo.")
            except Exception as e_field_tag:
                 logger.warning(f"Error procesando field '{field_str}' como tag DICOM: {e_field_tag}. Omitiendo.")

    logger.info(f"[find_instances_in_series] Identificador C-FIND final (después de filters y fields):\n{identifier}")
    
    pacs_config_dict = {
        "PACS_IP": config.PACS_IP, "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET, "AE_TITLE": config.CLIENT_AET
    }
    try:
        results_datasets = await pacs_operations.perform_c_find_async(
            identifier, pacs_config_dict, query_model_uid='S'
        )
        
        response_list: List[InstanceMetadataResponse] = []
        logger.debug(f"[find_instances_in_series] Número de datasets recibidos del PACS: {len(results_datasets)}")

        for i, res_ds in enumerate(results_datasets):
            # ... (la lógica de construcción de 'headers' y 'response_list' permanece igual que en la respuesta anterior,
            #      asegurándote de que usa 'requested_tags_for_response' o todos los tags de 'res_ds' si 'fields' no se proveyó,
            #      y que la conversión de valores es robusta) ...
            headers: Dict[str, Any] = {}
            sop_instance_uid_val = res_ds.get("SOPInstanceUID", f"DESCONOCIDO_EN_POS_{i}")
            instance_number_raw = res_ds.get("InstanceNumber")
            instance_number_val: Optional[str] = None
            if instance_number_raw is not None:
                try: instance_number_val = str(int(str(instance_number_raw)))
                except (ValueError, TypeError): instance_number_val = str(instance_number_raw)
            
            logger.debug(f"[find_instances_in_series] Procesando dataset de respuesta #{i} para SOPInstanceUID: {sop_instance_uid_val}")

            tags_to_populate_headers = requested_tags_for_response
            if not fields: 
                logger.debug(f"No se especificaron 'fields'. Se intentarán devolver todos los tags del dataset de respuesta para SOPInstanceUID {sop_instance_uid_val}.")
                tags_to_populate_headers = {str(elem.tag): elem.tag for elem in res_ds}
            
            logger.debug(f"Tags a incluir en headers para SOPInstanceUID {sop_instance_uid_val}: {[keyword_for_tag(t) or str(t) for t in tags_to_populate_headers.values()]}")

            for tag_key_str_loop, tag_obj_to_get in tags_to_populate_headers.items(): # tag_key_str_loop es string "(G, E)"
                if tag_obj_to_get in res_ds: # tag_obj_to_get es Tag(G,E)
                    element = res_ds[tag_obj_to_get]
                    key_to_use_in_json = keyword_for_tag(element.tag) or str(element.tag) # Nombre para el JSON de salida
                    value_to_store: Any
                    
                    # Lógica de conversión de valor detallada (basada en la discusión anterior)
                    if element.VR == 'SQ': 
                        sequence_items = []
                        if isinstance(element.value, pydicom.sequence.Sequence):
                            for item_index, item_dataset in enumerate(element.value): 
                                item_data: Dict[str, Any] = {}
                                for item_element in item_dataset: 
                                    item_key_in_seq = keyword_for_tag(item_element.tag) or str(item_element.tag)
                                    item_val_in_seq: Any = None
                                    if item_element.tag == Tag(0x0028, 0x3006): # LUTData
                                        item_val_in_seq = f"Binary LUT data (length {len(item_element.value) if item_element.value is not None else 0}), not included"
                                    elif item_element.tag == Tag(0x0028,0x3003): # LUTExplanation
                                        item_val_in_seq = parse_lut_explanation(item_element.value)
                                    elif item_element.VR == 'PN': item_val_in_seq = str(item_element.value) if item_element.value is not None else ""
                                    elif item_element.VR in ['DA', 'DT', 'TM']: item_val_in_seq = str(item_element.value) if item_element.value is not None else ""
                                    elif item_element.VR == 'IS':
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [str(int(str(v))) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = str(int(str(item_element.value)))
                                        else: item_val_in_seq = None
                                    elif item_element.VR == 'DS':
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [str(float(str(v))) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = str(float(str(item_element.value)))
                                        else: item_val_in_seq = None
                                    elif item_element.VR in ['US', 'SS', 'SL', 'UL', 'AT']:
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [int(str(v)) for v in item_element.value] # Convertir a int
                                        elif item_element.value is not None: item_val_in_seq = int(str(item_element.value)) # Convertir a int
                                        else: item_val_in_seq = None
                                    elif item_element.VR in ['FL', 'FD']:
                                        if isinstance(item_element.value, MultiValue): item_val_in_seq = [float(str(v)) for v in item_element.value]
                                        elif item_element.value is not None: item_val_in_seq = float(str(item_element.value))
                                        else: item_val_in_seq = None
                                    elif isinstance(item_element.value, (bytes, bytearray)):
                                        item_val_in_seq = f"Binary data (VR: {item_element.VR}, length {len(item_element.value)}), not included"
                                    elif item_element.value is None: item_val_in_seq = None
                                    else: item_val_in_seq = str(item_element.value)
                                    item_data[item_key_in_seq] = item_val_in_seq
                                sequence_items.append(item_data)
                        value_to_store = sequence_items
                    elif element.VR == 'PN': value_to_store = str(element.value) if element.value is not None else ""
                    elif element.VR in ['DA', 'DT', 'TM']: value_to_store = str(element.value) if element.value is not None else ""
                    elif element.VR == 'IS':
                        if isinstance(element.value, MultiValue): value_to_store = [str(int(str(v))) for v in element.value]
                        elif element.value is not None: value_to_store = str(int(str(element.value)))
                        else: value_to_store = None
                    elif element.VR == 'DS':
                        if isinstance(element.value, MultiValue): value_to_store = [str(float(str(v))) for v in element.value]
                        elif element.value is not None: value_to_store = str(float(str(element.value)))
                        else: value_to_store = None
                    elif element.VR in ['US', 'SS', 'SL', 'UL', 'AT']:
                        if isinstance(element.value, MultiValue): value_to_store = [int(str(v)) for v in element.value] # Convertir a int
                        elif element.value is not None: value_to_store = int(str(element.value)) # Convertir a int
                        else: value_to_store = None
                    elif element.VR in ['FL', 'FD']:
                        if isinstance(element.value, MultiValue): value_to_store = [float(str(v)) for v in element.value]
                        elif element.value is not None: value_to_store = float(str(element.value))
                        else: value_to_store = None
                    elif isinstance(element.value, (bytes, bytearray)) and element.VR not in ['OB', 'OW', 'OF', 'OD', 'OL', 'OV', 'UN', 'PixelData']: # Evitar PixelData
                        try: value_to_store = element.value.decode(pydicom.charset.detect_charset(element.value, default='iso_ir_100')).strip()
                        except: value_to_store = f"Undecodable text or binary data (VR: {element.VR}, length {len(element.value)})"
                    elif isinstance(element.value, (bytes, bytearray)): # Para OB, OW etc.
                         value_to_store = f"Binary data (VR: {element.VR}, length {len(element.value)}), not included"
                    elif element.value is None: value_to_store = None
                    else: value_to_store = str(element.value)
                    
                    headers[key_to_use_in_json] = value_to_store
                    # logger.debug(f"Añadido a headers para SOPInstanceUID {sop_instance_uid_val}: '{key_to_use_in_json}' (VR: {element.VR}) = '{value_to_store}'")
                else:
                    key_to_use_if_missing = keyword_for_tag(tag_obj_to_get) or str(tag_obj_to_get)
                    logger.debug(f"Tag '{key_to_use_if_missing}' (Tag: {tag_obj_to_get}) solicitado pero NO encontrado en la respuesta del PACS para SOPInstanceUID {sop_instance_uid_val}.")
            
            response_list.append(InstanceMetadataResponse(
                SOPInstanceUID=sop_instance_uid_val,
                InstanceNumber=instance_number_val,
                dicom_headers=headers
            ))
        return response_list
    except Exception as e:
        logger.error(f"Error en C-FIND de instancias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al consultar instancias: {str(e)}")

# ... (resto de tus endpoints, como /retrieve-instance, /retrieve-multiple-instances, /retrieved-instances/.../pixeldata)

# --- Endpoints para C-MOVE ---

# Endpoint para C-MOVE de una sola jerarquía (estudio, serie o instancia única)
@app.post("/retrieve-instance", status_code=202, summary="Solicita al PACS mover un estudio/serie/instancia a esta API")
async def retrieve_instance_via_cmove(item: MoveRequest): # Usa el modelo MoveRequest original
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
    elif item.study_instance_uid: # Solo StudyInstanceUID
        identifier.QueryRetrieveLevel = "STUDY"
        identifier.SeriesInstanceUID = "" 
        identifier.SOPInstanceUID = ""    
    else:
        # Esto no debería ocurrir si MoveRequest requiere study_instance_uid
        raise HTTPException(status_code=400, detail="Se requiere al menos StudyInstanceUID.")

    logger.info(f"Solicitud C-MOVE para: QueryLevel='{identifier.QueryRetrieveLevel}', StudyUID='{identifier.StudyInstanceUID}', SeriesUID='{identifier.get('SeriesInstanceUID', 'N/A')}', SOPInstanceUID='{identifier.get('SOPInstanceUID', 'N/A')}'")

    pacs_config_dict = {
        "PACS_IP": config.PACS_IP, "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET, "AE_TITLE": config.CLIENT_AET 
    }
    move_destination = config.API_SCP_AET
    try:
        move_responses = await pacs_operations.perform_c_move_async(
            identifier, pacs_config_dict, move_destination_aet=move_destination, query_model_uid='S' # Asume Study Root
        )
        
        # Interpretar la respuesta C-MOVE
        # La lista move_responses contiene tuplas de (status_dataset, identifier_dataset)
        # El último status_dataset es el que indica el estado final de la operación C-MOVE general.
        final_status_ds = None
        num_completed = 0
        num_failed = 0
        num_warning = 0

        if move_responses:
            for status_ds_item, _ in move_responses: # Iterar para obtener el último estado y contadores
                if status_ds_item:
                    final_status_ds = status_ds_item
                    num_completed = status_ds_item.get("NumberOfCompletedSuboperations", num_completed)
                    num_failed = status_ds_item.get("NumberOfFailedSuboperations", num_failed)
                    num_warning = status_ds_item.get("NumberOfWarningSuboperations", num_warning)
        
        if final_status_ds and hasattr(final_status_ds, 'Status'):
            status_val = final_status_ds.Status
            msg = (
                f"Operación C-MOVE. Estado final del PACS: 0x{status_val:04X}. "
                f"Sub-operaciones: Completadas={num_completed}, Fallidas={num_failed}, Advertencias={num_warning}."
            )
            if status_val == 0x0000: # Éxito
                logger.info(msg)
                return {"message": msg}
            elif status_val == 0xFF00: # Pending (raro como estado final, pero posible si es la única respuesta)
                 logger.info(f"{msg} La operación está pendiente, esperando más respuestas del PACS.")
                 return {"message": f"{msg} La operación está pendiente."}
            else: # Fallo o advertencia
                logger.error(msg)
                raise HTTPException(status_code=502, detail=msg) # Bad Gateway si el PACS reporta fallo
        else:
            logger.error("No se recibió una respuesta de estado final válida o completa del C-MOVE.")
            raise HTTPException(status_code=502, detail="Respuesta C-MOVE incompleta o no exitosa del PACS.")

    except ConnectionError as e:
        logger.error(f"Error de conexión C-MOVE: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Error de conexión al PACS para C-MOVE: {str(e)}")
    except Exception as e:
        logger.error(f"Error al solicitar C-MOVE: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor durante C-MOVE: {str(e)}")

@app.post("/retrieve-multiple-instances", status_code=202, summary="Solicita al PACS mover múltiples instancias específicas a esta API")
async def retrieve_multiple_instances_via_cmove(request_data: BulkMoveRequest):
    pacs_config_dict = {
        "PACS_IP": config.PACS_IP,
        "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET,
        "AE_TITLE": config.CLIENT_AET
    }
    move_destination_aet = config.API_SCP_AET
    responses_summary = []
    
    if not request_data.instances_to_move:
        raise HTTPException(status_code=400, detail="La lista 'instances_to_move' no puede estar vacía.")

    for instance_info in request_data.instances_to_move:
        identifier = DicomDataset()
        identifier.QueryRetrieveLevel = "IMAGE"
        identifier.StudyInstanceUID = instance_info.study_instance_uid
        identifier.SeriesInstanceUID = instance_info.series_instance_uid
        identifier.SOPInstanceUID = instance_info.sop_instance_uid
        
        instance_response_summary = {
            "study_instance_uid": instance_info.study_instance_uid,
            "series_instance_uid": instance_info.series_instance_uid,
            "sop_instance_uid": instance_info.sop_instance_uid,
            "status_code_hex": "N/A",
            "message": "No procesado",
            "sub_operations_completed": 0,
            "sub_operations_failed": 0,
            "sub_operations_warning": 0
        }

        try:
            logger.info(f"Iniciando C-MOVE para SOPInstanceUID: {instance_info.sop_instance_uid} hacia {move_destination_aet}")
            move_responses_single = await pacs_operations.perform_c_move_async(
                identifier, pacs_config_dict, move_destination_aet=move_destination_aet, query_model_uid='S'
            )
            
            final_status_ds_single = None
            num_completed_single = 0
            num_failed_single = 0
            num_warning_single = 0

            if move_responses_single:
                for status_ds_item, _ in move_responses_single:
                    if status_ds_item:
                        final_status_ds_single = status_ds_item
                        num_completed_single = status_ds_item.get("NumberOfCompletedSuboperations", num_completed_single)
                        num_failed_single = status_ds_item.get("NumberOfFailedSuboperations", num_failed_single)
                        num_warning_single = status_ds_item.get("NumberOfWarningSuboperations", num_warning_single)

            instance_response_summary["sub_operations_completed"] = num_completed_single
            instance_response_summary["sub_operations_failed"] = num_failed_single
            instance_response_summary["sub_operations_warning"] = num_warning_single

            if final_status_ds_single and hasattr(final_status_ds_single, 'Status'):
                status_val_single = final_status_ds_single.Status
                instance_response_summary["status_code_hex"] = f"0x{status_val_single:04X}"
                instance_response_summary["message"] = f"Estado final del PACS: 0x{status_val_single:04X}."
                if status_val_single == 0x0000:
                    logger.info(f"C-MOVE para {instance_info.sop_instance_uid} exitoso.")
                else:
                    logger.warning(f"C-MOVE para {instance_info.sop_instance_uid} con estado {status_val_single:#04X}.")
            else:
                instance_response_summary["message"] = f"No se recibió estado final claro del PACS para {instance_info.sop_instance_uid}."
                logger.error(instance_response_summary["message"])

        except ConnectionError as e_conn:
            logger.error(f"Error de conexión durante C-MOVE para {instance_info.sop_instance_uid}: {e_conn}", exc_info=True)
            instance_response_summary["message"] = f"Error de conexión: {str(e_conn)}"
            instance_response_summary["status_code_hex"] = "CONN_ERROR"
        except Exception as e_generic:
            logger.error(f"Error genérico durante C-MOVE para {instance_info.sop_instance_uid}: {e_generic}", exc_info=True)
            instance_response_summary["message"] = f"Error interno del servidor: {str(e_generic)}"
            instance_response_summary["status_code_hex"] = "SERVER_ERROR"
        
        responses_summary.append(instance_response_summary)

    return {
        "message": "Procesamiento de C-MOVE masivo completado. Revise los resultados individuales.",
        "results": responses_summary
    }


@app.get("/retrieved-instances/{sop_instance_uid}/pixeldata", response_model=PixelDataResponse, summary="Obtiene datos de píxeles de una instancia recibida localmente")
async def get_retrieved_instance_pixeldata(sop_instance_uid: str):
    # Validar el SOPInstanceUID para evitar traversal attacks, aunque join lo mitiga.
    # Un UID válido no debería contener '..' o '/'.
    if not re.fullmatch(r"[0-9\.]+", sop_instance_uid): # Patrón simple para UIDs DICOM
        raise HTTPException(status_code=400, detail="SOPInstanceUID con formato inválido.")

    # Usar config.DICOM_RECEIVED_DIR que es un Path object
    filepath = config.DICOM_RECEIVED_DIR / (sop_instance_uid + ".dcm")
    logger.info(f"[get_retrieved_instance_pixeldata] Buscando archivo: {filepath}")

    if not filepath.is_file(): # Usar el método de Path
        logger.warning(f"Archivo DICOM no encontrado en el directorio de recepción: {filepath}")
        raise HTTPException(status_code=404, detail="Archivo DICOM no encontrado. Es posible que C-MOVE no haya completado, fallado, o aún no haya llegado.")
    
    try:
        ds = pydicom.dcmread(str(filepath), force=True) # dcmread necesita string
        if not hasattr(ds, 'PixelData') or ds.PixelData is None:
            raise HTTPException(status_code=404, detail="El objeto DICOM no contiene datos de píxeles (PixelData) válidos.")
        
        pixel_array = ds.pixel_array # Esto puede tardar y consumir memoria para imágenes grandes
        logger.info(f"Array de píxeles obtenido del archivo {filepath}: forma={pixel_array.shape}, tipo={pixel_array.dtype}")
        
        preview = None
        # Crear un preview más pequeño para evitar enviar arrays muy grandes en JSON
        if pixel_array.ndim >= 2 and pixel_array.size > 0:
            # Para imágenes 2D (monocromo o un frame de color)
            if pixel_array.ndim == 2:
                rows_preview = min(pixel_array.shape[0], 5)
                cols_preview = min(pixel_array.shape[1], 5)
                preview = pixel_array[:rows_preview, :cols_preview].tolist()
            # Para imágenes 3D (multiframe monocromo o RGB)
            elif pixel_array.ndim == 3:
                # Asumimos primer frame para preview si es multiframe monocromo
                # o un plano si es color (ej. pixel_array[0] sería el plano R si es (planos, filas, cols))
                # pydicom.pixel_array maneja esto y devuelve (filas, cols) o (filas, cols, samples) o (frames, filas, cols)
                # Si es (frames, filas, cols)
                if ds.get("SamplesPerPixel", 1) == 1: # Monocromo multiframe
                     rows_preview = min(pixel_array.shape[1], 5)
                     cols_preview = min(pixel_array.shape[2], 5)
                     preview = pixel_array[0, :rows_preview, :cols_preview].tolist() # Preview del primer frame
                # Si es (filas, cols, samples) -> color
                elif ds.get("SamplesPerPixel", 1) > 1 and pixel_array.shape[-1] == ds.SamplesPerPixel:
                     rows_preview = min(pixel_array.shape[0], 5)
                     cols_preview = min(pixel_array.shape[1], 5)
                     preview = pixel_array[:rows_preview, :cols_preview, 0].tolist() # Preview del primer canal (ej. Rojo)


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

# --- Fin de api_main.py ---