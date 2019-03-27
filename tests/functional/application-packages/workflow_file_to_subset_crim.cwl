{
    "cwlVersion": "v1.0",
    "class": "Workflow",
    "requirements": [
        {
            "class": "StepInputExpressionRequirement"
        }
    ],
    "inputs": {
        "file": "File",
        "crim_lat0": "float",
        "crim_lat1": "float",
        "crim_lon0": "float",
        "crim_lon1": "float"
    },
    "outputs": {
        "output": {
            "type": "File",
            "outputSource": "crim_subset/output"
        }
    },
    "steps": {
        "file2string_array": {
            "run": "file2string_array",
            "in": {
                "input": "file"
            },
            "out": ["output"]
        },
        "crim_subset": {
            "run": "ColibriFlyingpigeon_SubsetBbox.cwl",
            "in": {
                "resource": "file2string_array/output",
                "lat0": "crim_lat0",
                "lat1": "crim_lat1",
                "lon0": "crim_lon0",
                "lon1": "crim_lon1"
            },
            "out": ["output"]
        }
    }
}
