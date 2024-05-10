cwlVersion: "v1.2"
class: CommandLineTool
# WARNING:
#   Use a script instead of using 'echo' command, which would write to the secret to stdout and be displayed!
#   A script using secrets could have other standard output messages that are relevant to log.
#   It is up to the application developer to make sure they do no echo their own secrets...
# baseCommand: echo
baseCommand: python
arguments: ["echo.py"]
requirements:
  DockerRequirement:
    dockerPull: "docker.io/python:3-slim"
  InitialWorkDirRequirement:
    listing:
      - entryname: echo.py
        entry: |
          import sys
          with open("out.txt", mode="w", encoding="utf-8") as f:
              f.write(sys.argv[1])
          print("OK!")  # print on purpose to test stdout includes only this, and not the secret input
hints:
  cwltool:Secrets:
    secrets:
      - message
$namespaces:
  cwltool: http://commonwl.org/cwltool#
inputs:
  message:
    type: string
    inputBinding:
      position: 1
outputs:
  output:
    type: File
    outputBinding:
      glob: "out.txt"
stdout: "stdout.log"
