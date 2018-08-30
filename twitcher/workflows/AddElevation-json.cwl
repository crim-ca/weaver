{
    "cwlVersion": "v1.0",
    "class": "CommandLineTool",
    "hints": {
        "DockerRequirement": {
            "dockerPull": "docker-registry.crim.ca/ogc-public/debian8-snap6-gpt:v1"
        }
    },
    "inputs": {
        "output_name": {
            "inputBinding": {
                "position": 2,
                "prefix": "-t"
            },
            "type": "string"
        },
        "file_type": {
            "inputBinding": {
                "position": 2,
                "prefix": "-f"
            },
            "type": "string"
        },
        "source_product": {
            "inputBinding": {
                "position": 2,
                "prefix": "-SsourceProduct=",
                "separate": false
            },
            "type": "File"
        },
        "mnt": {
            "inputBinding": {
                "position": 2,
                "prefix": "-Pmnt=",
                "separate": false
            },
            "type": "string"
        },
        "source_graph": {
            "inputBinding": {
                "position": 1
            },
            "type": "File"
        },
        "interpolation": {
            "inputBinding": {
                "position": 2,
                "prefix": "-Pinterpolation=",
                "separate": false
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
