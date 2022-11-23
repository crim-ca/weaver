#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: Workflow
inputs:
  files: File[]
outputs:
  output:
    type: File
    outputSource: listing/output_file
steps:
  merge:
    run: DirectoryMergingProcess.cwl
    in:
      files: files
    out:
      - output_dir
  listing:
    run: DirectoryListingProcess.cwl
    in:
      input_dir: merge/output_dir
    out:
      - output_file
