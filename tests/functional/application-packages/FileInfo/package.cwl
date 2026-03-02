cwlVersion: "v1.0"
class: CommandLineTool
id: "FileInfo"
baseCommand: echo
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
  InitialWorkDirRequirement:
    listing:
      - entryname: "output.json"
        entry: |
          {
            "path": "$(inputs.file.path)",
            "format": "$(inputs.file.format)"
          }
  InlineJavascriptRequirement: {}
inputs:
  file:
    doc: |
      This input purposely omits 'format' to allow any type, but outputs the received one if any is provided.
      This is used to validate chaining of the processing input format across the tools and pipeline.
    type: File
    inputBinding:
      position: 1
outputs:
  output:
    type: File
    format: "iana:application/json"
    outputBinding:
      glob: "output.json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
