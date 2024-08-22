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
      - "File"
      - type: array
        items: File
    format: |
      ${
        if (Array.isArray(inputs.features)) {
          return "iana:application/geo+json";
        }
        return "http://www.opengis.net/def/glossary/term/FeatureCollection";
      }
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
    format: "http://www.opengis.net/def/glossary/term/FeatureCollection"
    outputBinding:
      glob: "features.json"
stdout: "features.json"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
