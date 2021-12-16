{
    "cwlVersion": "v1.0",
    "class": "Workflow",
    "requirements": [
        {
            "class": "StepInputExpressionRequirement"
        }
    ],
    "inputs": {
        "files": "string[]",
        "variable": "string",
        "esgf_api_key": "string",
        "llnl_lat0": "float",
        "llnl_lat1": "float",
        "llnl_lon0": "float",
        "llnl_lon1": "float",
        "crim_lat0": "float",
        "crim_lat1": "float",
        "crim_lon0": "float",
        "crim_lon1": "float"
    },
    "outputs": {
        "output": {
            "type": "File",
            "outputSource": "llnl_subset/output"
        }
    },
    "steps": {
        "crim_subset": {
            "run": "ColibriFlyingpigeon_SubsetBbox.cwl",
            "in": {
                "resource": "files",
                "lat0": "crim_lat0",
                "lat1": "crim_lat1",
                "lon0": "crim_lon0",
                "lon1": "crim_lon1"
            },
            "out": ["output"]
        },
        "llnl_subset": {
            "run": "SubsetESGF.cwl",
            "in": {
                "files": "crim_subset/output",
                "variable": "variable",
                "api_key": "esgf_api_key",
                "lat_start": "llnl_lat0",
                "lat_end": "llnl_lat1",
                "lon_start": "llnl_lon0",
                "lon_end": "llnl_lon1"
            },
            "out": ["output"]
        }
    }
}
