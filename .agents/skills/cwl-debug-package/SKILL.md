---
name: cwl-debug-package
description: Debug CWL package issues including deployment failures, execution errors, and validation problems. Learn systematic troubleshooting approaches, common error patterns, and debugging techniques. Use when CWL packages fail to deploy or execute correctly.
license: Apache-2.0
compatibility: Requires cwltool for local testing. Works with CWL v1.0, v1.1, v1.2.
metadata:
  category: cwl-comprehension
  version: "1.0.0"
  author: CRIM
allowed-tools: file_read run_command http_request
---

# Debug CWL Packages

Systematic troubleshooting guide for CWL package deployment and execution issues.

## When to Use

- CWL package fails to deploy to Weaver
- Process executes but produces errors
- Validation warnings or errors
- Unexpected output or behavior
- Docker-related failures
- Input/output type mismatches

## Debugging Strategy

### 1. Validate Locally First

```bash
# Always validate before deploying
cwltool --validate package.cwl

# If validation passes, test with sample data
cwltool package.cwl test-inputs.json
```

### 2. Check Weaver Deployment

```bash
# Deploy and capture response
weaver deploy -u $WEAVER_URL -p my-process -b package.cwl

# Check if process is listed
weaver capabilities -u $WEAVER_URL | grep my-process

# Get process details
weaver describe -u $WEAVER_URL -p my-process
```

### 3. Test Execution

```bash
# Execute with test inputs
JOB_ID=$(weaver execute -u $WEAVER_URL -p my-process -I inputs.json -f json | jq -r .jobID)

# Monitor status
weaver status -u $WEAVER_URL -j $JOB_ID

# Check logs
weaver logs -u $WEAVER_URL -j $JOB_ID

# Check exceptions
weaver exceptions -u $WEAVER_URL -j $JOB_ID
```

## Common Errors and Solutions

### Validation Errors

#### Unknown Field

```
ERROR: Unknown field `DockerRequirment`
```

**Cause**: Typo in field name

**Solution**:

```yaml
# Wrong
DockerRequirment:  # Missing 'e'

# ✅ Correct
DockerRequirement:
  dockerPull: myimage:latest
```

#### Missing Required Field

```
ERROR: Missing required field `class`
```

**Solution**:

```yaml
cwlVersion: v1.2
class: CommandLineTool  # Must specify class
baseCommand: [echo]
```

#### Type Mismatch

```
ERROR: Expected type File, got string
```

**Solution**:

```yaml
# Wrong
inputs:
  input_file: string  # Should be File
```

```yaml
# ✅ Correct
inputs:
  input_file: File
```

### Deployment Errors

#### Invalid CWL Version

```text
ERROR: Unsupported CWL version v2.0
```

**Solution**:

```yaml
# Use supported version
cwlVersion: v1.2
class: CommandLineTool
```

#### Docker Image Not Found

```text
ERROR: Failed to pull Docker image 'myimage:latest'
```

**Solutions**:

```bash
# 1. Verify image exists
docker pull myimage:latest

# 2. Use full registry path
docker pull docker.io/library/myimage:latest

# 3. Check image name spelling
docker pull python:3.12-slim
```

#### Process ID Conflict

```
ERROR: Process 'my-process' already exists
```

**Solutions**:

```bash
# 1. Use different process ID
weaver deploy -u $WEAVER_URL -p my-process-v2 -b package.cwl

# 2. Undeploy existing process first
weaver undeploy -u $WEAVER_URL -p my-process
weaver deploy -u $WEAVER_URL -p my-process -b package.cwl
```

### Execution Errors

#### Missing Input

```text
ERROR: Required input 'input_file' not provided
```

**Solution**:

```json
{
  "input_file": {
    "class": "File",
    "path": "https://example.com/data.txt"
  }
}
```

#### Input Type Mismatch

```
ERROR: Expected File, got string
```

**Solution**:

❌ Incorrect reference for a File (not a string)

```json
{
  "input_file": "data.txt"
}
```

✅ Correct File input reference

```json
{
  "input_file": {
    "class": "File",
    "path": "https://example.com/data.txt"
  }
}
```

#### Command Not Found

```
ERROR: /bin/sh: mycommand: command not found
```

**Solutions**:

```yaml
# 1. Install command in Docker image
requirements:
  DockerRequirement:
    dockerPull: image-with-mycommand:latest
```

```yaml
# 2. Use full path
baseCommand: [/usr/local/bin/mycommand]
```

```yaml
# 3. Install via InitialWorkDirRequirement
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: install.sh
        entry: |
          #!/bin/bash
          apt-get update && apt-get install -y mycommand
```

#### Permission Denied

```
ERROR: Permission denied: /output/result.txt
```

**Solutions**:

```yaml
# 1. Ensure output directory is writable
outputs:
  result:
    type: File
    outputBinding:
      glob: "*.txt"  # Use glob pattern

# 2. Write to runtime.outdir
arguments:
  - -o
  - $(runtime.outdir)/result.txt
```

#### Output Not Found

```
ERROR: Output file 'result.txt' not found
```

**Solutions**:

```yaml
# 1. Check glob pattern
outputs:
  result:
    type: File
    outputBinding:
      glob: "result.txt"  # Exact match
```

```yaml
# 2. Use wildcard
outputs:
  result:
    type: File
    outputBinding:
      glob: "*.txt"  # Match any .txt file
```

```yaml
# 3. Verify command produces output
baseCommand: [echo, "test"]
stdout: result.txt  # Capture stdout
```

## Debugging Techniques

### Enable Verbose Logging

```bash
# Local testing with debug
cwltool --debug package.cwl inputs.json

# Weaver execution - check logs
weaver logs -u $WEAVER_URL -j $JOB_ID
```

### Test Incrementally

```yaml
# 1. Start with minimal CWL
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [echo, "hello"]
outputs:
  stdout: stdout
```

```yaml
# 2. Add inputs
inputs:
  message: string
baseCommand: [echo]
arguments: [$(inputs.message)]
```

```yaml
# 3. Add Docker
requirements:
  DockerRequirement:
    dockerPull: debian:stable-slim
```

### Isolate Issues

```bash
# Test each component separately

# 1. Test Docker image
docker run --rm myimage:latest mycommand --help

# 2. Test command locally
echo "test" | mycommand

# 3. Test with cwltool
cwltool package.cwl inputs.json

# 4. Test on Weaver
weaver execute -u $WEAVER_URL -p my-process -I inputs.json
```

### Check Intermediate Files

```yaml
# Add intermediate outputs for debugging
outputs:
  debug_output:
    type: Directory
    outputBinding:
      glob: .  # Capture all files in working directory
  
  final_output:
    type: File
    outputBinding:
      glob: result.txt
```

### Use Simple Test Data

Create minimal test inputs

```json
{
  "input_file": {
    "class": "File",
    "path": "test.txt",
    "contents": "test data\n"
  }
}
```

## Workflow-Specific Debugging

### Check Step Connections

```yaml
# Verify outputs match inputs
steps:
  step1:
    run: tool1.cwl
    in: {input: workflow_input}
    out: [output]  # Type: File
  
  step2:
    run: tool2.cwl
    in:
      input: step1/output  # Must expect File
    out: [result]
```

### Visualize Workflow

```bash
# Generate workflow diagram
cwltool --print-dot workflow.cwl | dot -Tpng > workflow.png
```

### Test Steps Individually

```bash
# Test each step separately
cwltool step1.cwl step1-inputs.json
cwltool step2.cwl step2-inputs.json

# Then test complete workflow
cwltool workflow.cwl workflow-inputs.json
```

## Docker-Specific Debugging

### Test Container Locally

```bash
# Run container interactively
docker run -it --rm myimage:latest /bin/bash

# Test command in container
docker run --rm myimage:latest mycommand --help

# Mount test data
docker run --rm -v $(pwd):/data myimage:latest mycommand /data/test.txt
```

### Check Image Availability

```bash
# Pull image
docker pull myimage:latest

# Inspect image
docker inspect myimage:latest

# List image tags
curl https://hub.docker.com/v2/repositories/myimage/tags/
```

### Debug Network Issues

```yaml
# Enable network access
requirements:
  NetworkAccess:
    networkAccess: true

# Test with curl/wget
baseCommand: [curl, -O, https://example.com/data.txt]
```

## Provenance and Statistics

### Check Execution Details

```bash
# Get detailed provenance
weaver provenance -u $WEAVER_URL -j $JOB_ID

# Get resource usage
weaver statistics -u $WEAVER_URL -j $JOB_ID

# Get inputs used
weaver inputs -u $WEAVER_URL -j $JOB_ID
```

## Common Pitfalls

### 1. Using `latest` Tags

```yaml
# ❌ Avoid
dockerPull: python:latest  # Unpredictable
```

```yaml
# ✅ Use specific versions
dockerPull: python:3.12.16-slim
```

### 2. Missing Output Glob

```yaml
# ❌ Output not found
outputs:
  result:
    type: File
    # Missing outputBinding!
```

```yaml
# ✅ Specify glob
outputs:
  result:
    type: File
    outputBinding:
      glob: "result.txt"
```

### 3. Incorrect Input Types

```yaml
# ❌ Type mismatch
inputs:
  file_input: string  # Should be File
```

```yaml
# ✅ Correct type
inputs:
  file_input: File
```

### 4. Forgetting Runtime Variables

```yaml
# ❌ Hardcoded path
arguments: ["-o", "/output/result.txt"]
```

```yaml
# ✅ Use runtime.outdir
arguments: ["-o", "$(runtime.outdir)/result.txt"]
```

### 5. Missing Requirements

```yaml
# ❌ No DockerRequirement
baseCommand: [python, script.py]  # Where does Python come from?
```

```yaml
# ✅ Specify Docker image
requirements:
  DockerRequirement:
    dockerPull: python:3.12-slim
baseCommand: [python, script.py]
```

## Debugging Checklist

- [ ] Validate with `cwltool --validate`
- [ ] Test locally with `cwltool`
- [ ] Check Docker image exists
- [ ] Verify input types match
- [ ] Check output glob patterns
- [ ] Test with minimal inputs
- [ ] Review Weaver logs
- [ ] Check exceptions
- [ ] Verify Docker requirements
- [ ] Test steps independently (workflows)
- [ ] Check runtime variables
- [ ] Verify network access (if needed)

## Related Skills

- [cwl-validate-package](../cwl-validate-package/) - Validate before deploying
- [process-deploy](../process-deploy/) - Deploy CWL packages
- [job-logs](../job-logs/) - View execution logs
- [job-exceptions](../job-exceptions/) - Get error details
- [job-status](../job-status/) - Monitor execution
- [cwl-understand-docker](../cwl-understand-docker/) - Docker troubleshooting

## Documentation

- [CWL Troubleshooting](https://www.commonwl.org/user_guide/)
- [cwltool Documentation](https://github.com/common-workflow-language/cwltool)
- [Weaver Process Deployment](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Docker Debugging](https://docs.docker.com/config/containers/runmetrics/)

## Tools

- **cwltool**: Local testing and validation
- **docker**: Container testing
- **jq**: JSON parsing for responses
- **curl**: API debugging

## Best Practices

1. ✅ Always validate locally first
2. ✅ Test with minimal data
3. ✅ Debug incrementally
4. ✅ Check logs and exceptions
5. ✅ Test Docker containers independently
6. ✅ Use specific image tags
7. ✅ Document known issues
8. ✅ Keep CWL packages simple
9. ✅ Version control your CWL
10. ✅ Learn from working examples
