#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
# target the installed python pointing to weaver conda env to allow imports
baseCommand: python
arguments: ["${WEAVER_ROOT_DIR}/weaver/processes/builtin/metalink2netcdf.py", "-o", $(runtime.outdir)]
inputs:
 input:
   type: File
   inputBinding:
     position: 1
     prefix: "-i"
 index:
   doc: Index of the MetaLink file to extract. This index is 1-based.
   type: int
   inputBinding:
     position: 2
     prefix: "-n"
outputs:
 output:
   type: File
   format: edam:format_3650
   outputBinding:
     glob: "*.nc"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  edam: "http://edamontology.org/"
