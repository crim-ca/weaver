{
    "cwlVersion": "v1.0",
    "class": "CommandLineTool",
    "stdout": "output.txt",
    "baseCommand": "echo",
    "inputs": {
      "files": {
        "inputBinding": {
          "position": 1
        },
        "type": {
          "type": "array",
          "items": "File"
        }
      }
    },
    "outputs": {
      "output": {
        "type": "File"
      }
    }
}