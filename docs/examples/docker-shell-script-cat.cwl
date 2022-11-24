#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
baseCommand: cat
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
inputs:
  - id: file
    type: File
    inputBinding:
      position: 1
outputs:
  - id: output
    type: File
    outputBinding:
      glob: output.txt
stdout: output.txt
