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
    # warning:
    #   When using an expression for 'format', the full URI must be specified.
    #   Using 'iana:application/geo+json' results in an error by cwltool
    #   (see https://github.com/common-workflow-language/cwltool/issues/2033).
    format: |
      ${
        if (Array.isArray(inputs.features)) {
          return "https://www.iana.org/assignments/media-types/application/geo+json";
        }
        return "http://www.opengis.net/def/glossary/term/FeatureCollection";
      }
    loadContents: true
    inputBinding:
      valueFrom: |
        ${
          if (Array.isArray(inputs.features)) {
            return JSON.stringify({
              "type": "FeatureCollection",
              "features": inputs.features.map(item => JSON.parse(item.contents))
            });
          }
          return inputs.features.contents;
        }
outputs:
  features:
    type: File
    format: "ogc-term:FeatureCollection"
    outputBinding:
      glob: "features.geojson"
stdout: "features.geojson"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  ogc-term: "http://www.opengis.net/def/glossary/term/"
