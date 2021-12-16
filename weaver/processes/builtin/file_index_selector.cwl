#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
# target the installed python pointing to weaver conda env to allow imports
baseCommand: python
arguments:
  - "${WEAVER_ROOT_DIR}/weaver/processes/builtin/file_index_selector.py"
  - "-o"
  - "$(runtime.outdir)"
inputs:
 files:
   type:
     type: array
     items: File
   inputBinding:
     position: 1
     prefix: "--files"
 index:
   type: int
   inputBinding:
     position: 2
     prefix: "--index"
outputs:
 output:
   type: File
   outputBinding:
     glob: "*.*"
