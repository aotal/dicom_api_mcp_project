# api_main.py
import logging
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, List, Optional, Dict

import pydicom # Necesario para DicomDataset si no, pydicom.dataset.Dataset
from pydicom.tag import Tag
from pydicom.dataset import Dataset as DicomDataset # Alias para claridad

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
    AccessionNumber: Optional[str] = None # Añadido basado en tu endpoint

class SeriesResponse(BaseModel):
    StudyInstanceUID: str
    SeriesInstanceUID: str
    Modality: Optional[str] = None
    SeriesNumber: Optional[str] = None
    SeriesDescription: Optional[str] = None
    # BodyPartExamined: Optional[str] = None
    # Laterality: Optional[str] = None
    # NumberOfSeriesRelatedInstances: Optional[str] = None # Debería ser str si lo conviertes

class InstanceMetadataResponse(BaseModel):
    SOPInstanceUID: str
    InstanceNumber: Optional[str] = None
    dicom_headers: Dict[str, Any]

# --- Endpoints ---

@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Consultas PACS DICOM"}

@app.get("/studies", response_model=List[StudyResponse])
async def find_studies_endpoint(
    PatientID: Optional[str] = Query(None, alias="PatientID", description="Patient ID to filter by."),
    StudyDate: Optional[str] = Query(None, alias="StudyDate", description="Study Date (YYYYMMDD or YYYYMMDD-YYYYMMDD range)."),
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

    if PatientID:
        identifier.PatientID = PatientID
    if StudyDate:
        identifier.StudyDate = StudyDate
    if AccessionNumber:
        identifier.AccessionNumber = AccessionNumber
    if ModalitiesInStudy:
        identifier.ModalitiesInStudy = ModalitiesInStudy
    
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
                PatientName=str(res_ds.get("PatientName", "")), # PersonName a str
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
    identifier.SeriesNumber = "" # Solicitamos que el PACS devuelva este campo
    identifier.SeriesDescription = ""
    # identifier.BodyPartExamined = ""
    # identifier.Laterality = ""
    # identifier.NumberOfSeriesRelatedInstances = "" # (0020,1209) tiene VR IS

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
                    # IS (Integer String) puede ser directamente convertido a int, luego a str.
                    series_number_for_pydantic = str(int(series_number_raw))
                except (ValueError, TypeError):
                    # Si falla la conversión a int (poco probable para '1', pero como fallback)
                    series_number_for_pydantic = str(series_number_raw)
            
            response_list.append(SeriesResponse(
                StudyInstanceUID=res_ds.get("StudyInstanceUID", study_instance_uid),
                SeriesInstanceUID=res_ds.get("SeriesInstanceUID", ""),
                Modality=res_ds.get("Modality", ""),
                SeriesNumber=series_number_for_pydantic, # Usar el valor procesado
                SeriesDescription=res_ds.get("SeriesDescription", "")
                # BodyPartExamined=str(res_ds.get("BodyPartExamined","")) if res_ds.get("BodyPartExamined") is not None else None,
                # Laterality=str(res_ds.get("Laterality","")) if res_ds.get("Laterality") is not None else None,
                # NumberOfSeriesRelatedInstances_raw = res_ds.get((0x0020,0x1209)) # Ejemplo con tag numérico
                # NumberOfSeriesRelatedInstances = str(int(NumberOfSeriesRelatedInstances_raw)) if NumberOfSeriesRelatedInstances_raw is not None else None
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
                    from pydicom.datadict import tag_for_keyword
                    tag_value_from_keyword = tag_for_keyword(field_str)
                    if tag_value_from_keyword:
                        tag_to_add = Tag(tag_value_from_keyword)
                        print(f"[find_instances_in_series] Convertido a Tag (keyword '{field_str}'): {tag_to_add}")
                    else:
                        logger.warning(f"Keyword DICOM '{field_str}' no reconocida. Omitiendo.")
                        print(f"[find_instances_in_series] Keyword '{field_str}' no reconocida.")
                        continue

                if tag_to_add:
                    # --- MODIFICACIÓN AQUÍ ---
                    # En lugar de: identifier[tag_to_add] = ""
                    # Crear y añadir el DataElement explícitamente:
                    try:
                        vr = dictionary_VR(tag_to_add) # Obtener el VR del diccionario DICOM
                        element = DataElement(tag_to_add, vr, "") # Crear DataElement con valor vacío
                        identifier.add(element) # Añadir el elemento al dataset
                        print(f"[find_instances_in_series] Añadido DataElement explícito para {tag_to_add} con VR {vr}")
                        requested_tags_for_response[str(tag_to_add)] = tag_to_add
                    except KeyError: # Si el tag no está en el diccionario (tag privado no estándar)
                        logger.warning(f"No se encontró VR en el diccionario para el tag {tag_to_add}. Intentando añadir con VR 'UN' o pydicom decidirá.")
                        # Como fallback, pydicom podría intentar adivinar o usar UN para cadenas vacías,
                        # o podrías asignar un VR por defecto si lo conoces para tags privados.
                        # Esta línea podría seguir dando problemas si pydicom no puede manejar `identifier[tag_to_add] = ""` para tags desconocidos sin VR.
                        # Para tags conocidos, lo anterior (con dictionary_VR) es más robusto.
                        # Para simplificar, si dictionary_VR falla, podríamos omitir o intentar la asignación directa:
                        try:
                            identifier[tag_to_add] = "" # Intento de asignación directa como fallback
                            print(f"[find_instances_in_series] Añadido tag {tag_to_add} con asignación directa (VR inferido).")
                            requested_tags_for_response[str(tag_to_add)] = tag_to_add
                        except Exception as e_assign:
                            logger.error(f"FALLO al añadir DataElement para {tag_to_add} incluso con fallback: {e_assign}")
                            print(f"[find_instances_in_series] FALLO al añadir DataElement para {tag_to_add} incluso con fallback: {e_assign}")


            except ValueError as ve:
                logger.warning(f"Formato de tag DICOM inválido para field '{field_str}': {ve}. Omitiendo.")
                print(f"[find_instances_in_series] ValueError para field '{field_str}': {ve}. Omitiendo.")
            except Exception as e_tag: # Captura más genérica
                logger.warning(f"Error procesando field '{field_str}' como tag DICOM: {e_tag}. Omitiendo.")
                print(f"[find_instances_in_series] Exception para field '{field_str}': {e_tag}. Omitiendo.")


    print(f"[find_instances_in_series] Identificador C-FIND final para instancias:\n{identifier}")
    print(f"[find_instances_in_series] Tags solicitados para respuesta (requested_tags_for_response): {requested_tags_for_response}")

    # ... (el resto de la función: llamada a pacs_operations.perform_c_find_async, procesamiento de resultados) ...
    # Esta parte del código (procesamiento de results_datasets para poblar dicom_headers)
    # debería funcionar bien una vez que requested_tags_for_response se popule correctamente
    # y el PACS devuelva los tags.
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
                    if element.VR == 'PN':
                        value_to_store = str(element.value) if element.value else ""
                    elif element.VR in ['DA', 'DT', 'TM']:
                        value_to_store = str(element.value) if element.value else ""
                    elif element.VR == 'IS':
                        if isinstance(element.value, list):
                            value_to_store = [str(int(v)) for v in element.value]
                        elif element.value is not None:
                             value_to_store = str(int(element.value))
                    elif element.VR == 'DS':
                        if isinstance(element.value, list):
                            value_to_store = [str(float(v)) for v in element.value]
                        elif element.value is not None:
                            value_to_store = str(float(element.value))
                    elif element.value is None:
                        value_to_store = None # Ya es None
                    else:
                        value_to_store = str(element.value)
                    
                    headers[key_to_use] = value_to_store
                    print(f"[find_instances_in_series] Añadido a headers: '{key_to_use}' = '{value_to_store}'")
                else:
                    missing_key_to_use = pydicom.datadict.keyword_for_tag(tag_obj) if pydicom.datadict.keyword_for_tag(tag_obj) else tag_key_str
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

# --- ASEGÚRATE DE QUE ESTE ENDPOINT ESTÉ PRESENTE Y DESCOMENTADO ---
@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Consultas PACS DICOM"}
# --------------------------------------------------------------------    