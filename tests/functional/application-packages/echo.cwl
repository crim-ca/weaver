cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: echo
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
inputs:
  message:
    type: string
    inputBinding:
      position: 1
outputs:
  output:
    type: File
    # note: format omitted on purpose to let Weaver Process/CWL resolution generate the IANA namespace mapping
    outputBinding:
      glob: "stdout.log"
