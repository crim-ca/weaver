cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: cat
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
inputs:
  file:
    type: File
    inputBinding:
      position: 1
outputs:
  output:
    type: File
    # note: format omitted on purpose to let Weaver Process/CWL resolution generate the IANA namespace mapping
    outputBinding:
      glob: "stdout.log"
