#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow
doc: |
  Workflow that calls the echo process in a chain to propagate the input value to the output.
  The workflow input is optional to allow testing omission of the input on the first step,
  and explicitly providing it on the second step (from the resulting propagation of the first step).
inputs:
  message: string?
  null_value:
    type: string?
    default: null
  null_file:
    type: File?
    default: null
    format: "iana:text/plain"
outputs:
  output:
    type: File
    outputSource: echo2/output
requirements:
  # required for the 'valueFrom' in the step
  # (see https://www.commonwl.org/v1.0/Workflow.html#WorkflowStepInput)
  StepInputExpressionRequirement: {}
  InlineJavascriptRequirement: {}
steps:
  echo1:
    run: EchoOptional.cwl
    in:
      message: message        # input omission should result in using the default, which is a default string in the tool
      null_value: null_value  # input omission should result in using the default, which is also null from this workflow
      null_file: null_file
    out:
      - output
  echo2:
    run: EchoOptional.cwl
    in:
      # temp input to pass result 'File', then load contents for 'string' type
      echo_file:
        source: echo1/output
        loadContents: true
      message:
        valueFrom: "$(inputs.echo_file.contents)"
      null_value:
        valueFrom: "${ return null; }"  # explicitly provided null should resolve the same as omitting it
      null_file:
        valueFrom: "${ return null; }"  # explicitly provided null should resolve the same as omitting it
    out:
      - output

$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
