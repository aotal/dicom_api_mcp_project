from typing import Dict, Optional, Any
from dataclasses import dataclass

@dataclass
class DicomToolContext:
    """Clase para contener la configuración que usarán las herramientas."""
    pacs_config: Dict[str, Any]
    move_destination_aet: str

dicom_context: Optional[DicomToolContext] = None
