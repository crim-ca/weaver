#! /usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
id: field_modifier_processor
label: Field Modifier Processor
doc: |
  Performs field modification over properties and contents using the specified input definitions.
# target the installed python pointing to weaver conda env to allow imports
baseCommand: ${WEAVER_ROOT_DIR}/bin/python
arguments: ["${WEAVER_ROOT_DIR}/weaver/processes/builtin/properties_processor.py", "-o", $(runtime.outdir)]
inputs:
  properties:
    doc: Properties definition submitted to the process and to be generated from input values.
    type: File
    format: "iana:application/json"
    inputBinding:
      prefix: --properties
  filter:
    doc: Filter definition submitted to the process and to be generated from input values.
    type: File
    format: "iana:application/json"
    inputBinding:
      prefix: --filter
  filter-crs:
    doc: Filter Coordinate Reference System (CRS) to employ with the 'filter' parameter.
    type: string
    default: "EPSG:4326"
    inputBinding:
      prefix: --filter-crs
  filter-lang:
    doc: Filter language to interpret the 'filter' parameter.
    type: string?
    inputBinding:
      prefix: --filter-lang
  sortBy:
    doc: Sorting definition with relevant properties and ordering direction.
    type: string?
    inputBinding:
      prefix: --sortby
  values:
    doc: Values available for content field modification.
    type: File
    format: "iana:application/json"
    inputBinding:
      prefix: -V
outputs:
  referenceOutput:
    doc: Generated file contents from specified field modifiers.
    type: File
    # note: important to omit 'format' here, since we want to preserve the flexibility to retrieve 'any' reference
    outputBinding:
      outputEval: $(runtime.outdir)/*
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
