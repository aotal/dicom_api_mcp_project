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
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

try:
    os.makedirs(config.DICOM_RECEIVED_DIR, exist_ok=True)
except Exception as e:
    logger.error(f"No se pudo crear el directorio de recepción DICOM: {e}")


def handle_store(event):
    """Manejador para el evento evt.EVT_C_STORE en el SCP receptor."""
    try:
        ds = event.dataset
        
        if not hasattr(ds, 'SOPInstanceUID'):
            logger.error("Dataset C-STORE recibido no tiene SOPInstanceUID.")
            return 0xA801

        # --- INICIO: LÓGICA CORREGIDA PARA CONSTRUIR FILE_META ---
        # Crear un nuevo objeto FileMetaDataset para asegurar que tenemos control total.
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = ds.SOPClassUID
        meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
        meta.ImplementationVersionName = "PYNETDICOM_2_SCP"
        # La información más importante: la Sintaxis de Transferencia negociada
        meta.TransferSyntaxUID = event.context.transfer_syntax
        
        # Asignar los metadatos construidos al dataset
        ds.file_meta = meta
        
        # Indicar a pydicom cómo interpretar los datos binarios recibidos
        ds.is_little_endian = meta.TransferSyntaxUID.is_little_endian
        ds.is_implicit_VR = meta.TransferSyntaxUID.is_implicit_VR
        # --- FIN: LÓGICA CORREGIDA ---

        filename = ds.SOPInstanceUID + ".dcm"
        filepath = os.path.join(config.DICOM_RECEIVED_DIR, filename)
        
        # La opción 'enforce_file_format=True' es la forma moderna en pydicom
        # para asegurar que se escribe un archivo DICOM Parte 10 completo y válido.
        ds.save_as(filepath, enforce_file_format=True)
        
        logger.info(f"Archivo DICOM recibido y guardado: {filepath} (SOPClass: {ds.SOPClassUID})")
        print(f"[DICOM_SCP] Archivo DICOM recibido: {filepath} (SOPInstanceUID: {ds.SOPInstanceUID})")

        return 0x0000 # Éxito
    except Exception as e:
        sop_uid_for_log = "UID_DESCONOCIDO"
        if hasattr(event, 'dataset') and hasattr(event.dataset, 'SOPInstanceUID'):
            sop_uid_for_log = event.dataset.SOPInstanceUID
        logger.error(f"Error al manejar C-STORE para SOPInstanceUID '{sop_uid_for_log}': {e}", exc_info=True)
        print(f"[DICOM_SCP] Error al manejar C-STORE para SOPInstanceUID '{sop_uid_for_log}': {e}")
        return 0xC001 # Error: No se puede procesar

def handle_echo(event):
    """Manejador para el evento evt.EVT_C_ECHO."""
    logger.info(f"Recibido C-ECHO de {event.assoc.ae.calling_ae_title} en {event.assoc.ae.address}:{event.assoc.ae.port}")
    print(f"[DICOM_SCP] Recibido C-ECHO de {event.assoc.ae.calling_ae_title}")
    return 0x0000 

handlers = [
    (evt.EVT_C_STORE, handle_store),
    (evt.EVT_C_ECHO, handle_echo)
]

ae_scp = AE(ae_title=config.API_SCP_AET)

# Usando el método para añadir contextos que te funcionó
for context in AllStoragePresentationContexts:
    ae_scp.add_supported_context(context.abstract_syntax, ALL_TRANSFER_SYNTAXES)
ae_scp.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)

def start_scp_server():
    """Inicia el servidor C-STORE SCP. Esta función es bloqueante."""
    host = "0.0.0.0"
    port = config.API_SCP_PORT
    
    logger.info(f"Iniciando servidor C-STORE SCP en {host}:{port} con AET: {ae_scp.ae_title}")
    print(f"[DICOM_SCP] Iniciando servidor C-STORE SCP en {host}:{port} con AET: {ae_scp.ae_title}")
    
    try:
        ae_scp.start_server((host, port), block=True, evt_handlers=handlers)
    except Exception as e:
        logger.error(f"Error fatal al iniciar o durante la ejecución del servidor SCP: {e}", exc_info=True)
        print(f"[DICOM_SCP] Error fatal del servidor SCP: {e}")
    finally:
        logger.info("Servidor SCP detenido.")
        print("[DICOM_SCP] Servidor SCP detenido.")

if __name__ == "__main__":
    print("Ejecutando dicom_scp.py directamente para pruebas de SCP...")
    start_scp_server()