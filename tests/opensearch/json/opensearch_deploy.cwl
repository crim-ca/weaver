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
    "requirements":{
      "DockerRequirement": {
        "dockerPull": "alpine:latest"
      }
    },
    "outputs": {
      "output": {
        "type": "File"
      }
    }
}