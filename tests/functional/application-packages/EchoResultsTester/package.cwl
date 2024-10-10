cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: echo
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    # note: use '>-' to avoid newline after the JSON contents in the generated file, tests validate that explicitly
    listing:
      - entryname: result.json
        entry: >-
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
      # note: since no file is associated for literal type, a link representation from it should use 'output_data.txt'
      outputEval: $(inputs.message)
  output_text:
    type: File
    outputBinding:
      # note: purposely use a different name than 'output_text' to validate the resulting path uses this one
      glob: result.txt
    format: "iana:text/plain"
  output_json:
    type: File
    outputBinding:
      # note: purposely use a different name than 'output_json' to validate the resulting path uses this one
      glob: result.json
    format: "iana:application/json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
