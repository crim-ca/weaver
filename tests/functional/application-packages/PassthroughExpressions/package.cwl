cwlVersion: v1.2
class: CommandLineTool
baseCommand: "true"
requirements:
  - class: InlineJavascriptRequirement
  - class: DockerRequirement
    dockerPull: docker.io/debian:stable-slim
inputs:
  message:
    type: string
  code:
    type: int
  autogen:
    type: float
    default: 3.1416
    inputBinding:
      valueFrom: ${ return self; }
outputs:
  message:
    type: string
    outputBinding:
      outputEval: ${ return inputs.message }
  code:
    type: int
    outputBinding:
      outputEval: $(inputs.code)
  number:
    type: float
    outputBinding:
      outputEval: $(inputs.autogen)
  integer:
    type: int
    outputBinding:
      outputEval: ${ return parseInt(inputs.autogen) }
