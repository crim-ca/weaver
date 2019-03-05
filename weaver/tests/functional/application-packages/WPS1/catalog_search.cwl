{
    "cwlVersion": "v1.0",
    "class": "CommandLineTool",
    "requirements": {
        "WPS1Requirement": {
            "provider": "https://pavics.ouranos.ca/twitcher/ows/proxy/malleefowl/wps",
            "process_id": "thredds_urls"
        }
    },
    "inputs": {
      "url": {
        "type": {
          "type": "File"
        }
      }
    },
    "outputs": {
      "output": {
        "type": "File"
      }
    }
}