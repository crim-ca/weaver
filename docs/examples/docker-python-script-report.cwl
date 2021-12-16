cwlVersion: v1.0
class: CommandLineTool
baseCommand:
  - python3
  - script.py
inputs:
  - id: amount
    type: int
  - id: cost
    type: float
outputs:
  - id: quote
    type: File
    outputBinding:
      glob: report.txt
requirements:
  DockerRequirement:
    dockerPull: "python:3.7-alpine"
  InitialWorkDirRequirement:
    listing:
      # below script is generated dynamically in the working directory, and then called by the base command
      - entryname: script.py
        entry: |
          amount = $(inputs.amount)
          cost = $(inputs.cost)
          with open("report.txt", "w") as report:
              report.write(f"Order Total: {amount * cost:0.2f}$\n")
