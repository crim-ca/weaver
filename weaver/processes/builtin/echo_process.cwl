#! /usr/bin/env cwl-runner
# based on: https://github.com/opengeospatial/ogcapi-processes/blob/8c41db3f/core/examples/json/ProcessDescription.json
cwlVersion: v1.0
class: CommandLineTool
label: Echo Process
doc: This process accepts and number of input and simple echoes each input as an output.
baseCommand: echo
inputs:
  string_input:
    label: String Literal Input Example
    doc: This is an example of a STRING literal input.
    type:
      type: enum
      symbols:
        - Value1
        - Value2
        - Value3
  date_input:
    type: string
  measure_input:
    type: double
  double_input:
    type: double
  array_input:
    type:
      type: array
      items: int
  complex_object_input:
    type: File
  geometry_input:
    type:
      type: array
      items: File
  images_input:
    type:
      type: array
      items: File
  feature_collection_input:
    type: File
outputs:
  string_output:
    type:
      type: enum
      symbols:
        - Value1
        - Value2
        - Value3
    outputBinding:
      outputEval: $(inputs.string_input)
  date_output:
    type: string
    outputBinding:
      outputEval: $(inputs.date_input)
  measure_output:
    type: float
    outputBinding:
      outputEval: $(inputs.measure_input)
  double_output:
    type: double
    outputBinding:
      outputEval: $(inputs.double_input)
  array_output:
    type:
      type: array
      items: int
    outputBinding:
      outputEval: $(inputs.array_input)
  complex_object_output:
    type: File
    outputBinding:
      outputEval: $(inputs.complex_object_input)
  geometry_output:
    type:
      type: array
      items: File
    outputBinding:
      outputEval: $(inputs.geometry_input)
  images_output:
    type:
      type: array
      items: File
    outputBinding:
      outputEval: $(inputs.images_input)
  feature_collection_output:
    type: File
    outputBinding:
      outputEval: $(inputs.feature_collection_input)
