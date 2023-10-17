#! /usr/bin/env cwl-runner
# based on: https://github.com/opengeospatial/ogcapi-processes/blob/8c41db3f/core/examples/json/ProcessDescription.json
cwlVersion: v1.0
class: CommandLineTool
label: Echo Process
doc: This process accepts and number of input and simple echoes each input as an output.
baseCommand: echo
inputs:
  stringInput:
    label: String Literal Input Example
    doc: This is an example of a STRING literal input.
    type:
      type: enum
      symbols:
        - Value1
        - Value2
        - Value3
  measureInput:
    type: double
  dateInput:
    type: string
  doubleInput:
    type: double
  arrayInput:
    type:
      type: array
      items: int
  complexObjectInput:
    type: File
  geometryInput:
    type:
      type: array
      items: File
    format: "iana:application/geo+json"
  boundingBoxInput:
    type: File
  imagesInput:
    type:
      - File
      - type: array
        items: File
  featureCollectionInput:
    type: File
outputs:
  stringOutput:
    type:
      type: enum
      symbols:
        - Value1
        - Value2
        - Value3
    outputBinding:
      outputEval: $(inputs.string_input)
  measureOutput:
    type: float
    outputBinding:
      outputEval: $(inputs.measure_input)
  dateOutput:
    type: string
    outputBinding:
      outputEval: $(inputs.date_input)
  doubleOutput:
    type: double
    outputBinding:
      outputEval: $(inputs.double_input)
  arrayOutput:
    type:
      type: array
      items: int
    outputBinding:
      outputEval: $(inputs.array_input)
  complexObjectOutput:
    type: File
    outputBinding:
      outputEval: $(inputs.complex_object_input)
  geometryOutput:
    type:
      type: array
      items: File
    outputBinding:
      outputEval: $(inputs.geometry_input)
  boundingBoxOutput:
    type: File
  imagesOutput:
    type:
      type: array
      items: File
    outputBinding:
      outputEval: $(inputs.images_input)
  featureCollectionOutput:
    type: File
    outputBinding:
      outputEval: $(inputs.feature_collection_input)
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
