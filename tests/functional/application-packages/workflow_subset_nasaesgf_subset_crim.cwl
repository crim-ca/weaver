{
    "cwlVersion": "v1.0",
    "class": "Workflow",
    "requirements": [
        {
            "class": "StepInputExpressionRequirement"
        }
    ],
    "inputs": {
        "files": "File",
        "variable": "string",
        "nasa_lat0": "float",
        "nasa_lat1": "float",
        "nasa_lon0": "float",
        "nasa_lon1": "float",
        "crim_lat0": "float",
        "crim_lat1": "float",
        "crim_lon0": "float",
        "crim_lon1": "float"
    },
    "outputs": {
        "output": {
            "type": "File",
            "outputSource": "nasa_subset/output"
        }
    },
    "steps": {
        "nasa_subset": {
            "run": "SubsetNASAESGF.cwl",
            "in": {
                "files": "files",
                "variable": "variable",
                "lat_start": "nasa_lat0",
                "lat_end": "nasa_lat1",
                "lon_start": "nasa_lon0",
                "lon_end": "nasa_lon1"
            },
            "out": ["output"]
        },
        "file2string_array": {
            "run": "file2string_array",
            "in": {
                "input": "nasa_subset/output"
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
