cwlVersion: v1.0
class: Workflow
inputs:
  files: File[]
outputs:
  output:
    type:
      type: array
      items: File
    outputSource: copy2/output_files
steps:
  copy1:
    run: DockerCopyNestedOutDir.cwl
    in:
      input_files: files
    out:
    - output_files
  copy2:
    run: DockerCopyNestedOutDir.cwl
    in:
      input_files: copy1/output_files
    out:
    - output_files
