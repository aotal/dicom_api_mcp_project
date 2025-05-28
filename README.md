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

http://127.0.0.1:8000/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances?fields=ImageComments