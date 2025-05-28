# models.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Tuple

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
    InCalibRange: Optional[Tuple[float, float]] = None
    OutLUTRange: Optional[Tuple[float, float]] = None

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
    ImageComments: Optional[str] = None