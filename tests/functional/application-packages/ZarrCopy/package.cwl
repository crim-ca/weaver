cwlVersion: v1.2
class: CommandLineTool
requirements:
  DockerRequirement:
    dockerPull: alpine:latest
baseCommand: [sh, -c]
arguments:
  # '$0' is the input Zarr directory passed as second argument
  - mkdir -p outputs/copy.zarr && cp -r "$0"/. outputs/copy.zarr/
  - $(inputs.zarr_in.path)
inputs:
  zarr_in:
    type: Directory
outputs:
  zarr_out:
    type: Directory
    outputBinding:
      glob: outputs/copy.zarr
