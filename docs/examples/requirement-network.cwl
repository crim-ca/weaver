#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
baseCommand: curl
requirements:
  NetworkAccess:
    networkAccess: true
inputs:
  url:
    type: string
outputs:
  output:
    type: File
    outputBinding:
      glob: "output.txt"
stdout: "output.txt"
