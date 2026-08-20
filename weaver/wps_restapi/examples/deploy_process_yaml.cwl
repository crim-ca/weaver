cwlVersion: "v1.2"
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
    outputBinding:
      glob: "stdout.log"
stdout: stdout.log
