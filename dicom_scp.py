# dicom_scp.py
import logging
from pathlib import Path
from pynetdicom import AE, evt, AllStoragePresentationContexts, ALL_TRANSFER_SYNTAXES
from pynetdicom.sop_class import Verification
import pydicom
from pydicom.dataset import FileMetaDataset

# Configuración del logger. No depende de config.py
logger = logging.getLogger("dicom_scp")
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Variable global para que el hilo principal pueda acceder a la instancia AE para apagarla.
# Se asignará dentro de start_scp_server.
ae_scp = None

def handle_echo(event):
    """
    Manejador para el evento C-ECHO (evt.EVT_C_ECHO) del SCP.
    Responde a las solicitudes de verificación (ping) de un SCU.
    No depende de ninguna configuración externa.
    """
    calling_ae = getattr(event.assoc.ae, 'calling_ae_title', 'Desconocido')
    logger.info(f"Recibido C-ECHO de {calling_ae}")
    return 0x0000 

def start_scp_server(aet: str, port: int, storage_dir: Path):
    """
    Inicia el servidor DICOM C-STORE SCP (Service Class Provider).

    Esta función es bloqueante y está diseñada para ser ejecutada en un hilo
    separado. Escucha en el host y puerto especificados para recibir
    imágenes DICOM. Toda la configuración se pasa a través de argumentos.

    Args:
        aet (str): El AE Title que este servidor SCP usará.
        port (int): El puerto en el que el servidor escuchará.
        storage_dir (Path): El directorio (objeto Path) donde se guardarán los
                            archivos DICOM recibidos.
    """
    global ae_scp
    
    # --- Manejador de C-STORE anidado (clausura) ---
    # Se define aquí para tener acceso a 'storage_dir' de forma segura.
    def handle_store(event):
        """
        Manejador para el evento C-STORE (evt.EVT_C_STORE) del SCP.
        Guarda el dataset DICOM recibido en el 'storage_dir' proporcionado.
        """
        try:
            ds = event.dataset
            
            if not hasattr(ds, 'SOPInstanceUID'):
                logger.error("Dataset C-STORE recibido no tiene SOPInstanceUID.")
                return 0xA801 # Processing failure

            # Crear metadatos del fichero
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = ds.SOPClassUID
            meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
            meta.ImplementationVersionName = "PYNETDICOM_SCP_3" # Versión actualizada
            meta.TransferSyntaxUID = event.context.transfer_syntax
            
            ds.file_meta = meta
            ds.is_little_endian = meta.TransferSyntaxUID.is_little_endian
            ds.is_implicit_VR = meta.TransferSyntaxUID.is_implicit_VR

            # Usar el objeto Path para construir la ruta del fichero
            filename = ds.SOPInstanceUID + ".dcm"
            filepath = storage_dir / filename
            
            # Guardar el fichero
            ds.save_as(filepath, enforce_file_format=True)
            
            logger.info(f"Archivo DICOM recibido y guardado: {filepath}")
            return 0x0000 # Éxito
        except Exception as e:
            sop_uid_for_log = getattr(event.dataset, 'SOPInstanceUID', 'UID_DESCONOCIDO')
            logger.error(f"Error al manejar C-STORE para SOPInstanceUID '{sop_uid_for_log}': {e}", exc_info=True)
            return 0xC001 # Error: No se puede procesar

    # --- Configuración y arranque del servidor ---
    
    # Asignar a la variable global para control externo (apagado)
    ae_scp = AE(ae_title=aet)

    # Añadir los contextos de presentación soportados
    # Soportar todos los SOP Classes de almacenamiento y el de verificación (C-ECHO)
    for context in AllStoragePresentationContexts:
        ae_scp.add_supported_context(context.abstract_syntax, ALL_TRANSFER_SYNTAXES)
    ae_scp.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)

    # Definir los manejadores de eventos
    handlers = [
        (evt.EVT_C_STORE, handle_store),
        (evt.EVT_C_ECHO, handle_echo)
    ]
    
    host = "0.0.0.0" # Escuchar en todas las interfaces de red
    
    logger.info(f"Iniciando servidor C-STORE SCP en {host}:{port} con AET: {aet}")
    logger.info(f"Los archivos recibidos se guardarán en: {storage_dir}")
    
    try:
        # Iniciar el servidor (bloqueante)
        ae_scp.start_server((host, port), block=True, evt_handlers=handlers)
    except Exception as e:
        logger.error(f"Error fatal al iniciar o durante la ejecución del servidor SCP: {e}", exc_info=True)
    finally:
        logger.info("Servidor SCP detenido.")

# Este bloque permite ejecutar el script directamente para pruebas rápidas
if __name__ == "__main__":
    print("Ejecutando dicom_scp.py directamente para pruebas de SCP...")
    
    # Crear un directorio de prueba
    test_storage_dir = Path("./dicom_received_test")
    test_storage_dir.mkdir(exist_ok=True)
    
    # Definir parámetros de prueba
    test_aet = "PYNETDICOM_TEST"
    test_port = 11112
    
    print(f"AE Title: {test_aet}")
    print(f"Puerto: {test_port}")
    print(f"Directorio de almacenamiento: {test_storage_dir.resolve()}")
    
    # Llamar a la función con los parámetros de prueba
    start_scp_server(aet=test_aet, port=test_port, storage_dir=test_storage_dir)