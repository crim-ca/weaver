#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
# target the installed python pointing to weaver conda env to allow imports
baseCommand: python
arguments: ["${WEAVER_ROOT_DIR}/weaver/processes/builtin/file2filearray.py", "-o", $(runtime.outdir)]
inputs:
 input:
   type: File
   format: edam:format_3650
   inputBinding:
      prefix: "-i"
      loadContents: false
      valueFrom: $(self.location)
outputs:
 output:
   format: edam:format_3650
   type:
     type: array
     items: File
   outputBinding:
     glob: "*.nc"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  edam: "http://edamontology.org/"
