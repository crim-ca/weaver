cwlVersion: v1.0
class: CommandLineTool
baseCommand:
  - bash
  - script.sh
requirements:
  DockerRequirement:
    dockerPull: debian:stretch-slim
  InitialWorkDirRequirement:
    listing:
      - entryname: script.sh
        entry: |
          set -x
          echo "Input: $2"
          echo "Output: $1"
          find "$1" ! -type d -exec ls -lht {} + > output.txt
          cat output.txt
inputs:
  input_dir:
    type: Directory
    inputBinding:
      position: 1
outputs:
  output_file:
    type: File
    outputBinding:
      glob: "output.txt"
