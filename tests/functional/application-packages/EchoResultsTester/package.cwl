cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: echo
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      - entryname: result.json
        entry: |
          {"data":"$(inputs.message)"}
      - entryname: result.txt
        entry: |
          $(inputs.message)
inputs:
  message:
    type: string
    inputBinding:
      position: 1
outputs:
  output_data:
    type: string
    outputBinding:
      outputEval: $(inputs.message)
  output_text:
    type: File
    outputBinding:
      glob: result.txt
    format: "iana:text/plain"
  output_json:
    type: File
    outputBinding:
      glob: result.json
    format: "iana:application/json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
