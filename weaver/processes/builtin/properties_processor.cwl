#! /usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
id: properties_processor
label: Properties Processor
doc: |
  Generates properties contents using the specified input definitions.
# target the installed python pointing to weaver conda env to allow imports
baseCommand: ${WEAVER_ROOT_DIR}/bin/python
arguments: ["${WEAVER_ROOT_DIR}/weaver/processes/builtin/properties_processor.py", "-o", $(runtime.outdir)]
inputs:
  properties:
    doc: Properties definition submitted to the process and to be generated from input values.
    type: File
    format: "iana:application/json"
    inputBinding:
      prefix: -P
  values:
    doc: Values available for properties generation.
    type: File
    format: "iana:application/json"
    inputBinding:
      prefix: -V
outputs:
  referenceOutput:
    doc: Generated file contents from specified properties.
    type: File
    # note: important to omit 'format' here, since we want to preserve the flexibility to retrieve 'any' reference
    outputBinding:
      outputEval: $(runtime.outdir)/*
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
