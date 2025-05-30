uvicorn api_main:app --reload

[
  {
    "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
    "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
    "Modality": "DX",
    "SeriesNumber": "1",
    "SeriesDescription": "Objeto de prueba universal",
    "ImageComments": null
  }
]

http://127.0.0.1:8000/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances?fields=ModalityLUTSequence&fields=ImageComments&fields=PatientName

http://127.0.0.1:8000/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances/1.3.46.670589.30.41.0.1.128635482625724.1743414241688.1/pixeldata

curl -v ["LA_BULK_DATA_URI_COMPLETA_AQUI"](http://127.0.0.1:8000/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances/1.3.46.670589.30.41.0.1.128635482625724.1743414241688.1/pixeldata --output pixel_data.bin 

/rs/studies/{StudyInstanceUID}/series/{SeriesInstanceUID}/instances/{SOPInstanceUID}

http://jupyter.arnau.scs.es:8000/dcm4chee-arc/aets/DCM4CHEE/rs/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances/1.3.46.670589.30.41.0.1.128635482625724.1743414241688.1/



curl -v "http://jupyter.arnau.scs.es:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances/1.3.46.670589.30.41.0.1.128635482625724.1743414241688.1/bulk/7FE00010" --output pixel_data.bin