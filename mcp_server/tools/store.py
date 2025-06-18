# Tools for storing and retrieving DICOM data
import json
import logging
from typing import Optional, Dict, Any
import pydicom

from pydicom.dataset import Dataset as DicomDataset

from config import settings
from models import PixelDataResponse
import pacs_operations
from mcp_server.context import dicom_context
from mcp_utils import parse_lut_explanation # Assuming this is still needed by one of the store functions

logger = logging.getLogger(__name__)

# Copied and adapted from main_mcp.py
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
            "status_code_hex": f"0x{final_status.Status:04X}", # Corrected formatting
            "completed_suboperations": final_status.get("NumberOfCompletedSuboperations", 0),
            "failed_suboperations": final_status.get("NumberOfFailedSuboperations", 0),
            "warning_suboperations": final_status.get("NumberOfWarningSuboperations", 0)
        }
    else:
        response = {"status_code_hex": "UNKNOWN", "message": "No se recibió respuesta de estado final del PACS."}
    return json.dumps(response, indent=2)

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
                if ds.get("SamplesPerPixel", 1) == 1: # Grayscale images with multiple frames
                    rows_preview, cols_preview = min(pixel_array.shape[1], 5), min(pixel_array.shape[2], 5)
                    preview = pixel_array[0, :rows_preview, :cols_preview].tolist() # Preview first frame
                elif ds.get("SamplesPerPixel", 1) > 1 and pixel_array.shape[-1] == ds.SamplesPerPixel: # Color images
                    rows_preview, cols_preview = min(pixel_array.shape[0], 5), min(pixel_array.shape[1], 5)
                    preview = pixel_array[:rows_preview, :cols_preview, 0].tolist() # Preview first channel

        response = PixelDataResponse(
            sop_instance_uid=sop_instance_uid, rows=ds.Rows, columns=ds.Columns,
            pixel_array_shape=pixel_array.shape, pixel_array_dtype=str(pixel_array.dtype),
            pixel_array_preview=preview, message="Pixel data accessed from local file."
        )
        return response.model_dump_json(indent=2)

    except Exception as e:
        logger.error(f"Error procesando archivo local {filepath}: {e}", exc_info=True)
        return json.dumps({"error": f"Error interno procesando el archivo: {str(e)}"})
