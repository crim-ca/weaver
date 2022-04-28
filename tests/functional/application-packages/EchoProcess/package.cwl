# WARNING:
#   This package definition is not operational in itself.
#   It is intended only to define minimal CWL required corresponding to deployed I/O from reference process description.

$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  ogc: "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/d52579/core/openapi/schemas/"

cwlVersion: "v1.0"
class: CommandLineTool
baseCommand: echo
requirements:
  DockerRequirement:
    dockerPull: "debian:stretch-slim"

inputs:
  arrayInput:
    type: int[]
  boundingBoxInput:
    type: File
    format: "ogc:bbox.yaml"
  complexObjectInput:
    type: File
    format: iana:application/json
  dateInput:
    type: string
  doubleInput:
    type: double
  featureCollectionInput:
    type: File
    # Must leave format undefined in this case since multiple are allowed (GML+XML, OGC KML+XML, GeoJSON)
    #format: iana:application/json
  geometryInput:
    type:
      # array from minOccurs=2/maxOccurs=5
      type: array
      items: File
    # Again multiple formats allowed.
    #format: iana:application/json
  imagesInput:
    type:
      # array from minOccurs=1/maxOccurs=150
      # note: '{type: File}' not allowed
      - "File"
      - type: array
        items: File
    # Multiple formats (GeoTIFF, JP2)
    #format:
  measureInput:
    # no way to provide unit of measure...?
    type: double
  stringInput:
    type:
      type: enum
      symbols:
        - Value1
        - Value2
        - Value3

outputs:
  arrayOutput:
    # minItems=2/maxItems=10 provided,
    # but schema also indicates explicitly that it is an array
    type:
      type: array
      items: int
  boundingBoxOutput:
    type: File
    format: "ogc:bbox.yaml"
    outputBinding:
      glob: bbox.json
  complexObjectOutput:
    type: File
    format: iana:application/json
  dateOutput:
    type: string
  doubleOutput:
    type: double
  featureCollectionOutput:
    type: File
    # Must leave format undefined in this case since multiple are allowed (GML+XML, OGC KML+XML, GeoJSON)
    #format: iana:application/json
  geometryOutput:
    type:
      # array from minOccurs=2/maxOccurs=5
      type: array
      items: File
    # Again multiple formats allowed.
    #format: iana:application/json
  imagesOutput:
    type:
      # array from minOccurs=1/maxOccurs=150
      # note: '{type: File}' not allowed
      - "File"
      - type: array
        items: File
    # Multiple formats (GeoTIFF, JP2)
    #format:
  measureOutput:
    # no way to provide unit of measure...?
    type: double
  stringOutput:
    type:
      type: enum
      symbols:
        - Value1
        - Value2
        - Value3
