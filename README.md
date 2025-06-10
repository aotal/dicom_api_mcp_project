uvicorn api_main:app --reload

	
Response body
Download
[
  {
    "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
    "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
    "Modality": "DX",
    "SeriesNumber": "1",
    "SeriesDescription": "Objeto de prueba universal"
  }
]

XrayTubeCurrent
[
{
  "study_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
  "series_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
  "sop_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743414242787.1"
},
{
  "study_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
  "series_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
  "sop_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743414242185.1"
}
]


http://jupyter.arnau.scs.es:8080/dicom-web/

http://jupyter.arnau.scs.es:8080/dcm4chee-arc/aets/DCM4CHEE/rs


curl -X GET "http://jupyter.arnau.scs.es:8000/dicom-web/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances?ImageComments="MTF"

curl -X GET "http://jupyter.arnau.scs.es:8000/dicom-web/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances?ImageComments=MTF&includefield=QC_Convencional"


curl "http://jupyter.arnau.scs.es:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances?includefield=QC_Convencional"

curl "http://jupyter.arnau.scs.es:8000/dicom-web/studies/1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1/series/1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1/instances?includefield=QC_Convencional"

{
  "instances_to_move": [
{
  "study_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
  "series_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
  "sop_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743414242787.1"
},
{
  "study_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
  "series_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
  "sop_instance_uid": "1.3.46.670589.30.41.0.1.128635482625724.1743414242185.1"
}
  ]
}


[
  {
    "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
    "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
    "Modality": "DX",
    "SeriesNumber": "1",
    "SeriesDescription": "Objeto de prueba universal"
  }
]


curl -X GET \
  -H "Accept: application/dicom+json" \
  "http://jupyter.arnau.scs.es:11112/dcm4chee-arc/aets/DCM4CHEE/rs/instances?00180060=70-80&00204000=*MTF*&00181151=120&includefield=SOPInstanceUID,KVP,XRayTubeCurrent,ImageComments,PatientID&limit=10"








  [
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242600.1",
    "InstanceNumber": "35",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242600.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "35"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241688.1",
    "InstanceNumber": "26",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241688.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "26"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242185.1",
    "InstanceNumber": "31",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242185.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "31"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242276.1",
    "InstanceNumber": "32",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242276.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "32"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242369.1",
    "InstanceNumber": "33",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242369.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "33"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241600.1",
    "InstanceNumber": "25",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241600.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "25"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241986.1",
    "InstanceNumber": "29",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241986.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "29"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241874.1",
    "InstanceNumber": "28",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241874.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "28"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242079.1",
    "InstanceNumber": "30",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242079.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "30"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242891.1",
    "InstanceNumber": "38",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242891.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "38"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242484.1",
    "InstanceNumber": "34",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242484.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "34"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242696.1",
    "InstanceNumber": "36",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242696.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "36"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241784.1",
    "InstanceNumber": "27",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414241784.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "27"
    }
  },
  {
    "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242787.1",
    "InstanceNumber": "37",
    "dicom_headers": {
      "SpecificCharacterSet": "ISO_IR 192",
      "SOPInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743414242787.1",
      "QueryRetrieveLevel": "IMAGE",
      "RetrieveAETitle": "DCM4CHEE",
      "InstanceAvailability": "ONLINE",
      "TimezoneOffsetFromUTC": "",
      "StudyInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412743040.1",
      "SeriesInstanceUID": "1.3.46.670589.30.41.0.1.128635482625724.1743412778135.1",
      "InstanceNumber": "37"
    }
  }
]