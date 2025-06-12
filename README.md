Este es un servidor MCP (Model Context Protocol) que expone operaciones DICOM como herramientas para agentes de IA.

## Características

- Búsqueda de estudios DICOM en PACS
- Búsqueda de series dentro de estudios
- Consulta de metadatos de instancias
- Movimiento de entidades DICOM al servidor local
- Obtención de datos de píxeles de instancias locales

## Instalación

```bash
pip install -e .
```

## Configuración

1. Ajusta la variable `DICOM_SERVER_BASE_URL` en el archivo principal según tu configuración:
   ```python
   DICOM_SERVER_BASE_URL = "http://tu-servidor-dicom:puerto"
   ```

2. Configura tu cliente MCP para usar este servidor:
   ```json
   {
     "mcpServers": {
       "dicom-tools": {
         "command": "python",
         "args": ["/ruta/a/dicom_mcp_server.py"],
         "env": {
           "DICOM_SERVER_URL": "http://localhost:8000"
         }
       }
     }
   }
   ```

## Uso

El servidor expone las siguientes herramientas:

### query_studies
Busca estudios en el PACS
- `patient_id`: ID del paciente
- `study_date`: Fecha del estudio (YYYYMMDD)
- `accession_number`: Número de acceso
- `patient_name`: Nombre del paciente
- `additional_filters`: Filtros adicionales

### query_series
Busca series dentro de un estudio
- `study_instance_uid`: UID del estudio (requerido)
- `additional_filters`: Filtros adicionales

### query_instances
Busca metadatos de instancias en una serie
- `study_instance_uid`: UID del estudio (requerido)
- `series_instance_uid`: UID de la serie (requerido)
- `fields_to_retrieve`: Campos específicos a recuperar

### move_dicom_entity_to_local_server
Mueve entidades DICOM al servidor local
- `study_instance_uid`: UID del estudio (requerido)
- `series_instance_uid`: UID de la serie (opcional)
- `sop_instance_uid`: UID de la instancia (opcional)

### get_local_instance_pixel_data
Obtiene datos de píxeles de instancias locales
- `sop_instance_uid`: UID de la instancia (requerido)

## Desarrollo

Para desarrollo:
```bash
pip install -e ".[dev]"
```

## Licencia