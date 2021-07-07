#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
baseCommand: python
arguments: ["${WEAVER_ROOT_DIR}/weaver/processes/builtin/file2string_array.py", "-o", $(runtime.outdir)]
inputs:
  input:
    type: File
    inputBinding:
      prefix: "-i"
      loadContents: false
      valueFrom: $(self.location)
outputs:
  output:
    type: File
    format: iana:application/json
    outputBinding:
      glob: "output.json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
