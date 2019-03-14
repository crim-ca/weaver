{
    "cwlVersion": "v1.0",
    "class": "Workflow",
    "requirements": [
        {
            "class": "StepInputExpressionRequirement"
        }
    ],
    "inputs": {
        "tas": "File",
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
            "outputSource": "crim_subset/output"
        }
    },
    "steps": {
        "llnl_subset": {
            "run": "esgf_subset.cwl",
            "in": {
                "resource": "tas",
                "lat0": "llnl_lat0",
                "lat1": "llnl_lat1",
                "lon0": "llnl_lon0",
                "lon1": "llnl_lon1"
            },
            "out": ["output"]
        },
        "crim_subset": {
            "run": "ColibriFlyingpigeon_SubsetBbox.cwl",
            "in": {
                "resource": "llnl_subset/output",
                "lat0": "crim_lat0",
                "lat1": "crim_lat1",
                "lon0": "crim_lon0",
                "lon1": "crim_lon1"
            },
            "out": ["output"]
        }
    }
}
