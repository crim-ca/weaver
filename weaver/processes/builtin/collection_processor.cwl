#! /usr/bin/env cwl-runner
# based on: https://github.com/opengeospatial/ogcapi-processes/blob/8c41db3f/core/examples/json/ProcessDescription.json
cwlVersion: v1.0
class: CommandLineTool
id: collection_processor
label: Collection Processor
doc: |
  Retrieves relevant data or files resolved from a collection reference using its metadata, queries and desired outputs.
# target the installed python pointing to weaver conda env to allow imports
baseCommand: ${WEAVER_ROOT_DIR}/bin/python
arguments: ["${WEAVER_ROOT_DIR}/weaver/processes/builtin/collection_processor.py", "-o", $(runtime.outdir)]
inputs:
  CollectionInput:
    type: File
    inputBinding:
      prefix: -c
  ProcessInput:
    type: File
    inputBinding:
      prefix: -p
outputs:
  referenceOutput:
    type:
      type: array
      items: File
      # note: important to omit 'format' here, since we want to preserve the flexibility to retrieve 'any' reference
    outputBinding:
      outputEval: $(runtime.outdir)/*
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
