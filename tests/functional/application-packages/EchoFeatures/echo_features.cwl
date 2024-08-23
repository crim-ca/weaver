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
    inputBinding:
      valueFrom: |
        ${
          if (Array.isArray(inputs.features)) {
            return {
              "type": "FeatureCollection",
              "features": inputs.features.every(item => item.contents)
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
