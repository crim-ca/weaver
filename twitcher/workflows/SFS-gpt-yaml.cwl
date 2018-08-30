#!/usr/bin/env cwl-runner

cwlVersion: v1.0
class: CommandLineTool
hints:
  DockerRequirement:
    dockerPull: docker-registry.crim.ca/ogc-public/debian8-snap6-gpt:v1
inputs:
  source_graph:
    type: File
    inputBinding:
      position: 1
  file_type:
    type: string
    inputBinding:
      position: 2
      prefix: -f
  source_product:
    type: File
    inputBinding:
      position: 2
      prefix: -SsourceProduct=
      separate: false
  output_name:
    type: string
    inputBinding:
      position: 2
      prefix: -t
outputs:
  output:
    type: File
    outputBinding:
      glob: $(inputs.output_name)
