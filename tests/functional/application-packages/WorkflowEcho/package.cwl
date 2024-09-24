#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow
doc: Workflow that calls the echo process in a chain to propagate the input value to the output.
inputs:
  message: string
outputs:
  output:
    type: File
    outputSource: echo2/output
requirements:
  # required for the 'valueFrom' in the step
  # (see https://www.commonwl.org/v1.0/Workflow.html#WorkflowStepInput)
  StepInputExpressionRequirement: {}
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
      # temp input to pass result 'File', then load contents for 'string' type
      echo_file:
        source: echo1/output
        loadContents: true
      message:
        valueFrom: "$(inputs.echo_file.contents)"
    out:
      - output
