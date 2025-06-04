# api_main.py
import logging
import re
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, List, Optional, Dict, Tuple # Añadido Tuple

import pydicom
from pydicom.tag import Tag
from pydicom.dataset import Dataset as DicomDataset
from pydicom.datadict import dictionary_VR, tag_for_keyword
from pydicom.dataelem import DataElement
from pydicom.multival import MultiValue

import pacs_operations
import config

# --- Configuración del Logger ---
logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)


app = FastAPI(title="API de Consultas PACS DICOM", version="1.0.0")

# --- Modelos Pydantic ---
class StudyResponse(BaseModel):
    StudyInstanceUID: str
    PatientID: Optional[str] = None
    PatientName: Optional[str] = None
    StudyDate: Optional[str] = None
    StudyDescription: Optional[str] = None
    ModalitiesInStudy: Optional[str] = None
    AccessionNumber: Optional[str] = None

class LUTExplanationModel(BaseModel):
    FullText: Optional[str] = None
    Explanation: Optional[str] = None
    InCalibRange: Optional[Tuple[float, float]] = None # MODIFICADO
    OutLUTRange: Optional[Tuple[float, float]] = None  # MODIFICADO

class ModalityLUTItemModel(BaseModel):
    LUTDescriptor: Optional[List[int]] = None
    LUTExplanation: Optional[LUTExplanationModel] = None
    ModalityLUTType: Optional[str] = None
    LUTData: Optional[str] = None

class InstanceMetadataResponse(BaseModel):
    SOPInstanceUID: str
    InstanceNumber: Optional[str] = None
    dicom_headers: Dict[str, Any]

class SeriesResponse(BaseModel):
    StudyInstanceUID: str
    SeriesInstanceUID: str
    Modality: Optional[str] = None
    SeriesNumber: Optional[str] = None
    SeriesDescription: Optional[str] = None


# --- Funciones Auxiliares ---
def _parse_range_to_floats(range_str: Optional[str]) -> Optional[Tuple[float, float]]:
    """Convierte una cadena 'num-num' o 'num' a una tupla de flotantes."""
    if not range_str:
        return None
    try:
        parts = range_str.strip().split('-')
        if len(parts) == 1: # Asumir que es un solo número si no hay guion
            val = float(parts[0].strip())
            return (val, val) # O podrías decidir devolver (val, None) o (None, val)
        elif len(parts) == 2:
            return (float(parts[0].strip()), float(parts[1].strip()))
        else:
            logger.warning(f"Formato de rango inesperado: '{range_str}'. No se pudo parsear a dos flotantes.")
            return None
    except ValueError:
        logger.warning(f"Error al convertir valores del rango '{range_str}' a flotantes.")
        return None

def parse_lut_explanation(explanation_str_raw: Optional[Any]) -> LUTExplanationModel:
    """Parsea la cadena de LUTExplanation en subcampos."""
    if explanation_str_raw is None:
        return LUTExplanationModel(FullText=None)

    text = str(explanation_str_raw) # Asegurar que es una cadena
    explanation_part = text # Valor por defecto
    in_calib_range_parsed: Optional[Tuple[float, float]] = None
    out_lut_range_parsed: Optional[Tuple[float, float]] = None

    # Ejemplo de cadena: "Kerma uGy (SF=100) InCalibRange:1.00-54.56 OutLUTRange:100-5456"
    # Usamos regex para intentar capturar las partes
    # Grupo 1: Explanation (todo hasta "InCalibRange" o "OutLUTRange" o el final)
    # Grupo 3: Valor de InCalibRange
    # Grupo 5: Valor de OutLUTRange
    regex_pattern = r"^(.*?)(?:InCalibRange:\s*([0-9\.\-]+))?\s*(?:OutLUTRange:\s*([0-9\.\-]+))?$"
    match = re.fullmatch(regex_pattern, text.strip()) # Usar fullmatch para asegurar que toda la cadena coincida

    if match:
        explanation_part = match.group(1).strip() if match.group(1) else ""
        
        in_calib_range_str = match.group(2) # Puede ser None si no hay "InCalibRange:"
        if in_calib_range_str:
            in_calib_range_parsed = _parse_range_to_floats(in_calib_range_str.strip())

        out_lut_range_str = match.group(3) # Puede ser None si no hay "OutLUTRange:"
        if out_lut_range_str:
            out_lut_range_parsed = _parse_range_to_floats(out_lut_range_str.strip())
        
        # Si InCalibRange o OutLUTRange no se encontraron explícitamente
        # y explanation_part todavía contiene las keywords, intentamos un parseo más simple
        # (Esto es un fallback, el regex debería ser el método principal)
        if in_calib_range_parsed is None and "InCalibRange:" in explanation_part:
            temp_parts = explanation_part.split("InCalibRange:", 1)
            explanation_part = temp_parts[0].strip()
            if len(temp_parts) > 1:
                temp_in_calib_parts = temp_parts[1].split("OutLUTRange:", 1)
                in_calib_range_parsed = _parse_range_to_floats(temp_in_calib_parts[0].strip())

        if out_lut_range_parsed is None and "OutLUTRange:" in explanation_part:
            temp_parts = explanation_part.split("OutLUTRange:", 1)
            # Actualizar explanation_part solo si OutLUTRange se encontró DESPUÉS de InCalibRange
            if "InCalibRange:" not in temp_parts[0]: # Evitar cortar la explicación si OutLUTRange vino primero o solo
                 explanation_part = temp_parts[0].strip()
            if len(temp_parts) > 1:
                out_lut_range_parsed = _parse_range_to_floats(temp_parts[1].strip())
    else:
        # Si el regex principal no coincide, intentamos un parseo más simple basado en split
        # Esto puede ser menos preciso si el formato de 'explanation_part' es complejo
        parts = text.split("InCalibRange:")
        explanation_part = parts[0].strip()
        if len(parts) > 1:
            remaining_parts = parts[1].split("OutLUTRange:")
            in_calib_range_parsed = _parse_range_to_floats(remaining_parts[0].strip())
            if len(remaining_parts) > 1:
                out_lut_range_parsed = _parse_range_to_floats(remaining_parts[1].strip())

    return LUTExplanationModel(
        FullText=text,
        Explanation=explanation_part if explanation_part else None,
        InCalibRange=in_calib_range_parsed,
        OutLUTRange=out_lut_range_parsed
    )

# --- Endpoints ---
# ... (tus endpoints @app.get("/") y @app.get("/studies") permanecen igual) ...
@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Consultas PACS DICOM"}

@app.get("/studies", response_model=List[StudyResponse])
async def find_studies_endpoint(
    PatientID: Optional[str] = Query(None, alias="PatientID", description="Patient ID to filter by."),
    StudyDate: Optional[str] = Query(None, alias="StudyDate", description="Study Date (YYYYMMDD or IAMMDD-YYYYMMDD range)."),
    AccessionNumber: Optional[str] = Query(None, alias="AccessionNumber", description="Accession Number."),
    ModalitiesInStudy: Optional[str] = Query(None, alias="ModalitiesInStudy", description="Modalities in Study (e.g., CT, MR)."),
):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "STUDY"
    identifier.StudyInstanceUID = ""
    identifier.PatientID = ""
    identifier.PatientName = ""
    identifier.StudyDate = ""
    identifier.StudyDescription = ""
    identifier.ModalitiesInStudy = ""
    identifier.AccessionNumber = ""

    if PatientID: identifier.PatientID = PatientID
    if StudyDate: identifier.StudyDate = StudyDate
    if AccessionNumber: identifier.AccessionNumber = AccessionNumber
    if ModalitiesInStudy: identifier.ModalitiesInStudy = ModalitiesInStudy
    
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
async def find_series_in_study(study_instance_uid: str):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "SERIES"
    identifier.StudyInstanceUID = study_instance_uid
    identifier.SeriesInstanceUID = ""
    identifier.Modality = ""
    identifier.SeriesNumber = "" 
    identifier.SeriesDescription = ""

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
                try:
                    series_number_for_pydantic = str(int(series_number_raw))
                except (ValueError, TypeError):
                    series_number_for_pydantic = str(series_number_raw)
            
            kvp_val = res_ds.get("KVP")

            response_list.append(SeriesResponse(
                StudyInstanceUID=res_ds.get("StudyInstanceUID", study_instance_uid),
                SeriesInstanceUID=res_ds.get("SeriesInstanceUID", ""),
                Modality=res_ds.get("Modality", ""),
                SeriesNumber=series_number_for_pydantic,
                SeriesDescription=res_ds.get("SeriesDescription", ""),
                KVP=str(kvp_val) if kvp_val is not None else None
            ))
        return response_list
    except Exception as e:
        logger.error(f"Error en C-FIND de series: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al consultar series: {str(e)}")

@app.get("/studies/{study_instance_uid}/series/{series_instance_uid}/instances", response_model=List[InstanceMetadataResponse])
async def find_instances_in_series(
    study_instance_uid: str,
    series_instance_uid: str,
    fields: Optional[List[str]] = Query(None, description="Lista de keywords DICOM o (gggg,eeee) a recuperar. E.g., 'PatientName' o '0010,0020'.")
):
    print(f"[find_instances_in_series] Recibido fields: {fields}") 

    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "IMAGE"
    identifier.StudyInstanceUID = study_instance_uid
    identifier.SeriesInstanceUID = series_instance_uid
    identifier.SOPInstanceUID = ""
    identifier.InstanceNumber = ""

    requested_tags_for_response: Dict[str, Tag] = {}

    if fields:
        for field_str in fields:
            tag_to_add: Optional[Tag] = None
            print(f"[find_instances_in_series] Procesando field_str: '{field_str}'") 
            try:
                if ',' in field_str:
                    group, elem = field_str.split(',')
                    tag_to_add = Tag(int(group, 16), int(elem, 16))
                    print(f"[find_instances_in_series] Convertido a Tag (gggg,eeee): {tag_to_add}")
                else:
                    tag_value_from_keyword = tag_for_keyword(field_str)
                    if tag_value_from_keyword:
                        tag_to_add = Tag(tag_value_from_keyword)
                        print(f"[find_instances_in_series] Convertido a Tag (keyword '{field_str}'): {tag_to_add}")
                    else:
                        logger.warning(f"Keyword DICOM '{field_str}' no reconocida. Omitiendo.")
                        print(f"[find_instances_in_series] Keyword '{field_str}' no reconocida.")
                        continue

                if tag_to_add:
                    try:
                        vr = dictionary_VR(tag_to_add) 
                        element_to_add = DataElement(tag_to_add, vr, "") 
                        identifier.add(element_to_add) 
                        print(f"[find_instances_in_series] Añadido DataElement explícito para {tag_to_add} con VR {vr}")
                        requested_tags_for_response[str(tag_to_add)] = tag_to_add
                    except KeyError: 
                        logger.warning(f"No se encontró VR en el diccionario para el tag {tag_to_add}. Intentando añadir con asignación directa.")
                        print(f"[find_instances_in_series] No se encontró VR para {tag_to_add}. Intentando asignación directa.")
                        try:
                            identifier[tag_to_add] = "" 
                            print(f"[find_instances_in_series] Añadido tag {tag_to_add} con asignación directa (VR inferido).")
                            requested_tags_for_response[str(tag_to_add)] = tag_to_add
                        except Exception as e_assign:
                            logger.error(f"FALLO al añadir DataElement para {tag_to_add} incluso con fallback: {e_assign}")
                            print(f"[find_instances_in_series] FALLO al añadir DataElement para {tag_to_add} incluso con fallback: {e_assign}")
            except ValueError as ve:
                logger.warning(f"Formato de tag DICOM inválido para field '{field_str}': {ve}. Omitiendo.")
                print(f"[find_instances_in_series] ValueError para field '{field_str}': {ve}. Omitiendo.")
            except Exception as e_tag: 
                logger.warning(f"Error procesando field '{field_str}' como tag DICOM: {e_tag}. Omitiendo.")
                print(f"[find_instances_in_series] Exception para field '{field_str}': {e_tag}. Omitiendo.")

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
                try:
                    instance_number_val = str(int(instance_number_raw))
                except (ValueError, TypeError):
                    instance_number_val = str(instance_number_raw)
            
            print(f"[find_instances_in_series] Procesando res_ds para SOPInstanceUID: {sop_instance_uid_val}")
            for tag_key_str, tag_obj in requested_tags_for_response.items():
                print(f"[find_instances_in_series] Verificando tag_obj: {tag_obj} ({tag_key_str}) in res_ds: {tag_obj in res_ds}")
                if tag_obj in res_ds:
                    element = res_ds[tag_obj]
                    key_to_use = element.keyword if element.keyword and isinstance(element.keyword, str) else tag_key_str
                    value_to_store: Any = None

                    if element.VR == 'SQ': 
                        print(f"[find_instances_in_series] Procesando Secuencia: {key_to_use}")
                        sequence_items = []
                        if isinstance(element.value, pydicom.sequence.Sequence):
                            for item_index, item_dataset in enumerate(element.value): 
                                item_data: Dict[str, Any] = {}
                                print(f"[find_instances_in_series]  Procesando Item #{item_index} de la secuencia {key_to_use}")
                                for item_element in item_dataset: 
                                    item_key_in_seq = item_element.keyword if item_element.keyword and isinstance(item_element.keyword, str) else str(item_element.tag)
                                    item_val_in_seq: Any = None

                                    if item_element.tag == Tag(0x0028, 0x3006): # LUT Data
                                        item_data[item_key_in_seq] = f"Binary LUT data (length {len(item_element.value) if item_element.value is not None else 0}), not included"
                                        print(f"[find_instances_in_series]    Tag {item_element.tag} ({item_key_in_seq}): LUTData (longitud: {len(item_element.value) if item_element.value is not None else 0})")
                                        continue
                                    
                                    # --- Parseo específico para LUTExplanation ---
                                    if item_element.tag == Tag(0x0028,0x3003): # LUTExplanation
                                        item_val_in_seq = parse_lut_explanation(item_element.value)
                                    # --- Fin Parseo específico para LUTExplanation ---
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
                    print(f"[find_instances_in_series] Añadido a headers: '{key_to_use}' = '{value_to_store}'")
                else:
                    missing_key_to_use = tag_for_keyword(tag_obj) if tag_for_keyword(tag_obj) else str(tag_obj)
                    headers[missing_key_to_use] = None
                    print(f"[find_instances_in_series] Tag {tag_obj} ({missing_key_to_use}) no encontrado en res_ds.")
            
            print(f"[find_instances_in_series] Headers finales para esta instancia ({sop_instance_uid_val}): {headers}")
            response_list.append(InstanceMetadataResponse(
                SOPInstanceUID=sop_instance_uid_val,
                InstanceNumber=instance_number_val,
                dicom_headers=headers
            ))
        return response_list
    except Exception as e:
        logger.error(f"Error en C-FIND de instancias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al consultar instancias: {str(e)}")