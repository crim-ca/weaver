---
name: cwl-understand-workflow
description: Understand CWL Workflow class structures for chaining multiple processing steps. Learn how to connect outputs to inputs, manage data flow between steps, and create complex multi-step workflows. Use when building workflows that chain multiple processes together.
license: Apache-2.0
compatibility: Requires understanding of CWL CommandLineTool basics. Supports CWL v1.0, v1.1, v1.2.
metadata:
  category: cwl-comprehension
  version: "1.0.0"
  author: CRIM
allowed-tools: file_read
---

# Understand CWL Workflows

Learn to create and understand CWL Workflow class structures for chaining multiple processing steps.

## When to Use

- Building multi-step data processing pipelines
- Chaining multiple tools together
- Understanding workflow execution order
- Debugging workflow step connections
- Optimizing data flow between steps

## Workflow Basics

### Workflow vs CommandLineTool

**CommandLineTool**: Single process execution

```yaml
class: CommandLineTool  # Runs one command
baseCommand: [process]
```

**Workflow**: Chain multiple steps

```yaml
class: Workflow  # Chains multiple tools
steps:
  step1: ...
  step2: ...
```

## Simple Workflow Example

```yaml
cwlVersion: v1.2
class: Workflow

inputs:
  input_file: File
  threshold: float

outputs:
  final_output:
    type: File
    outputSource: step2/output

steps:
  step1:
    run: preprocess.cwl
    in:
      input: input_file
    out: [processed]
  
  step2:
    run: analyze.cwl
    in:
      data: step1/processed
      threshold: threshold
    out: [output]
```

## Workflow Components

### 1. Inputs

Workflow-level inputs that can be used by any step:

```yaml
inputs:
  input_files:
    type: File[]  # Array of files
  parameter:
    type: string
    default: "default_value"
  optional_param:
    type: string?  # Optional input
```

### 2. Outputs

Final outputs from the workflow:

```yaml
outputs:
  result:
    type: File
    outputSource: final_step/output  # From which step
  
  intermediate:
    type: File
    outputSource: step1/output  # Can expose intermediate results
```

### 3. Steps

Individual processing steps:

```yaml
steps:
  step_name:
    run:  # Inline tool definition
      class: CommandLineTool
      baseCommand: [echo]
    
    in:  # Map workflow inputs to step inputs
      step_input: workflow_input
      another: some_step/output
    
    out: [output1, output2]  # Step outputs
```

The `run` can also reference an external CWL file.

> ⚠️ WARNING:
> The referenced `tool.cwl` should be a corresponding pre-existing process (where ID would be `tool`) for
> this CWL to succeed [Weaver deployment](../process-deploy).

```yaml
steps:
  step_name:
    run: tool.cwl  # CWL file to run
```

## Data Flow Patterns

### Sequential Processing

```yaml
steps:
  download:
    run: download.cwl
    in: {url: input_url}
    out: [file]
  
  process:
    run: process.cwl
    in: {input: download/file}  # Uses output from download
    out: [result]
  
  upload:
    run: upload.cwl
    in: {file: process/result}  # Uses output from process
    out: [location]
```

### Parallel Processing

```yaml
steps:
  # These can run in parallel (no dependencies)
  process_a:
    run: tool-a.cwl
    in: {input: input_file}
    out: [output_a]
  
  process_b:
    run: tool-b.cwl
    in: {input: input_file}  # Same input, independent processing
    out: [output_b]
  
  # This waits for both to complete
  merge:
    run: merge.cwl
    in:
      file_a: process_a/output_a
      file_b: process_b/output_b
    out: [merged]
```

### Scatter/Gather Pattern

```yaml
steps:
  process_many:
    run: process-one.cwl
    scatter: input_file  # Run on each file
    in:
      input_file: input_files  # Array input
    out: [output]  # Array output
  
  combine:
    run: combine.cwl
    in:
      files: process_many/output  # Array of outputs
    out: [combined]
```

## Advanced Workflow Features

### ScatterMethod

```yaml
steps:
  process:
    run: tool.cwl
    scatter: [input1, input2]  # Scatter over multiple inputs
    scatterMethod: dotproduct  # How to combine
    # dotproduct: pair inputs (1with1, 2with2)
    # nested_crossproduct: all combinations
    # flat_crossproduct: all combinations, flatten
    in:
      input1: files_a
      input2: files_b
    out: [output]
```

### Conditional Execution (CWL v1.2+)

```yaml
steps:
  optional_step:
    run: tool.cwl
    when: $(inputs.do_process)  # Only run if true
    in:
      do_process: run_optional
      input: data
    out: [output]
```

### SubWorkflows

```yaml
steps:
  sub_workflow:
    run: another-workflow.cwl  # Run a workflow as a step
    in:
      workflow_input: my_input
    out: [workflow_output]
```

## Common Workflow Patterns

### Preprocessing Pipeline

```yaml
steps:
  validate:
    run: validate.cwl
    in: {input: raw_data}
    out: [validated]
  
  clean:
    run: clean.cwl
    in: {input: validate/validated}
    out: [cleaned]
  
  transform:
    run: transform.cwl
    in: {input: clean/cleaned}
    out: [transformed]
  
  analyze:
    run: analyze.cwl
    in: {data: transform/transformed, params: parameters}
    out: [results]
```

### Map-Reduce Pattern

```yaml
steps:
  # Map: process each item
  map:
    run: mapper.cwl
    scatter: item
    in: {item: input_items}
    out: [mapped]
  
  # Reduce: combine results
  reduce:
    run: reducer.cwl
    in: {items: map/mapped}
    out: [result]
```

## Debugging Workflows

### Visualize Workflow

```bash
# Generate workflow diagram
cwltool --print-dot workflow.cwl | dot -Tpng > workflow.png
```

### Check Step Connections

```bash
# Validate connections
cwltool --validate workflow.cwl

# Print execution plan
cwltool --print-deps workflow.cwl inputs.json
```

### Test Individual Steps

```bash
# Test each step separately
cwltool step1.cwl step1-inputs.json
cwltool step2.cwl step2-inputs.json
```

### Enable Debug Output

```bash
# See detailed execution
cwltool --debug workflow.cwl inputs.json
```

## Requirements for Workflows

### Subworkflow Feature

```yaml
requirements:
  SubworkflowFeatureRequirement: {}
```

### Scatter Feature

```yaml
requirements:
  ScatterFeatureRequirement: {}
```

### Multiple Input Feature

```yaml
requirements:
  MultipleInputFeatureRequirement: {}
```

### Step Input Expression

```yaml
requirements:
  StepInputExpressionRequirement: {}

steps:
  process:
    run: tool.cwl
    in:
      computed_input:
        valueFrom: $(inputs.x + inputs.y)  # Compute from other inputs
```

## Weaver Workflow Example

Complete workflow for data processing:

```yaml
cwlVersion: v1.2
class: Workflow

requirements:
  ScatterFeatureRequirement: {}

inputs:
  netcdf_files: File[]
  region: string

outputs:
  statistics:
    type: File
    outputSource: compute_stats/output

steps:
  subset:
    run: subset-by-region.cwl
    scatter: input_file
    in:
      input_file: netcdf_files
      region: region
    out: [subset_file]
  
  compute_stats:
    run: compute-statistics.cwl
    in:
      input_files: subset/subset_file
    out: [output]
```

## Related Skills

- [process-deploy](../process-deploy/) - Deploy workflow to Weaver
- [job-execute](../job-execute/) - Execute workflow
- [job-provenance](../job-provenance/) - Track workflow execution
- [cwl-validate-package](../cwl-validate-package/) - Validate workflow
- [cwl-debug-package](../cwl-debug-package/) - Debug workflow issues

## Documentation

- [CWL Workflows](https://www.commonwl.org/user_guide/23-scatter-workflow/)
- [Weaver Workflows](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [Workflow Patterns](https://www.commonwl.org/user_guide/)
- [Process Chaining](https://pavics-weaver.readthedocs.io/en/latest/processes.html)

## Best Practices

1. **Keep steps modular** - Each step should do one thing well
2. **Use descriptive names** - Clear step and variable names
3. **Document data flow** - Comment complex connections
4. **Test incrementally** - Verify each step works before chaining
5. **Handle errors** - Consider what happens if a step fails
6. **Optimize scatter** - Use appropriate scatterMethod for your use case
7. **Version control** - Track workflow changes
