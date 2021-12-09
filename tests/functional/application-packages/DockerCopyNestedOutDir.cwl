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
        mkdir -p nested/output/directory/
        cp $1 "nested/output/directory/"
inputs:
  input_files:
    type:
      type: array
      items: File
    inputBinding:
      position: 1
outputs:
  output_files:
    type:
      type: array
      items: File
    outputBinding:
      glob: "nested/output/directory/*.txt"
