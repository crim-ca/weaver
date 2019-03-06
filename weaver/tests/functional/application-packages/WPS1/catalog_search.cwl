{
    "cwlVersion": "v1.0",
    "class": "CommandLineTool",
    "hints": {
        "WPS1Requirement": {
            "provider": "https://pavics.ouranos.ca/twitcher/ows/proxy/malleefowl/wps",
            "process": "thredds_urls"
        }
    },
    "inputs": {
      "url": {
        "type": "string"
      }
    },
    "outputs": {
      "output": {
        "type": "File"
      }
    }
}
