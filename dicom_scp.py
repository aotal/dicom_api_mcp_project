# dicom_scp.py
import os
import logging
# Usando el bloque de importación que has confirmado que funciona
from pynetdicom import AE, evt, AllStoragePresentationContexts, ALL_TRANSFER_SYNTAXES
from pynetdicom.sop_class import Verification
import pydicom
from pydicom.dataset import FileMetaDataset

try:
    import config
except ModuleNotFoundError:
    class ConfigMock:
        API_SCP_AET = "TEST_SCP_DIRECT"
        API_SCP_PORT = 11115
        DICOM_RECEIVED_DIR = "dicom_received_test_direct"
    config = ConfigMock()
    print("ADVERTENCIA: Usando configuración mock para dicom_scp.py.")

logger = logging.getLogger("dicom_scp")
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

try:
    # Asegurarse de que config.DICOM_RECEIVED_DIR sea un objeto Path
    from pathlib import Path
    dicom_dir = Path(config.DICOM_RECEIVED_DIR)
    dicom_dir.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.error(f"No se pudo crear el directorio de recepción DICOM: {e}")


def handle_store(event):
    """Manejador para el evento evt.EVT_C_STORE en el SCP receptor."""
    try:
        ds = event.dataset
        
        if not hasattr(ds, 'SOPInstanceUID'):
            logger.error("Dataset C-STORE recibido no tiene SOPInstanceUID.")
            return 0xA801 # Processing failure

        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = ds.SOPClassUID
        meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
        meta.ImplementationVersionName = "PYNETDICOM_SCP_2"
        meta.TransferSyntaxUID = event.context.transfer_syntax
        
        ds.file_meta = meta
        ds.is_little_endian = meta.TransferSyntaxUID.is_little_endian
        ds.is_implicit_VR = meta.TransferSyntaxUID.is_implicit_VR

        filename = ds.SOPInstanceUID + ".dcm"
        filepath = os.path.join(config.DICOM_RECEIVED_DIR, filename)
        
        ds.save_as(filepath, enforce_file_format=True)
        
        logger.info(f"Archivo DICOM recibido y guardado: {filepath}")
        return 0x0000 # Éxito
    except Exception as e:
        sop_uid_for_log = getattr(event.dataset, 'SOPInstanceUID', 'UID_DESCONOCIDO')
        logger.error(f"Error al manejar C-STORE para SOPInstanceUID '{sop_uid_for_log}': {e}", exc_info=True)
        return 0xC001 # Error: No se puede procesar

def handle_echo(event):
    """Manejador para el evento evt.EVT_C_ECHO."""
    calling_ae = getattr(event.assoc.ae, 'calling_ae_title', 'Desconocido')
    logger.info(f"Recibido C-ECHO de {calling_ae}")
    return 0x0000 

handlers = [
    (evt.EVT_C_STORE, handle_store),
    (evt.EVT_C_ECHO, handle_echo)
]

ae_scp = AE(ae_title=config.API_SCP_AET)

for context in AllStoragePresentationContexts:
    ae_scp.add_supported_context(context.abstract_syntax, ALL_TRANSFER_SYNTAXES)
ae_scp.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)

# CORRECCIÓN: La función ahora acepta un 'callback' opcional
def start_scp_server(callback=None):
    """
    Inicia el servidor C-STORE SCP. Esta función es bloqueante.
    Si se proporciona un callback, se llama con la instancia del servidor AE.
    """
    host = "0.0.0.0"
    port = config.API_SCP_PORT
    
    logger.info(f"Iniciando servidor C-STORE SCP en {host}:{port} con AET: {ae_scp.ae_title}")
    
    # CORRECCIÓN: Llamar al callback con la instancia del servidor para que el
    # hilo principal pueda acceder a ella y detenerla limpiamente.
    if callback:
        callback(ae_scp)
    
    try:
        ae_scp.start_server((host, port), block=True, evt_handlers=handlers)
    except Exception as e:
        logger.error(f"Error fatal al iniciar o durante la ejecución del servidor SCP: {e}", exc_info=True)
    finally:
        logger.info("Servidor SCP detenido.")

if __name__ == "__main__":
    print("Ejecutando dicom_scp.py directamente para pruebas de SCP...")
    start_scp_server()