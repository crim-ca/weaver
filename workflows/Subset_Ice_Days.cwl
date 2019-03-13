{
    "cwlVersion": "v1.0",
    "class": "Workflow",
    "requirements": [
        {
            "class": "StepInputExpressionRequirement"
        }
    ],
    "inputs": {
        "tasmax": "File",
        "lat0": "float",
        "lat1": "float",
        "lon0": "float",
        "lon1": "float",
        "freq": "string"
    },
    "outputs": {
        "output": {
            "type": "File",
            "outputSource": "ice_days/output_netcdf"
        }
    },
    "steps": {
        "subset": {
            "run": "flyingpigeon_subset_bbox.cwl",
            "in": {
                "resource": "tasmax",
                "lat0": "lat0",
                "lat1": "lat1",
                "lon0": "lon0",
                "lon1": "lon1"
            },
            "out": ["output"]
        },
        "ice_days": {
            "run": "finch_ice_days.cwl",
            "in": {
                "tasmax": "subset/output",
                "freq": "freq"
            },
            "out": ["output_netcdf"]
        }
    }
}
