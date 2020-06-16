{
    "cwlVersion": "v1.0",
    "class": "Workflow",
    "requirements": [
        {
            "class": "StepInputExpressionRequirement"
        }
    ],
    "inputs": {
        "tasmax": {
            "type": {
                "type": "array",
                "items": "File"
            }
        },
        "lat0": "float",
        "lat1": "float",
        "lon0": "float",
        "lon1": "float",
        "metaindex": "integer"
    },
    "outputs": {
        "output": {
            "type": "File",
            "outputSource": "metalink_picker/output"
        }
    },
    "steps": {
        "subset": {
            "run": "ColibriFlyingpigeon_SubsetBbox.cwl",
            "in": {
                "resource": "tasmax",
                "lat0": "lat0",
                "lat1": "lat1",
                "lon0": "lon0",
                "lon1": "lon1"
            },
            "out": ["output"]
        },
        "metalink_picker": {
            "run": "metalink2netcdf",
            "in": {
                "input": "subset/output",
                "index": "metaindex"
            },
            "out": ["output"]
        }
    }
}
