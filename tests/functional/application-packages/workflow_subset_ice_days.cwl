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
        "freq": {
            "default": "YS",
            "type": {
                "type": "enum",
                "symbols": ["YS", "MS", "QS-DEC", "AS-JUL"]
            }
        }
    },
    "outputs": {
        "output": {
            "type": "File",
            "outputSource": "ice_days/output_netcdf"
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
        "ice_days": {
            "run": "Finch_IceDays.cwl",
            "in": {
                "tasmax": "subset/output",
                "freq": "freq"
            },
            "out": ["output_netcdf"]
        }
    }
}
