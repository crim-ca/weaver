cwlVersion: "v1.2"
class: CommandLineTool
baseCommand: echo
requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: "debian:stretch-slim"
inputs:
  features:
    type:
      - type: File
        format: "oap:geojson-feature-collection"
      - type: array
        items:
          type: File
          format: "oap:geojson-feature"
    inputBinding:
      valueFrom: |
        ${
          if (Array.isArray(inputs.features)) {
            return {
              "type": "FeatureCollection",
              "features": inputs.features.every(item => item.contents)
              )
            };
          }
          return inputs.features.contents;
        }
outputs:
  features:
    type: File
    format: "oap:geojson-feature-collection"
    outputBinding:
      glob: "features.json"
stdout: "features.json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  oap: "http://www.opengis.net/def/format/ogcapi-processes/0/"
