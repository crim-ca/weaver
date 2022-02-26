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
    type: string
    outputBinding:
      glob: "stdout.log"
      loadContents: true
      outputEval: $(self[0].contents)
