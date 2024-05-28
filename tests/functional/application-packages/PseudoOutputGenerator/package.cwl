cwlVersion: "v1.2"
class: CommandLineTool

baseCommand:
  - bash
  - script.sh
requirements:
  DockerRequirement:
    dockerPull: debian:stretch-slim
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      - entryname: script.sh
        entry: |
          set -x
          echo "$(inputs.data)" > "image.jp2"
          echo "$(inputs.data)" > "image.tif"
          echo "$(inputs.data)" > "image.png"
          echo "$(inputs.data)" > "data.nc"
          echo "<xml>$(inputs.data)</xml>" > "text.xml"
          echo "$(inputs.data)" > "text.log"
          echo "$(inputs.data)" > "text.txt"
          echo "$(inputs.data)" > "text.abc"

inputs:
  data:
    type: string

outputs:
  image_jp2:
    type: File
    format: "iana:image/jp2"
    outputBinding:
      glob: image.jp2

  image_tif:
    type: File
    format: "iana:image/tiff"
    outputBinding:
      glob: image.tif

  image_png:
    type: File
    format: "iana:image/png"
    outputBinding:
      glob: image.png

  data_nc:
    type: File
    format: "ogc:netcdf"
    outputBinding:
      glob: data.nc

  text_xml:
    type: File
    format: "iana:text/xml"
    outputBinding:
      glob: text.xml

  text_log:
    type: File
    format: "iana:text/plain"
    outputBinding:
      glob: text.log

  text_txt:
    type: File
    format: "iana:text/plain"
    outputBinding:
      glob: text.txt

  no_format:
    type: File
    outputBinding:
      glob: text.txt

  unknown_format:
    type: File
    outputBinding:
      glob: text.abc

$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  ogc: "http://www.opengis.net/def/media-type/ogc/1.0/"
