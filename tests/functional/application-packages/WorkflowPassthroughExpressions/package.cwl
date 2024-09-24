cwlVersion: v1.2
class: Workflow
requirements:
  - class: InlineJavascriptRequirement

inputs:
  message:
    type: string
  code:
    type: int

outputs:
  message1:
    type: string
    outputSource: first/message
  message2:
    type: string
    outputSource: second/message
  code1:
    type: int
    outputSource: first/code
  code2:
    type: int
    outputSource: second/code
  number1:
    type: float
    outputSource: first/number
  number2:
    type: float
    outputSource: second/number
  integer1:
    type: int
    outputSource: first/integer
  integer2:
    type: int
    outputSource: second/integer

steps:
  first:
    run: PassthroughExpressions.cwl
    in:
      message: message
      code: code
    out:
      - message
      - code
      - number
      - integer
  second:
    run: PassthroughExpressions.cwl
    in:
      message: first/message
      code: first/code
    out:
      - message
      - code
      - number
      - integer
