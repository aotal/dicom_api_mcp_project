# utils.py (o el contenido que debe quedar en api_main.py)

import re
import logging
from typing import Optional, Tuple, Any
from models import LUTExplanationModel # Asegúrate de que models.py tiene esta clase

logger = logging.getLogger(__name__)

def _parse_range_to_floats(range_str: Optional[str]) -> Optional[Tuple[float, float]]:
    """
    Parsea una cadena que representa un rango (ej. "1.0-5.5" o "10") a una tupla de flotantes.

    Args:
        range_str: La cadena a parsear.

    Returns:
        Una tupla (min, max) si el parseo es exitoso, o None en caso contrario. 
        Si la cadena contiene un solo número, devuelve (num, num).
    """
    if not range_str: return None
    try:
        parts = range_str.strip().split('-')
        if len(parts) == 1:
            val = float(parts[0].strip())
            return (val, val)
        elif len(parts) == 2:
            return (float(parts[0].strip()), float(parts[1].strip()))
        else:
            logger.warning(f"Formato de rango inesperado: '{range_str}'.")
            return None
    except ValueError:
        logger.warning(f"Error al convertir valores del rango '{range_str}' a flotantes.")
        return None

def parse_lut_explanation(explanation_str_raw: Optional[Any]) -> LUTExplanationModel:
    """
    Extrae información estructurada de una cadena de explicación de LUT (LUTExplanation).

    Busca una descripción textual y rangos opcionales "InCalibRange" y "OutLUTRange"
    dentro de la cadena proporcionada.

    Args:
        explanation_str_raw: El valor del tag LUTExplanation, puede ser de cualquier tipo.

    Returns:
        Un objeto LUTExplanationModel con los campos parseados.
    """
    if explanation_str_raw is None:
        return LUTExplanationModel(FullText=None)
    
    text = str(explanation_str_raw)
    explanation_part = text
    in_calib_range_parsed: Optional[Tuple[float, float]] = None
    out_lut_range_parsed: Optional[Tuple[float, float]] = None
    
    # Expresión regular mejorada para capturar los rangos
    regex_pattern = r"^(.*?)(?:InCalibRange:\s*([0-9\.\-]+))?\s*(?:OutLUTRange:\s*([0-9\.\-]+))?$"
    match = re.fullmatch(regex_pattern, text.strip())
    
    if match:
        explanation_part = match.group(1).strip() if match.group(1) else ""
        in_calib_range_str = match.group(2)
        out_lut_range_str = match.group(3)
        
        if in_calib_range_str:
            in_calib_range_parsed = _parse_range_to_floats(in_calib_range_str.strip())
        if out_lut_range_str:
            out_lut_range_parsed = _parse_range_to_floats(out_lut_range_str.strip())
            
    else: 
        logger.debug(f"Regex principal no coincidió para LUTExplanation: '{text}'.")
        explanation_part = text

    return LUTExplanationModel(
        FullText=text,
        Explanation=explanation_part if explanation_part else None,
        InCalibRange=in_calib_range_parsed,
        OutLUTRange=out_lut_range_parsed
    )