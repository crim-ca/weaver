#!/usr/bin/env cwl-runner
# WARNING:
#   This process can generate a large memory load and a very large output file that captures the generated data.
#   Even with default ResourceRequirement values, the output can become substantial rapidly.
cwlVersion: "v1.0"
class: CommandLineTool
baseCommand:
  - bash
  - script.sh
requirements:
  DockerRequirement:
    dockerPull: debian:stretch-slim
  InitialWorkDirRequirement:
    listing:
      # below script is generated dynamically in the working directory, and then called by the base command
      # reference: https://unix.stackexchange.com/a/254976/288952
      - entryname: script.sh
        entry: |
          echo "Will allocate RAM chunks of $(inputs.ram_chunks) MiB."
          echo "Will allocate RAM chunks in increments up to $(inputs.ram_amount) times."
          echo "Will maintain allocated RAM load for $(inputs.time_duration)s for each increment."
          echo "Will wait $(inputs.time_interval)s between each allocation."
          echo "Begin allocating memory..."
          for index in \$(seq $(inputs.ram_amount)); do
              echo "Allocating \$index x $(inputs.ram_chunks) MiB for $(inputs.time_duration)s..."
              cat <( </dev/zero head -c \$((\$index * $(inputs.ram_chunks)))m) <(sleep $(inputs.time_duration)) | tail
              echo "Waiting for $(inputs.time_interval)s..."
              sleep $(inputs.time_interval)
          done
          echo "Finished allocating memory..."
inputs:
  ram_chunks:
    type: int
  ram_amount:
    type: int
  time_duration:
    type: float
  time_interval:
    type: float
outputs:
  output:
    type: File
    outputBinding:
      glob: "stdout.log"
stdout: stdout.log
