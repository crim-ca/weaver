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
  output_reference:
    type: File
    outputBinding:
      glob: "stdout.log"
  output_data:
    type: string
    outputBinding:
      outputEval: $(inputs.message)
stdout: stdout.log
