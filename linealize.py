# linealize.py
import logging
import warnings
from typing import Dict, Optional, Tuple # Union también podría ser útil

import numpy as np
import pandas as pd
import pydicom # Para añadir tags al dataset DICOM
from pydicom.dataset import Dataset # Para type hinting explícito
from pydicom.uid import generate_uid # Para SOPInstanceUID de prueba

logger = logging.getLogger(__name__)

# --- Constantes (si son específicas de este módulo) ---
# Estos factores RQA deberían venir de config.py o ser pasados como argumento
RQA_FACTORS_EXAMPLE: Dict[str, float] = {
    "RQA5": 0.000123, # Reemplaza con tus valores reales (SNR_in^2 / 1000)
    "RQA9": 0.000456,
    # ...otros RQA...
}
EPSILON = 1e-9 # Para evitar divisiones por cero

# --- Funciones de Carga de Datos de Calibración para Linealización Física ---

def obtener_datos_calibracion_vmp_k_linealizacion(
    ruta_archivo_csv: str,
) -> Optional[pd.DataFrame]:
    """
    Carga los datos de calibración VMP vs Kerma desde un archivo CSV.

    Estos datos se utilizan para calcular la pendiente de linealización física.
    El CSV debe contener, como mínimo, las columnas 'K_uGy' y 'VMP'.

    Args:
        ruta_archivo_csv: La ruta al archivo CSV de calibración.

    Returns:
        Un DataFrame de pandas con los datos de calibración si la carga es
        exitosa, o None en caso de error o si el archivo no es válido.
    """
    try:
        # Usar pathlib para manejo de rutas es más robusto
        from pathlib import Path
        path_obj = Path(ruta_archivo_csv)
        if not path_obj.is_file():
            logger.error(f"Fichero CSV de calibración (para linealización física) no encontrado: {ruta_archivo_csv}")
            return None

        df = pd.read_csv(path_obj)
        logger.info(f"Datos de calibración VMP vs K (para linealización física) cargados desde: {ruta_archivo_csv}")
        
        required_columns = ['K_uGy', 'VMP']
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            logger.error(f"Columnas requeridas {missing} no encontradas en {ruta_archivo_csv} para linealización.")
            return None
        
        # Validar que haya datos después de eliminar NaNs en columnas críticas
        if df[required_columns].isnull().any().any():
            logger.warning(f"Valores nulos encontrados en columnas {required_columns} de {ruta_archivo_csv}. Se eliminarán esas filas.")
            df.dropna(subset=required_columns, inplace=True)
            if df.empty:
                logger.error(f"El CSV {ruta_archivo_csv} quedó vacío después de eliminar NaNs en {required_columns}.")
                return None
        
        if len(df) < 2: # Necesita al menos dos puntos para la pendiente
             logger.error(f"No hay suficientes datos válidos (se necesitan al menos 2 puntos) en {ruta_archivo_csv} para calcular la pendiente.")
             return None

        return df
    except FileNotFoundError: # Ya cubierto por Path.is_file(), pero por si acaso
        logger.error(f"Fichero CSV de calibración (para linealización física) no encontrado: {ruta_archivo_csv}")
        return None
    except pd.errors.EmptyDataError:
        logger.error(f"Fichero CSV de calibración (para linealización física) {ruta_archivo_csv} está vacío.")
        return None
    except Exception as e:
        logger.exception(f"Error al leer datos de calibración (para linealización física) desde {ruta_archivo_csv}: {e}")
        return None


# --- Funciones de Cálculo de Parámetros de Linealización ---

def calculate_linearization_slope(
    calibration_df: pd.DataFrame, 
    rqa_type: str, 
    rqa_factors_dict: Dict[str, float]
) -> Optional[float]:
    """
    Calcula la pendiente de linealización (VMP vs. quanta/area) para un RQA dado.

    La función convierte los valores de Kerma (K_uGy) del DataFrame a unidades
    de "quanta por área" usando el factor RQA proporcionado y luego calcula la
    pendiente de la relación lineal entre estos y los valores VMP.

    Args:
        calibration_df: DataFrame con los datos de calibración ('K_uGy', 'VMP').
        rqa_type: El tipo de calidad de haz (ej. "RQA5") para buscar su factor.
        rqa_factors_dict: Un diccionario que mapea tipos de RQA a sus factores de conversión.

    Returns:
        El valor de la pendiente calculada como un flotante, o None si no se
        pudo calcular.
    """
    try:
        if not isinstance(calibration_df, pd.DataFrame): raise TypeError("calibration_df debe ser DataFrame.")
        if not isinstance(rqa_factors_dict, dict): raise TypeError("rqa_factors_dict debe ser dict.")
        if rqa_type not in rqa_factors_dict: 
            logger.error(f"RQA type '{rqa_type}' no encontrado en rqa_factors_dict. Disponibles: {list(rqa_factors_dict.keys())}")
            raise ValueError(f"RQA type '{rqa_type}' no en rqa_factors_dict.")
        if not all(col in calibration_df.columns for col in ['K_uGy', 'VMP']): 
            raise ValueError("El DataFrame de calibración debe contener las columnas 'K_uGy' y 'VMP'.")

        factor_lin = rqa_factors_dict[rqa_type] 
        snr_in_squared_factor = factor_lin * 1000.0
        
        valid_cal_data = calibration_df[
            (calibration_df['K_uGy'] > EPSILON) & 
            (np.isfinite(calibration_df['VMP'])) & 
            (np.isfinite(calibration_df['K_uGy']))
        ].copy()

        if valid_cal_data.empty: 
            logger.warning(f"No hay puntos de calibración válidos (K_uGy > {EPSILON} y VMP/K_uGy finitos) para {rqa_type}.")
            return None

        valid_cal_data['quanta_per_area'] = valid_cal_data['K_uGy'] * snr_in_squared_factor
        
        x_values = valid_cal_data['quanta_per_area'].values
        y_values = valid_cal_data['VMP'].values
        
        valid_points_mask = (np.abs(x_values) > EPSILON) & np.isfinite(x_values) & np.isfinite(y_values)
        x_masked = x_values[valid_points_mask]
        y_masked = y_values[valid_points_mask]

        if len(x_masked) < 2: # Necesita al menos dos puntos para un ajuste lineal robusto
            logger.warning(f"No quedan suficientes puntos válidos ({len(x_masked)}) para el cálculo de la pendiente para {rqa_type} después de filtrar.")
            return None
        
        # Estimación de la pendiente: sum(x*y) / sum(x*x) para el modelo y = slope * x (pasa por el origen)
        slope_prime = np.sum(x_masked * y_masked) / np.sum(x_masked**2)

        if abs(slope_prime) < EPSILON:
            logger.warning(f"Pendiente de linealización calculada para {rqa_type} ({slope_prime:.2e}) es demasiado cercana a cero.")
            return None 
            
        logger.info(f"Pendiente de linealización calculada para {rqa_type}: {slope_prime:.6e}")
        return float(slope_prime)
    except Exception as e:
        logger.warning(f"No se pudo calcular la pendiente de linealización para {rqa_type}: {e}", exc_info=True)
        return None


# --- Funciones para Aplicar Linealización (a un array de píxeles, si se necesita fuera del PACS) ---

def linearize_pixel_array(
    pixel_array: np.ndarray, 
    linearization_slope: float
) -> Optional[np.ndarray]:
    """
    Linealiza un array de píxeles dividiéndolo por la pendiente de linealización.

    Esta operación convierte los valores de píxel (VMP) a una escala que es
    proporcional a los "quanta por área" incidentes.

    Args:
        pixel_array: El array de NumPy con los datos de la imagen.
        linearization_slope: La pendiente de linealización a aplicar.

    Returns:
        Un nuevo array de NumPy con los píxeles linealizados, o None si hay un error.
    """
    if not isinstance(pixel_array, np.ndarray):
        logger.error("Entrada 'pixel_array' debe ser un numpy array.")
        return None
    if not isinstance(linearization_slope, (float, np.floating)) or abs(linearization_slope) < EPSILON:
        logger.error(f"Pendiente de linealización inválida o cercana a cero: {linearization_slope}")
        return None
        
    try:
        image_float = pixel_array.astype(np.float64)
        linearized_image = image_float / linearization_slope
        logger.info("Array de píxeles linealizado (división por pendiente).")
        return linearized_image
    except Exception as e: # Captura genérica, ZeroDivisionError ya cubierto por el check de slope
        logger.exception(f"Error inesperado durante la linealización del array de píxeles: {e}")
        return None


# --- Funciones de Ayuda para VMP (si se usan para derivar la pendiente) ---

def calculate_vmp_roi(imagen: np.ndarray, halfroi: int) -> Tuple[Optional[float], Optional[float]]:
    """
    Calcula el Valor Medio de Píxel (VMP) y su desviación estándar en una ROI central.

    Define una Región de Interés (ROI) cuadrada en el centro de la imagen y
    calcula el promedio y la desviación estándar de los valores de píxel dentro de ella.

    Args:
        imagen: El array de NumPy 2D de la imagen.
        halfroi: La mitad del lado de la ROI cuadrada (el tamaño será (2*halfroi)x(2*halfroi)).

    Returns:
        Una tupla (media, std_dev) con los valores calculados, o (None, None)
        si no se pudo calcular.
    """
    try:
        if not isinstance(imagen, np.ndarray) or imagen.ndim != 2:
            logger.warning(f"Imagen para VMP no es 2D (dimensiones: {imagen.ndim}). Se devuelve None.")
            return None, None
        if halfroi <= 0:
            logger.warning(f"Tamaño de halfroi ({halfroi}) debe ser positivo. Se devuelve None.")
            return None, None
            
        img_h, img_w = imagen.shape
        centro_y, centro_x = img_h // 2, img_w // 2
        
        y_start, y_end = max(0, centro_y - halfroi), min(img_h, centro_y + halfroi)
        x_start, x_end = max(0, centro_x - halfroi), min(img_w, centro_x + halfroi)

        if y_start >= y_end or x_start >= x_end:
            logger.warning(f"ROI para VMP tiene tamaño cero o inválido: y[{y_start}:{y_end}], x[{x_start}:{x_end}]")
            return None, None
            
        roi = imagen[y_start:y_end, x_start:x_end]
        if roi.size == 0:
            logger.warning("ROI para VMP está vacía después del slicing.")
            return None, None

        vmp = np.mean(roi)
        std = np.std(roi)
        logger.debug(f"VMP ROI calculado: {vmp:.2f}, StdDev: {std:.2f}")
        return float(vmp), float(std)
    except Exception as e:
        logger.exception(f"Error al calcular VMP en ROI: {e}")
        return None, None

# --- Funciones para almacenar parámetros de linealización en DICOM ---

def add_linearization_parameters_to_dicom(
    ds: Dataset, 
    rqa_type: str, 
    linearization_slope: float,
    private_creator_id: str = "LINEALIZATION_PARAMS_RFB"
) -> Dataset:
    """
    Añade los parámetros de linealización a la cabecera DICOM usando tags privados.

    Crea un bloque de tags privados identificado por `private_creator_id` y
    almacena en él el tipo de RQA y la pendiente de linealización calculada.
    No modifica los datos de píxeles.

    Args:
        ds: El dataset de pydicom al que se añadirán los tags.
        rqa_type: El tipo de RQA (ej. "RQA5") a guardar.
        linearization_slope: El valor de la pendiente a guardar.
        private_creator_id: Un identificador único para tu bloque de datos privados.

    Returns:
        El dataset de pydicom modificado con los nuevos tags privados.
    """
    try:
        # Grupo privado (impar) para los parámetros de linealización.
        private_group = 0x00F1 
        
        # Obtener o crear el bloque privado
        block = ds.private_block(private_group, private_creator_id, create=True)
        
        # Añadir los elementos de datos al bloque privado.
        # Pydicom gestiona internamente el mapeo del offset del creador (ej. 0x10)
        # a la dirección completa del tag (ej. 0x00F1, 1010).
        block.add_new(0x10, "LO", rqa_type) # Elemento offset 0x10: RQA Type
        block.add_new(0x11, "DS", f"{linearization_slope:.8e}") # Elemento offset 0x11: Linearization Slope
        
        logger.info(f"Parámetros de linealización (RQA={rqa_type}, Pendiente={linearization_slope:.4e}) "
                    f"añadidos al dataset DICOM en bloque privado (Grupo:0x{private_group:04X}, Creador:'{private_creator_id}').")
        
    except Exception as e:
        logger.exception(f"Error añadiendo parámetros de linealización al dataset DICOM: {e}")
        # No relanzar para no detener el flujo, pero el ds no tendrá los tags.
        
    return ds


if __name__ == '__main__':
    from pathlib import Path 
    import shutil 

    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Pruebas para linealize.py ---")

    # Crear un DataFrame de calibración de ejemplo
    sample_cal_data_dict = {
        'K_uGy': [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 0.05, np.nan, 15.0], 
        'VMP':   [10,  50,  100, 200, 500, 1000, 5,    1200,   1500]  
    }
    test_csv_dir = Path("temp_linealize_test_data")
    test_csv_dir.mkdir(exist_ok=True)
    test_csv_path = test_csv_dir / "test_linearizacion_fisica.csv"
    
    temp_df_for_csv = pd.DataFrame(sample_cal_data_dict)
    temp_df_for_csv.to_csv(test_csv_path, index=False)
    logger.info(f"CSV de prueba creado en: {test_csv_path}")

    cal_df = obtener_datos_calibracion_vmp_k_linealizacion(str(test_csv_path))
    if cal_df is not None:
        print(f"\nDataFrame de calibración cargado (después de limpiar NaNs en K_uGy/VMP si aplica):\n{cal_df}")

        rqa = "RQA5" 
        slope = calculate_linearization_slope(cal_df, rqa, RQA_FACTORS_EXAMPLE)
        if slope:
            print(f"\nPendiente de linealización calculada para {rqa}: {slope:.6e}")

            test_pixel_array = np.array([[50, 100], [200, 500]], dtype=np.float32)
            linearized_arr = linearize_pixel_array(test_pixel_array, slope)
            if linearized_arr is not None:
                print(f"Array original (VMP):\n{test_pixel_array}")
                print(f"Array linealizado (quanta/area aproximado):\n{linearized_arr}")

            ds_test = Dataset()
            ds_test.PatientName = "Test^LinearizeParams"
            ds_test.SOPInstanceUID = generate_uid() 
            ds_test.file_meta = Dataset() 
            ds_test.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian

            test_private_creator_id = "MY_LIN_PARAMS"
            ds_modified = add_linearization_parameters_to_dicom(ds_test, rqa, slope, test_private_creator_id)
            print("\nDataset DICOM con parámetros de linealización:")
            
            # Verificación simplificada usando el método private_block
            private_group_test = 0x00F1
            if ds_modified.get_private_block(private_group_test, test_private_creator_id):
                block = ds_modified.private_block(private_group_test, test_private_creator_id)
                rqa_val = block.get(0x10).value
                slope_val = block.get(0x11).value
                print(f"  Bloque privado '{test_private_creator_id}' encontrado.")
                print(f"    RQA Type (tag offset 0x10): {rqa_val}")
                print(f"    Slope (tag offset 0x11): {slope_val}")
            else:
                print(f"  No se encontró el bloque privado '{test_private_creator_id}' como se esperaba.")
        else:
            print(f"\nNo se pudo calcular la pendiente para {rqa}.")
    else:
        print("\nNo se pudieron cargar los datos de calibración desde el CSV de prueba.")

    if test_csv_dir.exists():
        shutil.rmtree(test_csv_dir)
        logger.info(f"Directorio de prueba {test_csv_dir} eliminado.")