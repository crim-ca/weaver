#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow
doc: Workflow that calls the echo process with secrets feature applied on the input.
hints:
  cwltool:Secrets:
    secrets:
      - message
$namespaces:
  cwltool: http://commonwl.org/cwltool#
inputs:
  message: string
outputs:
  output:
    type: File
    outputSource: echo2/output
steps:
  echo:
    run: EchoSecrets.cwl
    in:
      message: message
    out:
      - output
