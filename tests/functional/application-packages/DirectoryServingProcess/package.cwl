cwlVersion: v1.0
class: CommandLineTool
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
          echo "Output: $(runtime.outdir)/output/"
          mkdir -p "$(runtime.outdir)/output/"
          cd "$(runtime.outdir)/output/"
          for file_path in $(inputs.input_file_paths); do
            echo "Writing [$(runtime.outdir)/output/$${file_path}]"
            dir_path=$(basename $${file_path})
            mkdir -p "$${dir_path}"
            echo "TEST" > "$${file_path}"
          done
          ls -R "$(runtime.outdir)/output/"
inputs:
  input_file_paths:
    type:
      type: array
      items: string
    inputBinding:
      position: 1
outputs:
  output_dir:
    type: Directory
    outputBinding:
      glob: "output/"
