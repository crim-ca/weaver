cwlVersion: v1.0
class: Workflow
inputs:
  message: string
outputs:
  output:
    type: string
    outputSource: read/output
steps:
  # string -> file
  echo:
    run: Echo.cwl
    in:
      message: message
    out:
      - output
  # file -> string
  read:
    run: ReadFile.cwl
    in:
      file: echo/output
    out:
      - output
