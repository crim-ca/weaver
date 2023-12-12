cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: cat
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
inputs:
  bboxInput:
    # for CWL, bbox is simply a JSON file!
    type: File
    format: "iana:application/json"
    inputBinding:
      position: 1
outputs:
  bboxOutput:
    # for CWL, bbox is simply a JSON file!
    type: File
    format: "iana:application/json"
    outputBinding:
      glob: "bbox.json"
stdout: "bbox.json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
