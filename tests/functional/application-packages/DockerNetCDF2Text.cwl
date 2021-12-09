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
          in="\${1}"
          out="\${2%.*}.txt"
          echo "Input: \${in}"
          echo "Output: \${out}"
          mv "\${in}" "\${out}"
inputs:
  input_nc:
    type: File
    inputBinding:
      position: 1
outputs:
  output_txt:
    type: File
    outputBinding:
      glob: "*.txt"
