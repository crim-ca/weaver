---
name: cwl-optimize-performance
description: Optimize CWL package performance including resource allocation, Docker image selection, scatter patterns, and execution strategies. Learn techniques to improve execution speed and resource efficiency. Use when processes are slow, use too many resources, or need optimization.
license: Apache-2.0
compatibility: Requires Weaver deployment and CWL v1.0+.
metadata:
  category: cwl-comprehension
  version: "1.0.0"
  author: CRIM
allowed-tools: http_request file_read
---

# Optimize CWL Package Performance

Techniques to improve CWL package execution speed and resource efficiency.

## When to Use

- Processes take too long to execute
- Docker images are large and slow to pull
- Resource allocation is inefficient
- Parallel processing opportunities exist
- Jobs fail due to resource limits
- Optimizing workflow execution time

## Docker Image Optimization

### Use Slim/Alpine Variants

```yaml
# ❌ Slow - large image (~1GB)
DockerRequirement:
  dockerPull: python:3.12
```

```yaml
# ✅ Faster - slim image (~150MB)
DockerRequirement:
  dockerPull: python:3.12-slim
```

```yaml
# ✅ Smallest - alpine (~50MB)
DockerRequirement:
  dockerPull: python:3.12-alpine
```

### Pin Specific Versions

```yaml
# ❌ Slow - always pulls latest
DockerRequirement:
  dockerPull: myimage:latest
```

```yaml
# ✅ Fast - cached after first pull
DockerRequirement:
  dockerPull: myimage:1.2.3
```

### Use Digest for Immutability

```yaml
# ✅ Best - never changes, cached forever
DockerRequirement:
  dockerPull: python@sha256:abc123...
```

### Pre-pull Images

```bash
# Pull images before workflow execution
docker pull python:3.12-slim
docker pull gdal:3.6.0-alpine
```

## Resource Requirements

### Right-size Resources

```yaml
requirements:
  ResourceRequirement:
    # ✅ Appropriate for task
    coresMin: 2
    coresMax: 4
    ramMin: 4096      # 4GB
    ramMax: 8192      # 8GB
    tmpdirMin: 10240  # 10GB temp
    outdirMin: 20480  # 20GB output
```

### Dynamic Resource Allocation

```yaml
requirements:
  InlineJavascriptRequirement: {}
  ResourceRequirement:
    # Scale RAM with input file size
    ramMin: |
      ${
        var sizeMB = inputs.input_file.size / (1024 * 1024);
        return Math.max(2048, Math.ceil(sizeMB * 3));
      }
    
    # Scale cores with number of inputs
    coresMin: |
      ${
        return Math.min(8, Math.max(2, inputs.files.length));
      }
```

### Avoid Over-allocation

```yaml
# ❌ Wastes resources
ResourceRequirement:
  ramMin: 64000  # 64GB for a simple task
  coresMin: 32
```

```yaml
# ✅ Appropriate allocation
ResourceRequirement:
  ramMin: 4096   # 4GB
  coresMin: 2
```

## Parallel Processing with Scatter

### Basic Scatter

```yaml
steps:
  process:
    run: tool.cwl
    scatter: input_file  # Process files in parallel
    in:
      input_file: input_files
    out: [output]
```

### Scatter Multiple Inputs

```yaml
steps:
  process:
    run: tool.cwl
    scatter: [file, parameter]
    scatterMethod: dotproduct  # Pair inputs
    in:
      file: files
      parameter: parameters
    out: [output]
```

### Optimal Scatter Size

```yaml
# ❌ Too fine-grained - overhead dominates
scatter: tiny_chunks  # 1000s of 1MB files
```

```yaml
# ✅ Balanced - good parallelism
scatter: reasonable_chunks  # Dozens of 100MB files
```

```yaml
# ❌ Too coarse - underutilizes resources
scatter: huge_chunks  # 2-3 multi-GB files
```

## Input/Output Optimization

### Minimize Data Transfer

```yaml
# ❌ Transfers entire large file
inputs:
  full_dataset:
    type: File  # 10GB file
```

```yaml
# ✅ Transfer only needed subset
inputs:
  subset_params:
    type: string  # Small parameters
# Tool downloads only needed data
```

### Use File References

```yaml
# ✅ Pass by reference when possible
{
  "input_file": {
    "class": "File",
    "path": "https://example.com/large-file.nc"  # Weaver downloads
  }
}
```

### Stream When Possible

```yaml
# ✅ Process streams instead of files
baseCommand: [curl, https://example.com/data.txt]
stdout: processed.txt

# Pipes directly without intermediate file
```

### Efficient Output Patterns

```yaml
# ❌ Returns many small files
outputs:
  results:
    type: File[]
    outputBinding:
      glob: "*.txt"  # 1000s of tiny files
```

```yaml
# ✅ Returns aggregated results
outputs:
  results:
    type: File
    outputBinding:
      glob: "combined-results.tar.gz"  # Single archive
```

## Workflow Structure Optimization

### Minimize Steps

```yaml
# ❌ Too many small steps
steps:
  step1: download.cwl
  step2: unzip.cwl
  step3: validate.cwl
  step4: process.cwl
```

```yaml
# ✅ Combined operations
steps:
  process:  # Does download, unzip, validate, process
    run: optimized-process.cwl
```

### Parallel Independent Steps

```yaml
# ✅ Steps that can run in parallel
steps:
  process_a:
    run: tool-a.cwl
    in: {input: data}
    out: [output_a]
  
  process_b:  # Runs simultaneously with process_a
    run: tool-b.cwl
    in: {input: data}
    out: [output_b]
  
  combine:  # Waits for both
    run: merge.cwl
    in:
      a: process_a/output_a
      b: process_b/output_b
    out: [merged]
```

### Cache Intermediate Results

```yaml
# ✅ Expose intermediate results for reuse
outputs:
  preprocessed:  # Can be reused
    type: File
    outputSource: preprocess/output
  
  final:
    type: File
    outputSource: analyze/output
```

## Command Optimization

### Efficient Commands

```yaml
# ❌ Inefficient
baseCommand: [bash, -c]
arguments:
  - "cat file.txt | grep pattern | sort | uniq > output.txt"
```

```yaml
# ✅ More efficient
baseCommand: [grep, pattern]
stdin: file.txt
stdout: output.txt
```

### Avoid Unnecessary Operations

```yaml
# ❌ Reads entire file into memory
baseCommand: [python, -c]
arguments:
  - "open('huge.txt').read()"
```

```yaml
# ✅ Streams data
baseCommand: [awk, '{print $1}']
```

### Use Native Tools

```yaml
# ❌ Python for simple text operations
DockerRequirement:
  dockerPull: python:3.12-slim
baseCommand: [python, -c, "print('hello')"]
```

```yaml
# ✅ Simple shell command
DockerRequirement:
  dockerPull: alpine:latest
baseCommand: [echo, hello]
```

## Monitoring and Profiling

### Track Resource Usage

```bash
# Get job statistics
weaver statistics -u $WEAVER_URL -j $JOB_ID

# Check execution time
weaver status -u $WEAVER_URL -j $JOB_ID | jq '.duration'

# View logs for bottlenecks
weaver logs -u $WEAVER_URL -j $JOB_ID
```

### Identify Bottlenecks

```yaml
# Add timing to steps
steps:
  download:
    run: download.cwl
    # Check logs to see how long this takes
  
  process:
    run: process.cwl
    # Compare durations
```

### Profile Locally

```bash
# Time local execution
time cwltool process.cwl inputs.json

# Check resource usage
docker stats
```

## Caching Strategies

### Docker Image Caching

```yaml
# ✅ Use versioned tags for caching
DockerRequirement:
  dockerPull: myimage:1.2.3  # Cached after first use
```

### Intermediate File Caching

```yaml
# ✅ Reuse expensive preprocessing
steps:
  expensive_preprocess:
    run: preprocess.cwl
    in: {input: raw_data}
    out: [preprocessed]  # Cache this
  
  analyze:
    run: analyze.cwl
    in: {input: expensive_preprocess/preprocessed}
    out: [result]
```

## Common Performance Issues

### Issue: Slow Docker Pull

```yaml
# Problem: Large image
DockerRequirement:
  dockerPull: tensorflow/tensorflow:latest-gpu  # 4GB+
```

```yaml
# Solutions:
# 1. Use smaller base image
DockerRequirement:
  dockerPull: tensorflow/tensorflow:2.11.0-gpu-slim

# 2. Pre-pull images
# 3. Use private registry closer to Weaver

# 4. Build custom minimal image
```

### Issue: Memory Overflow

```yaml
# Problem: Insufficient RAM
ResourceRequirement:
  ramMin: 2048
```

```yaml
# Solution: Increase based on data size
ResourceRequirement:
  ramMin: |
    ${
      var dataSizeMB = inputs.data.size / (1024 * 1024);
      return Math.max(4096, dataSizeMB * 4);
    }
```

### Issue: Slow File I/O

```yaml
# Problem: Reading entire file
baseCommand: [python, -c]
arguments:
  - "data = open('huge.csv').read()"
```

```yaml
# Solution: Stream processing
baseCommand: [python, -c]
arguments:
  - |
    import sys
    for line in sys.stdin:
        process(line)
stdin: huge.csv
```

### Issue: Sequential Processing

```yaml
# Problem: Processing items one by one
steps:
  process:
    run: tool.cwl
    # No scatter - sequential
```

```yaml
# Solution: Scatter for parallelism
steps:
  process:
    run: tool.cwl
    scatter: item
    in: {item: items}
    out: [output]
```

## Benchmarking

### Compare Approaches

```bash
# Approach 1
time weaver execute -u $WEAVER_URL -p approach1 -I inputs.json

# Approach 2
time weaver execute -u $WEAVER_URL -p approach2 -I inputs.json

# Compare statistics
weaver statistics -u $WEAVER_URL -j $JOB1
weaver statistics -u $WEAVER_URL -j $JOB2
```

### A/B Testing

```yaml
# Test different resource allocations
# Version A: Conservative
ResourceRequirement:
  ramMin: 4096
  coresMin: 2
```

```yaml
# Version B: Generous
ResourceRequirement:
  ramMin: 8192
  coresMin: 4

# Measure which performs better
```

## Best Practices Summary

1. ✅ Use slim Docker images
2. ✅ Pin image versions for caching
3. ✅ Right-size resource allocations
4. ✅ Use scatter for parallel processing
5. ✅ Minimize data transfer
6. ✅ Combine small steps
7. ✅ Profile and measure
8. ✅ Cache expensive operations
9. ✅ Stream large data when possible
10. ✅ Use appropriate tools for tasks

## Related Skills

- [cwl-understand-docker](../cwl-understand-docker/) - Docker optimization
- [cwl-understand-workflow](../cwl-understand-workflow/) - Workflow patterns
- [cwl-debug-package](../cwl-debug-package/) - Debug performance issues
- [job-statistics](../job-statistics/) - Monitor resource usage

## Documentation

- [CWL Resource Requirements](https://www.commonwl.org/v1.2/CommandLineTool.html#ResourceRequirement)
- [Scatter Feature](https://www.commonwl.org/v1.2/Workflow.html#WorkflowStep)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Weaver Performance](https://pavics-weaver.readthedocs.io/en/latest/processes.html)

## Measurement

Track these metrics for optimization:

- **Execution time**: Start to finish duration
- **Docker pull time**: Image download duration
- **Resource usage**: CPU, RAM, Disk I/O
- **Data transfer**: Input/output transfer time
- **Queue time**: Time waiting for resources

Optimize the biggest bottleneck first!
