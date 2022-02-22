cwlVersion: v1.0
class: Workflow
inputs:
  message: string
outputs:
  output:
    type: string
    outputSource: echo2/output
steps:
  echo1:
    run: Echo.cwl
    in:
      message: message
    out:
      - output
  echo2:
    run: Echo.cwl
    in:
      input_files: echo1/output
    out:
      - output
