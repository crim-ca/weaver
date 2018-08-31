{
    "cwlVersion": "v1.0",
    "class": "CommandLineTool",
    "hints": {
        "DockerRequirement": {
            "dockerPull": "docker-registry.crim.ca/ogc-public/snap6-sfs:v2"
        }
    },
    "inputs": {
        "source_product": {
            "inputBinding": {
                "position": 1,
                "prefix": "-SsourceProduct=",
                "separate": false
            },
            "type": "File"
        },
        "output_file_type": {
            "inputBinding": {
                "position": 2,
                "prefix": "-f"
            },
            "type": {
                "type": "enum",
                "symbols": [
                    "GeoTIFF",
                    "NetCDF-CF"
                ]
            }
        },
        "output_name": {
            "inputBinding": {
                "position": 3,
                "prefix": "-t"
            },
            "type": "string"
        }
    },
    "outputs": {
        "output": {
            "outputBinding": {
                "glob": "$(inputs.output_name)"
            },
            "type": "File"
        }
    }
}
