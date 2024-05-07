#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: Workflow
doc: Workflow that simply calls the echo process twice in a chain.
inputs:
  message: string
outputs:
  output:
    type: File
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
      # temp input to pass result 'File', then load contents for 'string' type
      echo_file: echo1/output
      message:
        valueFrom: $(inputs.echo_file.contents)
    out:
      - output
