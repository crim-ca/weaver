cwlVersion: v1.0
class: Workflow
requirements:
  ScatterFeatureRequirement: {}
inputs:
  input_json: File
outputs:
  output:
    type:
      type: array
      items: File
    outputSource: convert/output_txt
steps:
  parse:
    # note: This cannot exist as CWL by itself. It uses Weaver WSP1Requirement.
    run: WPS1JsonArray2NetCDF.cwl
    in:
      input: input_json
    out:
      - output
  convert:
    run: DockerNetCDF2Text.cwl
    scatter: input_nc
    in:
      input_nc: parse/output
    out:
      - output_txt
