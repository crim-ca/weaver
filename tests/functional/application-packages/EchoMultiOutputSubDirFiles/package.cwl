cwlVersion: "v1.2"
class: CommandLineTool
id: "EchoMultiOutputSubDirFiles"
doc: |
  Generates an output sub-directory hierarchy where files contained in them match by name.
  Although Weaver stages outputs separately by ID to avoid conflicts, the CWL itself is allowed to
  generate outputs with a mixture of files and collect them from the same source (glob) directory.
  Therefore, the internal execution logic of the CWL must be able to handle staging-out these files without
  conflicts (by replicating the structure), in order to avoid the auto-correction of 'fn.ext_{n}' by cwltool.
  Such extension adjustment would result in 'format' validation error (due to mismatching media-type extension)
  by Weaver WPS/CWL/Process resolution.

baseCommand:
  - bash
  - script.sh
requirements:
  DockerRequirement:
    dockerPull: debian:stretch-slim
  InitialWorkDirRequirement:
    listing:
      - entryname: script.sh
        entry: |
          set -x
          echo "Input: $1"
          mkdir -p "$(runtime.outdir)/outputs/out1"
          mkdir -p "$(runtime.outdir)/outputs/out2"
          mkdir -p "$(runtime.outdir)/outputs/out3"
          echo "{\"test\": \"$1\"}" > "$(runtime.outdir)/outputs/out1/test1.json"
          echo "{\"test\": \"$1\"}" > "$(runtime.outdir)/outputs/out2/test1.json"
          echo "{\"test\": \"$1\"}" > "$(runtime.outdir)/outputs/out3/test1.json"
          echo "{\"test\": \"$1\"}" > "$(runtime.outdir)/outputs/out1/test2.json"
          echo "{\"test\": \"$1\"}" > "$(runtime.outdir)/outputs/out2/test2.json"
          echo "{\"test\": \"$1\"}" > "$(runtime.outdir)/outputs/out3/test2.json"

inputs:
  message:
    type: string
    inputBinding:
      position: 1
outputs:
  output1:
    type: File[]
    format: "iana:application/json"
    outputBinding:
      glob: "$(runtime.outdir)/outputs/out1/*.json"
  output2:
    type: File[]
    format: "iana:application/json"
    outputBinding:
      glob: "$(runtime.outdir)/outputs/out2/*.json"
  output3:
    type: File[]
    format: "iana:application/json"
    outputBinding:
      glob: "$(runtime.outdir)/outputs/out3/*.json"

$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
