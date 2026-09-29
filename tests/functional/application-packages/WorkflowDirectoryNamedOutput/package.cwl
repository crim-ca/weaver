cwlVersion: v1.2
class: Workflow
inputs:
  marker:
    type: string
outputs:
  result:
    type: Directory
    outputSource: directory_step/result
steps:
  directory_step:
    run: DirectoryNamedOutput.cwl
    in:
      marker: marker
    out: [result]
