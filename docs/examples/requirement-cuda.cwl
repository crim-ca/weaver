#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: CommandLineTool
baseCommand: nvidia-smi
requirements:
  cwltool:CUDARequirement:
    cudaVersionMin: "11.2"
    cudaComputeCapability: "7.5"
    cudaDeviceCountMin: 1
    cudaDeviceCountMax: 4
$namespaces:
  cwltool: "http://commonwl.org/cwltool#"
inputs: {}
outputs:
  output:
    type: File
    outputBinding:
      glob: output.txt
stdout: output.txt
