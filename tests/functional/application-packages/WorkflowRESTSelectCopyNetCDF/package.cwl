cwlVersion: v1.0
class: Workflow
inputs:
  input_json:
    type: File
    format: iana:application/json
  index_json: int
outputs:
  output:
    type: File
    outputSource: convert/output_txt
steps:
  parse:
    # note: Builtin process. CWL within corresponding directory.
    run: jsonarray2netcdf
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
    # note: This cannot exist as CWL by itself. It uses Weaver WPS1Requirement.
    run: WPS1DockerNetCDF2Text.cwl
    in:
      input_nc: select/output
    out:
      - output_txt

$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
