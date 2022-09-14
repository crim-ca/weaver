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
          out="\$(basename \${1%.*}.txt)"
          echo "Input: \${in}"
          echo "Output: \${out}"
          ls "$(runtime.outdir)"
          cp "\${in}" "\${out}"
inputs:
  input_nc:
    type: File
    inputBinding:
      position: 1
    format: ogc:netcdf
outputs:
  output_txt:
    type: File
    outputBinding:
      glob: "*.txt"
$namespaces:
  ogc: "http://www.opengis.net/def/media-type/ogc/1.0/"
