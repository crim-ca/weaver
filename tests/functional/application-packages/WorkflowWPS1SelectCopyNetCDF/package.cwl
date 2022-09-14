#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: Workflow
inputs:
  input_json: File
  index_json: int
outputs:
  output:
    type: File
    outputSource: convert/output_txt
steps:
  parse:
    # note: This cannot exist as CWL by itself. It uses Weaver WSP1Requirement.
    run: WPS1JsonArray2NetCDF.cwl
    in:
      input: input_json
    out:
      - output
  select:
    # note: Builtin process. CWL within corresponding directory.
    run: file_index_selector.cwl
    in:
      files: parse/output
      index: index_json
    out:
      - output
  convert:
    run: DockerNetCDF2Text.cwl
    in:
      input_nc: select/output
    out:
      - output_txt
