---
name: cwl-create-commandlinetool
description: Create CWL CommandLineTool packages from scratch including proper structure, inputs, outputs, and requirements. Learn best practices for wrapping command-line tools and creating reusable process definitions. Use when creating new CWL packages for Weaver deployment.
license: Apache-2.0
compatibility: Requires understanding of command-line tools and CWL basics. Supports CWL v1.0, v1.1, v1.2.
metadata:
  category: cwl-comprehension
  version: "1.0.0"
  author: CRIM
allowed-tools: file_write file_read
---

# Create CWL CommandLineTool

Learn to create well-structured CWL CommandLineTool packages from scratch.

## When to Use

- Wrapping a command-line tool for Weaver
- Creating a new process definition
- Converting existing scripts to CWL
- Building reusable process components
- Standardizing tool execution

## Basic Structure

### Minimal CommandLineTool

```yaml
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [echo]

inputs:
  message:
    type: string
    inputBinding:
      position: 1

outputs:
  output:
    type: stdout
```

### Complete Template

```yaml
cwlVersion: v1.2
class: CommandLineTool

label: Process Name
doc: |
  Detailed description of what this process does.
  Include usage examples and expected behavior.

baseCommand: [command, subcommand]

requirements:
  DockerRequirement:
    dockerPull: appropriate-image:version

inputs:
  required_input:
    type: File
    label: Required input file
    doc: Description of this input
    inputBinding:
      position: 1
      prefix: --input
  
  optional_param:
    type: string?
    default: "default_value"
    inputBinding:
      position: 2
      prefix: --param

outputs:
  output_file:
    type: File
    label: Output result
    doc: Description of output
    outputBinding:
      glob: "output.txt"

stdout: output.log
stderr: error.log
```

## Building Inputs

### Simple Literal Input
```yaml
inputs:
  threshold:
    type: float
    doc: "Threshold value (0.0-1.0)"
    inputBinding:
      position: 1
      prefix: -t
```

### File Input
```yaml
inputs:
  input_file:
    type: File
    label: "Input data file"
    doc: "NetCDF or GeoTIFF file"
    format:
      - edam:format_3650  # NetCDF
      - edam:format_3591  # GeoTIFF
    inputBinding:
      position: 1
      prefix: --input
```

### Array Input
```yaml
inputs:
  input_files:
    type: File[]
    doc: "Multiple input files"
    inputBinding:
      position: 1
      prefix: --files
      itemSeparator: ","  # Creates: --files file1,file2,file3
```

### Optional Input
```yaml
inputs:
  optional_flag:
    type: boolean?
    default: false
    inputBinding:
      prefix: --verbose
```

### Input with Default
```yaml
inputs:
  output_format:
    type: string
    default: "netcdf"
    inputBinding:
      position: 2
      prefix: --format
```

## InputBinding Configuration

### Position
```yaml
# Command will be: tool input1 input2 output
inputs:
  input1:
    type: File
    inputBinding:
      position: 1  # First argument
  
  input2:
    type: File
    inputBinding:
      position: 2  # Second argument
  
  output_name:
    type: string
    inputBinding:
      position: 3  # Third argument
```

### Prefix
```yaml
# Creates: tool --input file.txt --format json
inputs:
  input_file:
    type: File
    inputBinding:
      prefix: --input
  
  format:
    type: string
    inputBinding:
      prefix: --format
```

### Separate vs Together
```yaml
# Separate: --input file.txt
inputs:
  input_with_space:
    type: File
    inputBinding:
      prefix: --input
      separate: true  # Default
```
```yaml
# Together: --input=file.txt
inputs:
  input_no_space:
    type: File
    inputBinding:
      prefix: --input
      separate: false
```

### Value From Expression
```yaml
inputs:
  input_file:
    type: File
    inputBinding:
      position: 1
      valueFrom: $(self.basename)  # Use just filename, not full path
```

## Building Outputs

### File Output
```yaml
outputs:
  output_file:
    type: File
    outputBinding:
      glob: "result.txt"  # Exact filename
```

### Multiple Files
```yaml
outputs:
  output_files:
    type: File[]
    outputBinding:
      glob: "*.txt"  # All .txt files
```

### Directory Output
```yaml
outputs:
  output_dir:
    type: Directory
    outputBinding:
      glob: "results/"
```

### Standard Streams
```yaml
outputs:
  stdout_output:
    type: stdout

  stderr_output:
    type: stderr

stdout: output.log
stderr: error.log
```

### Conditional Output
```yaml
outputs:
  optional_output:
    type: File?  # Optional output
    outputBinding:
      glob: "optional.txt"
```

## Requirements

### Docker
```yaml
requirements:
  DockerRequirement:
    dockerPull: python:3.12-slim
```

### Initial Work Directory
```yaml
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: script.py
        entry: |
          #!/usr/bin/env python3
          print("Hello from Python")
      
      - entryname: config.json
        entry: |
          {"setting": "value"}
      
      - $(inputs.input_file)  # Stage input file
```

### Resource Requirements
```yaml
requirements:
  ResourceRequirement:
    coresMin: 2
    coresMax: 4
    ramMin: 4096  # MB
    ramMax: 8192
    tmpdirMin: 10240
    outdirMin: 10240
```

### Environment Variables
```yaml
requirements:
  EnvVarRequirement:
    envDef:
      PATH: "/usr/local/bin:$(PATH)"
      PYTHONUNBUFFERED: "1"
```

### Inline JavaScript
```yaml
requirements:
  InlineJavascriptRequirement: {}

inputs:
  value:
    type: int
    inputBinding:
      valueFrom: $(self * 2)  # Double the input value
```

## Advanced Patterns

### Conditional Arguments
```yaml
inputs:
  verbose:
    type: boolean?
    default: false

arguments:
  - valueFrom: |
      ${
        if (inputs.verbose) {
          return "--verbose";
        } else {
          return null;
        }
      }
```

### Dynamic Output Names
```yaml
inputs:
  input_file:
    type: File

outputs:
  output_file:
    type: File
    outputBinding:
      glob: |
        ${
          return inputs.input_file.nameroot + "_processed.txt";
        }
```

### Capture Success/Exit Codes
```yaml
successCodes: [0]
temporaryFailCodes: [1, 2]  # Retry these
permanentFailCodes: [3, 4]  # Don't retry these

outputs:
  exit_code:
    type: int
    outputBinding:
      glob: .
      outputEval: $(runtime.exitCode)
```

## Complete Examples

### Simple Python Script
```yaml
cwlVersion: v1.2
class: CommandLineTool

baseCommand: [python]

requirements:
  DockerRequirement:
    dockerPull: python:3.12-slim
  InitialWorkDirRequirement:
    listing:
      - entryname: script.py
        entry: |
          import sys
          with open(sys.argv[1]) as f:
              data = f.read()
          with open('output.txt', 'w') as f:
              f.write(data.upper())

arguments:
  - script.py
  - $(inputs.input_file.path)

inputs:
  input_file:
    type: File

outputs:
  output_file:
    type: File
    outputBinding:
      glob: output.txt
```

### Command with Multiple Options
```yaml
cwlVersion: v1.2
class: CommandLineTool

label: Image Processor
doc: Process images with various filters

baseCommand: [convert]

requirements:
  DockerRequirement:
    dockerPull: dpokidov/imagemagick:7.1.0-57

inputs:
  input_image:
    type: File
    doc: "Input image file"
    inputBinding:
      position: 1
  
  resize:
    type: string?
    doc: "Resize dimensions (e.g., 800x600)"
    inputBinding:
      prefix: -resize
  
  quality:
    type: int?
    default: 90
    doc: "JPEG quality (1-100)"
    inputBinding:
      prefix: -quality
  
  output_format:
    type: string
    default: "jpg"
    doc: "Output format"

arguments:
  - valueFrom: "output.$(inputs.output_format)"
    position: 100

outputs:
  output_image:
    type: File
    outputBinding:
      glob: "output.*"
```

## Testing Your CWL

### Local Validation
```bash
cwltool --validate my-tool.cwl
```

### Local Execution
```bash
# Create test inputs
cat > test-inputs.json << EOF
{
  "input_file": {
    "class": "File",
    "path": "test.txt"
  },
  "threshold": 0.5
}
EOF

# Run
cwltool my-tool.cwl test-inputs.json
```

### Deploy to Weaver
```bash
weaver deploy -u $WEAVER_URL -p my-tool -b my-tool.cwl
```

## Best Practices

1. **Use descriptive names**: Clear input/output names
2. **Add documentation**: Use `doc` and `label` fields
3. **Specify types clearly**: Be explicit with types
4. **Use proper positions**: Order arguments logically
5. **Pin Docker versions**: Use specific image tags
6. **Test locally first**: Use cwltool before deploying
7. **Handle optional inputs**: Use `?` for optional
8. **Capture all outputs**: Don't lose important files
9. **Use runtime variables**: `$(runtime.outdir)`, etc.
10. **Version your CWL**: Track changes

## Related Skills

- [cwl-validate-package](../cwl-validate-package/) - Validate your CWL
- [cwl-understand-docker](../cwl-understand-docker/) - Docker configuration
- [cwl-debug-package](../cwl-debug-package/) - Debug issues
- [process-deploy](../process-deploy/) - Deploy to Weaver
- [cwl-understand-workflow](../cwl-understand-workflow/) - Chain tools

## Documentation

- [CWL CommandLineTool Specification](https://www.commonwl.org/v1.2/CommandLineTool.html)
- [CWL User Guide](https://www.commonwl.org/user_guide/)
- [Weaver Package Guide](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [CWL Examples](https://github.com/common-workflow-language/workflows)

## Templates

See the examples in this skill as starting templates for your own CWL packages!
