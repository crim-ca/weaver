#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
baseCommand: "<high-compute-algorithm>"
requirements:
  ResourceRequirement:
    coresMin: 8
    coresMax: 16
    ramMin: 1024
    ramMax: 2048
    tmpdirMin: 128
    tmpdirMax: 1024
    outdirMin: 1024
    outdirMax: 2048
inputs: {}
outputs:
  output:
    type: File
    outputBinding:
      glob: output.txt
stdout: output.txt
