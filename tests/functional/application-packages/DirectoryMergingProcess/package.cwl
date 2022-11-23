cwlVersion: v1.0
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
          outdir="$(runtime.outdir)/output/" 
          echo "Input: $(inputs.files.length) files"
          echo "Output: \${outdir}"
          mkdir -p "\${outdir}"
          
          file_array=(${
            var cmd = "";
            for (var i = 0; i < inputs.files.length; i++) {
               cmd += "\"" + inputs.files[i].path + "\" ";
            }
            return cmd;
          });
          
          for file_path in \${file_array[@]}; do
            file_name="\$(basename \${file_path})"
            echo "Writing [\${file_name}]"
            cp "\${file_path}" "\${outdir}"
          done
          ls -R "\${outdir}"
inputs:
  files:
    type:
      type: array
      items: File
    inputBinding:
      position: 1
outputs:
  output_dir:
    type: Directory
    outputBinding:
      glob: "output/"
