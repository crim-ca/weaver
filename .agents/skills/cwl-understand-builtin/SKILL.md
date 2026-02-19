---
name: cwl-understand-builtin
description: |
  Use Weaver's built-in processes including jsonarray2netcdf, file2string\_array, and other utility
  processes. Learn when to use builtins instead of custom Docker containers for common operations.
  Use to simplify workflows and avoid unnecessary Docker complexity.
license: Apache-2.0
compatibility: Requires Weaver deployment with builtin processes enabled.
metadata:
---
# Understand Weaver Built-in Processes

Learn to use Weaver's built-in utility processes for common operations without custom Docker containers.

## When to Use

- Converting data formats (JSON to NetCDF)
- Splitting or combining files
- Simple text processing
- Avoiding Docker overhead for simple operations
- Chaining builtins in workflows
- Quick prototyping without custom containers

## What are Built-in Processes?

Built-in processes are pre-deployed utility processes in Weaver that perform common operations without requiring custom
Docker images or CWL packages.

### Benefits

- ✅ No Docker image required
- ✅ Faster execution (no image pull)
- ✅ Always available in Weaver
- ✅ Well-tested and maintained
- ✅ Simpler CWL definitions

## Available Built-in Processes

### jsonarray2netcdf

Convert JSON array data to NetCDF format.

**Use Cases**:

- Converting API responses to NetCDF
- Creating NetCDF from structured data
- Data format conversion in workflows

**Inputs**:

- `input`: JSON array or file
- `x_variable`: X-axis variable name
- `y_variable`: Y-axis variable name
- `z_variable`: Data variable name

**Outputs**:

- `output`: NetCDF file

**Example**:

```yaml
cwlVersion: v1.2
class: Workflow

steps:
  convert:
    run: "https://weaver.example.com/processes/jsonarray2netcdf"
    in:
      input: json_data
      x_variable: {default: "lon"}
      y_variable: {default: "lat"}
      z_variable: {default: "temperature"}
    out: [output]
```

### file2string\_array

Convert a file to an array of strings (one per line).

**Use Cases**:

- Reading configuration files
- Processing line-based data
- Splitting file content for parallel processing

**Inputs**:

- `file`: Input text file

**Outputs**:

- `output`: Array of strings

**Example**:

```yaml
steps:
  read_file:
    run: "https://weaver.example.com/processes/file2string_array"
    in:
      file: config_file
    out: [output]
  
  process_lines:
    run: process-line.cwl
    scatter: line
    in:
      line: read_file/output
    out: [result]
```

## Discovering Built-in Processes

### List All Built-ins

```bash
# List processes (built-ins typically don't have visibility tag or have special marker)
weaver capabilities -u $WEAVER_URL

# Look for processes without custom deployment
```

### Describe Built-in Process

```bash
# Get detailed information
weaver describe -u $WEAVER_URL -p jsonarray2netcdf

# View inputs and outputs
weaver describe -u $WEAVER_URL -p file2string_array -f json | jq '.inputs'
```

## Using Built-ins in Workflows

### Simple Conversion Workflow

```yaml
cwlVersion: v1.2
class: Workflow

inputs:
  json_input: File

outputs:
  netcdf_output:
    type: File
    outputSource: convert/output

steps:
  convert:
    run:
      class: CommandLineTool
      # Reference built-in by its process ID
      id: jsonarray2netcdf
    in:
      input: json_input
    out: [output]
```

### Chaining Built-ins

```yaml
cwlVersion: v1.2
class: Workflow

inputs:
  data_file: File

outputs:
  final_result:
    type: File
    outputSource: convert/output

steps:
  # Split file into lines
  split:
    run: file2string_array
    in:
      file: data_file
    out: [output]
  
  # Process could continue with custom processing
  # Then convert back
  convert:
    run: string_array2file
    in:
      input: split/output
    out: [output]
```

### Mixing Built-ins with Custom Processes

```yaml
cwlVersion: v1.2
class: Workflow

steps:
  # Use built-in for format conversion
  to_netcdf:
    run: jsonarray2netcdf
    in:
      input: json_data
    out: [output]
  
  # Use custom process for analysis
  analyze:
    run: custom-analysis.cwl  # Your custom CWL
    in:
      input: to_netcdf/output
    out: [result]
  
  # Use built-in for final conversion
  to_json:
    run: netcdf2jsonarray
    in:
      input: analyze/result
    out: [output]
```

## Common Patterns

### Data Format Pipeline

```yaml
# JSON → NetCDF → Process → GeoTIFF
steps:
  json_to_nc:
    run: jsonarray2netcdf
    in: {input: raw_json}
    out: [output]
  
  process:
    run: analysis.cwl
    in: {input: json_to_nc/output}
    out: [result]
  
  nc_to_geotiff:
    run: netcdf2geotiff
    in: {input: process/result}
    out: [output]
```

### File Processing Pipeline

```yaml
# File → Lines → Process Each → Combine
steps:
  split_lines:
    run: file2string_array
    in: {file: input_file}
    out: [output]
  
  process_each:
    run: process-line.cwl
    scatter: line
    in: {line: split_lines/output}
    out: [processed]
  
  combine:
    run: array2file
    in: {lines: process_each/processed}
    out: [output]
```

## When to Use Built-ins vs Custom

### Use Built-ins When:

- ✅ Simple format conversion
- ✅ Basic string/file operations
- ✅ Quick prototyping
- ✅ Avoiding Docker overhead
- ✅ Operation matches built-in capability exactly

### Use Custom CWL When:

- ❌ Complex processing logic
- ❌ Specific software dependencies
- ❌ Custom algorithms
- ❌ Performance-critical operations
- ❌ Unique requirements

## Built-in Limitations

### Not Customizable

Built-ins have fixed behavior - you can't modify them.

**Workaround**: Chain built-ins with custom processes

```yaml
steps:
  builtin_convert:
    run: jsonarray2netcdf
    in: {input: data}
    out: [output]
  
  custom_post_process:
    run: my-custom-tool.cwl
    in: {input: builtin_convert/output}
    out: [result]
```

### Limited Operations

Built-ins only cover common operations.

**Workaround**: Use as pre/post-processing steps

```yaml
steps:
  preprocess:
    run: file2string_array  # Built-in
    in: {file: input}
    out: [lines]
  
  main_process:
    run: complex-analysis.cwl  # Custom
    in: {data: preprocess/lines}
    out: [result]
```

### Version Locked

Built-in behavior tied to Weaver version.

**Workaround**: Document Weaver version requirements

```yaml
# In process metadata
metadata:
  weaverVersion: ">=6.0.0"
```

## Executing Built-in Processes

### Direct Execution

```bash
# Execute jsonarray2netcdf
weaver execute \
  -u $WEAVER_URL \
  -p jsonarray2netcdf \
  -I inputs.json

# inputs.json:
{
  "input": {"href": "https://example.com/data.json"},
  "x_variable": "longitude",
  "y_variable": "latitude",
  "z_variable": "temperature"
}
```

### In Workflow Context

```bash
# Deploy workflow using built-ins
weaver deploy -u $WEAVER_URL -p my-workflow -b workflow.cwl

# Execute workflow
weaver execute -u $WEAVER_URL -p my-workflow -I workflow-inputs.json
```

## Best Practices

### 1. Check Availability

```bash
# Verify built-in exists before using
weaver describe -u $WEAVER_URL -p jsonarray2netcdf
```

### 2. Document Built-in Usage

```yaml
# Add comments in CWL
steps:
  convert:
    # Using Weaver built-in jsonarray2netcdf
    # Converts JSON array to NetCDF format
    run: jsonarray2netcdf
    in: {input: json_data}
    out: [output]
```

### 3. Handle Built-in Errors

```yaml
# Built-ins can fail like any process
# Check job status and logs
```

### 4. Version Compatibility

```yaml
# Document Weaver version requirements
# Different Weaver versions may have different built-ins
```

### 5. Combine with Custom Processes

```yaml
# Use built-ins for common operations
# Use custom CWL for specific logic
```

## Related Skills

- [process-list](../process-list/) - List all available processes including built-ins
- [process-describe](../process-describe/) - Get built-in process details
- [cwl-understand-workflow](../cwl-understand-workflow/) - Chain built-ins in workflows
- [job-execute](../job-execute/) - Execute built-in processes
- [process-deploy](../process-deploy/) - Deploy workflows using built-ins

## Documentation

- [Weaver Built-in Processes](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [Process Deployment](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Workflow Examples](https://pavics-weaver.readthedocs.io/en/latest/processes.html)

## Examples

### Complete Workflow with Built-ins

```yaml
cwlVersion: v1.2
class: Workflow

doc: |
  Workflow demonstrating built-in process usage.
  1. Split input file into lines
  2. Process each line in parallel
  3. Convert results to NetCDF

inputs:
  input_file: File
  config: string

outputs:
  final_output:
    type: File
    outputSource: to_netcdf/output

steps:
  split:
    run: file2string_array
    in:
      file: input_file
    out: [output]
  
  process:
    run: custom-processor.cwl
    scatter: line
    in:
      line: split/output
      config: config
    out: [result]
  
  to_netcdf:
    run: jsonarray2netcdf
    in:
      input: process/result
      z_variable: {default: "data"}
    out: [output]
```

## Tips

- 💡 Built-ins are faster (no Docker pull)
- 💡 Use for simple, common operations
- 💡 Chain with custom processes for complex workflows
- 💡 Check built-in availability in target Weaver instance
- 💡 Document which built-ins your workflow depends on
- 💡 Consider built-ins for prototyping before creating custom Docker images
