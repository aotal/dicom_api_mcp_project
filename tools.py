# tools.py
import httpx
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, AsyncIterator

import pydicom
from fastapi import FastAPI, HTTPException, Request
from pydicom.dataset import Dataset as DicomDataset
from pydicom.tag import Tag
from pydicom.datadict import tag_for_keyword, keyword_for_tag
from pydicom.multival import MultiValue

from config import settings
import pacs_operations # <--- CORRECCIÓN DE NOMBRE
import dicom_scp
from models import (
    StudyResponse, SeriesResponse, InstanceMetadataResponse, PixelDataResponse
)
from mcp_utils import parse_lut_explanation

# --- Configuración del Logger ---
logging.basicConfig(level=settings.logging.level, format=settings.logging.format, force=True)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Dict[str, DicomToolContext]]:
    global scp_thread
    logger.info("Iniciando la aplicación y el servidor DICOM C-STORE SCP...")
    
    scp_thread = threading.Thread(
        target=dicom_scp.start_scp_server,
        args=(
            settings.gateway.local_scp.aet,
            settings.gateway.local_scp.port,
            settings.gateway.local_scp.storage_dir
        ),
        daemon=True
    )
    scp_thread.start()
    
    context = DicomToolContext(
        pacs_config={
            "PACS_IP": settings.gateway.pacs_node.ip, "PACS_PORT": settings.gateway.pacs_node.port,
            "PACS_AET": settings.gateway.pacs_node.aet, "AE_TITLE": settings.gateway.client_ae.aet
        },
        move_destination_aet=settings.gateway.local_scp.aet
    )
    
    try:
        yield {"dicom_context": context}
    finally:
        logger.info("Deteniendo la aplicación...")
        if hasattr(dicom_scp, 'ae_scp') and dicom_scp.ae_scp and dicom_scp.ae_scp.is_running:
            logger.info("Solicitando apagado del servidor SCP...")
            dicom_scp.ae_scp.shutdown()
        
        if scp_thread and scp_thread.is_alive():
            logger.info("Esperando que el hilo del SCP termine...")
            scp_thread.join(timeout=10.0)
            if scp_thread.is_alive():
                logger.warning("Advertencia: El hilo del servidor SCP no terminó limpiamente.")
        logger.info("Apagado del servidor completado.")


def dicom_tools(mcp):
    """
    Registers all the tools for the MCP server.
    """

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers"""
        return a + b


    @mcp.tool()
    async def obtener_clima(ciudad: str) -> str:
        """
        Obtiene el pronóstico del tiempo actual para una ciudad específica.
        Utiliza la API pública de wttr.in.
        :param ciudad: El nombre de la ciudad, por ejemplo, 'Madrid' o 'Buenos Aires'.
        """
        url = f"https://wttr.in/{ciudad}?format=%C+%t"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                response.raise_for_status()  # Lanza una excepción para códigos de error HTTP
                return response.text
            except httpx.HTTPStatusError as e:
                return f"Error al obtener el clima: {e.response.status_code}"
    @mcp.tool()
    
    async def query_series(
        study_instance_uid: str,
        additional_filters: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Busca todas las series DICOM que pertenecen a un estudio específico.

        Utiliza esta herramienta cuando tengas el UID de un estudio y necesites listar
        las series que contiene, como diferentes tipos de escaneos (T1, T2, etc.).

        :param study_instance_uid: El identificador único (StudyInstanceUID) del estudio a consultar. Es un campo obligatorio.
        :param additional_filters: (Opcional) Un diccionario para aplicar filtros adicionales a nivel de serie, como la modalidad (e.g., {"Modality": "MR"}).
        :return: Un string en formato JSON con la lista de las series encontradas para el estudio dado.
        """
        if not dicom_context:
            return json.dumps({"error": "El contexto DICOM no está inicializado."})

        identifier = DicomDataset()
        identifier.QueryRetrieveLevel = "SERIES"
        identifier.StudyInstanceUID = study_instance_uid
        # Solicitar campos específicos para la respuesta
        for kw in ["SeriesInstanceUID", "Modality", "SeriesNumber", "SeriesDescription"]:
            setattr(identifier, kw, "")

        if additional_filters:
            for key, value in additional_filters.items():
                try:
                    tag = Tag(key) if ',' in str(key) else Tag(tag_for_keyword(str(key)))
                    keyword = keyword_for_tag(tag)
                    if keyword:
                        setattr(identifier, keyword, value)
                    else:
                        identifier[tag] = value
                except Exception:
                    logger.warning(f"No se pudo procesar el filtro de serie '{key}'.")

        logger.info(f"Ejecutando query_series con el identificador:\n{identifier}")
        pacs_config = dicom_context.pacs_config
        results = await pacs_operations.perform_c_find_async(identifier, pacs_config, query_model_uid='S')
        
        # Validar los datos con el modelo Pydantic y serializarlos a un string JSON
        response_data = [SeriesResponse.model_validate(ds, from_attributes=True).model_dump() for ds in results]
        return json.dumps(response_data, indent=2)    