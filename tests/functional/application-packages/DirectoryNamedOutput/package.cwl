cwlVersion: v1.2
class: CommandLineTool
requirements:
  DockerRequirement:
    dockerPull: alpine:latest
baseCommand: [sh, -c]
arguments:
  - mkdir -p outputs/test.zarr && printf '{}' > outputs/test.zarr/zarr.json
inputs:
  marker:
    type: string
outputs:
  result:
    type: Directory
    outputBinding:
      glob: outputs/test.zarr
