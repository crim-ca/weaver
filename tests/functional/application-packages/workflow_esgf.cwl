{
  "cwlVersion": "v1.0",
  "class": "Workflow",
  "requirements": [
    {
      "class": "StepInputExpressionRequirement"
    }
  ],
  "inputs": {
    "files": {
      "type": {
        "type": "array",
        "items": "File"
      }
    },
    "variable": {
      "type": "string"
    },
    "api_key": {
      "type": "string"
    }
  },
  "outputs": {
    "output": {
      "type": "File",
      "outputSource": "aggregate/output_netcdf"
    }
  },
  "steps": {
    "aggregate": {
      "run": "esgf_aggregate.cwl",
      "in": {
        "files": "files",
        "variable": "variable",
        "api_key": "api_key"
      },
      "out": [
        "output_netcdf"
      ]
    }
  }
}
