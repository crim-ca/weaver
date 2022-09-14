cwlVersion: v1.0
class: Workflow
requirements:
  ScatterFeatureRequirement: {}
inputs:
  input_json:
    type: File
    format: "iana:application/json"
outputs:
  output:
    type:
      type: array
      items: File
    outputSource: convert/output_txt
steps:
  parse:
    run: jsonarray2netcdf
    in:
      input: input_json
    out:
      - output
  convert:
    run: WPS1DockerNetCDF2Text.cwl
    scatter: input_nc
    in:
      input_nc: parse/output
    out:
      - output_txt
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
