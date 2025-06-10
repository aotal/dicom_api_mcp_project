# models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple

class StudyResponse(BaseModel):
    """
    Representa la información de un Estudio DICOM devuelta por una consulta.
    """
    StudyInstanceUID: str
    PatientID: Optional[str] = None
    PatientName: Optional[str] = None
    StudyDate: Optional[str] = None
    StudyDescription: Optional[str] = None
    ModalitiesInStudy: Optional[str] = None
    AccessionNumber: Optional[str] = None

class LUTExplanationModel(BaseModel):
    """
    Modela la información extraída del tag LUTExplanation (0028,3003).
    """
    FullText: Optional[str] = Field(None, description="El texto completo y original del tag.")
    Explanation: Optional[str] = Field(None, description="La parte puramente descriptiva del texto.")
    InCalibRange: Optional[Tuple[float, float]] = Field(None, description="Rango de valores de entrada de la calibración (min, max).")
    OutLUTRange: Optional[Tuple[float, float]] = Field(None, description="Rango de valores de salida de la LUT (min, max).")

class InstanceMetadataResponse(BaseModel):
    """
    Representa los metadatos de una Instancia DICOM específica.
    """
    SOPInstanceUID: str
    InstanceNumber: Optional[str] = None
    dicom_headers: Dict[str, Any] = Field({}, description="Un diccionario con los tags y valores de la cabecera DICOM solicitados.")

class SeriesResponse(BaseModel): 
    """
    Representa la información de una Serie DICOM dentro de un estudio.
    """
    StudyInstanceUID: str
    SeriesInstanceUID: str
    Modality: Optional[str] = None
    SeriesNumber: Optional[str] = None
    SeriesDescription: Optional[str] = None

class PixelDataResponse(BaseModel):
    """
    Representa los datos de píxeles extraídos de una instancia DICOM.
    """
    sop_instance_uid: str
    rows: int
    columns: int
    pixel_array_shape: Tuple[int, ...] = Field(..., description="La forma (shape) del array de píxeles según NumPy.")
    pixel_array_dtype: str = Field(..., description="El tipo de dato (dtype) del array de píxeles.")
    pixel_array_preview: Optional[List[List[Any]]] = Field(None, description="Una pequeña matriz de previsualización de los datos de píxeles.")
    message: Optional[str] = None

class MoveRequest(BaseModel):
    """
    Modela una solicitud de C-MOVE para una jerarquía DICOM (estudio, serie o instancia).
    """
    study_instance_uid: str
    series_instance_uid: Optional[str] = None
    sop_instance_uid: Optional[str] = None # Para mover una instancia específica
    # El destino será el AET de nuestro propio SCP
    # destination_aet: str # No es necesario si siempre es nuestro propio SCP    

class IndividualInstanceMoveRequest(BaseModel):
    """
    Define los identificadores necesarios para mover una única instancia DICOM específica.
    """
    study_instance_uid: str = Field(..., description="Study Instance UID de la instancia a mover.")
    series_instance_uid: str = Field(..., description="Series Instance UID de la instancia a mover.")
    sop_instance_uid: str = Field(..., description="SOP Instance UID de la instancia específica a mover.")

class BulkMoveRequest(BaseModel):
    """
    Modela una solicitud de C-MOVE para mover una lista de instancias DICOM específicas.
    """
    instances_to_move: List[IndividualInstanceMoveRequest] = Field(..., description="Lista de instancias específicas a mover.")
    # Opcionalmente, podrías añadir aquí el AET de destino si fuese dinámico,
    # pero según tu config.py, es fijo.
    # destination_aet: Optional[str] = None 

# Asegúrate de que el MoveRequest original se mantiene o se elimina/reemplaza según tu necesidad.
# Si quieres mantener la funcionalidad de mover un estudio/serie completo con el endpoint antiguo,
# puedes crear un nuevo endpoint para el movimiento masivo de instancias.