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
      # copy the file to the output location with nested directory path
      # add prefix within the contents to allow validation of final output
      # note: Any $(cmd) or ${var} notation must be escaped to avoid conflict with CWL parsing.
      - entryname: script.sh
        entry: |
          set -x
          echo "Input: $2"
          echo "Output: $1"
          mkdir -p nested/output/directory/
          for file in $1; do
            name="\$(basename \${file})"
            path="nested/output/directory/\${name}"
            echo "COPY:" > "\${path}"
            cat "\${file}" >> "\${path}"
          done
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
