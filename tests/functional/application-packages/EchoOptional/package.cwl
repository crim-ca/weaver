cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: echo
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
inputs:
  message:
    type: string?
    default: test-message
    inputBinding:
      position: 1
  null_value:
    type: string?
    # note: no 'default' to auto-default to 'null', value (including 'null') must be provided explicitly
    inputBinding:
      position: 2
  null_file:
    # note: nothing is done with this input, defined only to test a 'File' type handling by omission from inputs
    type: File?
    default: null
    format: "iana:text/plain"
outputs:
  output:
    type: File
    # note: format omitted on purpose to let Weaver Process/CWL resolution generate the IANA namespace mapping
    outputBinding:
      glob: "stdout.log"
stdout: stdout.log
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
