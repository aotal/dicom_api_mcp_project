# api_main.py
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional

import pydicom
from pydicom.dataset import Dataset as DicomDataset

import pacs_operations
import config

app = FastAPI(title="API de Consultas PACS DICOM", version="1.0.0")

# --- Tus modelos Pydantic (StudyResponse) y el endpoint /studies van aquí ---
class StudyResponse(BaseModel):
    StudyInstanceUID: str
    PatientID: Optional[str] = None
    PatientName: Optional[str] = None
    StudyDate: Optional[str] = None
    StudyDescription: Optional[str] = None
    ModalitiesInStudy: Optional[str] = None
    # ... otros campos relevantes

@app.get("/studies", response_model=List[StudyResponse])
async def find_studies_endpoint(
    PatientID: Optional[str] = Query(None, alias="PatientID", description="Patient ID to filter by."), # Parameter from FastAPI
    StudyDate: Optional[str] = Query(None, alias="StudyDate", description="Study Date (YYYYMMDD or YYYYMMDD-YYYYMMDD range)."), # Parameter from FastAPI
    AccessionNumber: Optional[str] = Query(None, alias="AccessionNumber", description="Accession Number."), # Parameter from FastAPI
    ModalitiesInStudy: Optional[str] = Query(None, alias="ModalitiesInStudy", description="Modalities in Study (e.g., CT, MR)."), # Parameter from FastAPI
    # ... otros parámetros de búsqueda comunes
):
    identifier = DicomDataset()
    identifier.QueryRetrieveLevel = "STUDY"

    # 1. Especifica TODOS los campos que quieres que el PACS te devuelva, inicializándolos vacíos.
    identifier.StudyInstanceUID = ""
    identifier.PatientID = ""       # Request PatientID to be returned
    identifier.PatientName = ""
    identifier.StudyDate = ""       # Request StudyDate to be returned
    identifier.StudyDescription = ""
    identifier.ModalitiesInStudy = ""
    identifier.AccessionNumber = "" # Assuming AccessionNumber is in StudyResponse and you want it back

    # 2. Ahora, si el usuario proporcionó filtros, usa esos valores para la búsqueda.
    #    Usa los nombres de los parámetros definidos en la firma de la función.
    if PatientID: # USA EL NOMBRE DEL PARÁMETRO DE FASTAPI
        identifier.PatientID = PatientID
    if StudyDate: # USA EL NOMBRE DEL PARÁMETRO DE FASTAPI
        identifier.StudyDate = StudyDate
    if AccessionNumber: # USA EL NOMBRE DEL PARÁMETRO DE FASTAPI
        identifier.AccessionNumber = AccessionNumber
    if ModalitiesInStudy: # USA EL NOMBRE DEL PARÁMETRO DE FASTAPI
        identifier.ModalitiesInStudy = ModalitiesInStudy

    pacs_config_dict = {
        "PACS_IP": config.PACS_IP,
        "PACS_PORT": config.PACS_PORT,
        "PACS_AET": config.PACS_AET,
        "AE_TITLE": config.CLIENT_AET
    }

    try:
        results_datasets = await pacs_operations.perform_c_find_async(
            identifier,
            pacs_config_dict,
            query_model_uid='S'
        )
        # ... (resto de tu código para procesar results_datasets y devolver la respuesta) ...
        response_studies: List[StudyResponse] = []
        for res_ds in results_datasets:
            response_studies.append(StudyResponse(
                StudyInstanceUID=res_ds.get("StudyInstanceUID", ""),
                PatientID=res_ds.get("PatientID", ""), # Se obtendrá el valor (o "" si no está)
                PatientName=str(res_ds.get("PatientName", "")),
                StudyDate=res_ds.get("StudyDate", ""), # Se obtendrá el valor (o "" si no está)
                StudyDescription=res_ds.get("StudyDescription", ""),
                ModalitiesInStudy=res_ds.get("ModalitiesInStudy", ""),
                # AccessionNumber=res_ds.get("AccessionNumber", "") # Si lo añadiste a StudyResponse
            ))
        return response_studies
    except Exception as e:
        logger.error(f"Error en C-FIND de estudios: {e}", exc_info=True) # Asegúrate de tener 'logger' definido
        raise HTTPException(status_code=500, detail=f"Internal server error during PACS query: {str(e)}")
    
# --- ASEGÚRATE DE QUE ESTE ENDPOINT ESTÉ PRESENTE Y DESCOMENTADO ---
@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Consultas PACS DICOM"}
# --------------------------------------------------------------------