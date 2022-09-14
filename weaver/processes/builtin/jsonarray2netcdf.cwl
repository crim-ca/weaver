#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
# target the installed python pointing to weaver conda env to allow imports
baseCommand: python
arguments:
  - "${WEAVER_ROOT_DIR}/weaver/processes/builtin/jsonarray2netcdf.py"
  - "-o"
  - "$(runtime.outdir)"
inputs:
 input:
   type: File
   format: iana:application/json
   inputBinding:
     position: 1
     prefix: "-i"
outputs:
 output:
   format: ogc:netcdf
   type:
     type: array
     items: File
   outputBinding:
     glob: "*.nc"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  ogc: "http://www.opengis.net/def/media-type/ogc/1.0/"
