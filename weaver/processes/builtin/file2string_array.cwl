#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
# target the installed python pointing to weaver conda env to allow imports
baseCommand: $WEAVER_ROOT_DIR/bin/python
arguments: ["$WEAVER_ROOT_DIR/weaver/processes/builtin/file2string_array.py", "-o", $(runtime.outdir)]
inputs:
 input:
   type: File
   inputBinding:
     prefix: "-i"
     loadContents: false
     valueFrom: $(self.location)
outputs:
 output: string[]
