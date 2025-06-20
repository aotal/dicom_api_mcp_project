# dicomweb_operations.py

import httpx
import logging
import os
import json
from email import message_from_bytes
from email.message import Message
from typing import List, Dict, Any

# Importamos la configuración que definimos en el paso anterior
from config import settings

logger = logging.getLogger(__name__)

async def query_pacs(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Realiza una consulta QIDO-RS (búsqueda) al PACS. 

    Args:
        params: Un diccionario de parámetros de consulta DICOM (ej. {"PatientName": "DOE^JOHN"}). 

    Returns:
        Una lista de resultados en formato JSON. 
    """
    # Construye la URL para QIDO-RS (búsqueda de estudios)
    qido_url = f"{settings.pacs.base_url}/aets/{settings.pacs.aet}/rs/studies"
    headers = {"Accept": "application/dicom+json"}
    logger.info(f"Ejecutando consulta QIDO-RS a: {qido_url} con params: {params}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(qido_url, params=params, headers=headers, timeout=30.0)
            response.raise_for_status()  # Lanza una excepción para errores HTTP (4xx o 5xx)
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Error en la consulta QIDO-RS: {e.response.status_code} - {e.response.text}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Error de conexión durante la consulta QIDO-RS: {e}")
        return []

async def retrieve_study_wado(study_uid: str, output_dir: str = "./dicom_received") -> bool:
    """
    Recupera un estudio completo usando WADO-RS (descarga) y lo guarda en disco. 

    Args:
        study_uid: El Study Instance UID del estudio a recuperar. 
        output_dir: El directorio donde se guardarán los ficheros. 

    Returns:
        True si la descarga fue exitosa, False en caso contrario. 
    """
    # Construye la URL para WADO-RS (recuperación de un estudio completo)
    wado_url = f"{settings.pacs.base_url}/aets/{settings.pacs.aet}/rs/studies/{study_uid}"
    headers = {"Accept": 'multipart/related; type="application/dicom"'}
    logger.info(f"Iniciando descarga WADO-RS para el estudio: {study_uid}")

    try:
        async with httpx.AsyncClient() as client:
            # Usamos un stream para manejar respuestas grandes (múltiples imágenes)
            async with client.stream("GET", wado_url, headers=headers, timeout=120.0) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type")

                if not content_type or "multipart/related" not in content_type:
                    logger.error(f"Respuesta inesperada. Content-Type no es multipart/related: {content_type}")
                    return False

                # La librería 'email' es excelente para parsear respuestas multipart
                full_response_bytes = f"Content-Type: {content_type}\\r\\n\\r\\n".encode('utf-8') + await response.aread()
                multipart_message: Message = message_from_bytes(full_response_bytes)
                os.makedirs(output_dir, exist_ok=True)
                instance_count = 0

                if not multipart_message.is_multipart():
                    logger.error("La respuesta no es un mensaje multipart válido.")
                    return False

                # Iteramos sobre cada "parte" del mensaje multipart
                for part in multipart_message.get_payload():
                    if part.get_content_type() == "application/dicom":
                        dicom_bytes = part.get_payload(decode=True)
                        
                        # Guardamos cada instancia DICOM en un fichero
                        instance_count += 1
                        filepath = os.path.join(output_dir, f'{study_uid}_{instance_count}.dcm')
                        with open(filepath, 'wb') as f:
                            f.write(dicom_bytes)
                        logger.info(f"Instancia DICOM guardada en: {filepath}")

                if instance_count == 0:
                    logger.warning("La solicitud WADO fue exitosa pero no se encontraron instancias DICOM.")
                
                return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Error en la solicitud WADO-RS: {e.response.status_code} - {e.response.text}")
        return False
    except httpx.RequestError as e:
        logger.error(f"Error de conexión durante la recuperación WADO-RS: {e}")
        return False