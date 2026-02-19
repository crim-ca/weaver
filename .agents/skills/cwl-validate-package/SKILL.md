---
name: cwl-validate-package
description: |
  Validate CWL package syntax and structure before deployment to Weaver. Check for syntax errors,
  Docker requirements, input/output definitions, and CWL version compatibility. Use to catch errors
  early and ensure package quality before deployment.
license: Apache-2.0
compatibility: Requires cwltool installed locally. Supports CWL v1.0, v1.1, v1.2.
metadata:
---

# Validate CWL Package

Validate CWL package syntax and structure before deploying to Weaver.

## When to Use

- Before deploying a new process to catch errors early
- When creating or modifying CWL packages
- To verify Docker requirements are properly specified
- When troubleshooting package deployment failures
- To ensure CWL version compatibility

## Parameters

### Required

- **package\_file** (path): CWL file to validate (.cwl or .yaml)

### Optional

- **strict** (boolean): Enable strict validation mode
- **check\_docker** (boolean): Verify Docker images are accessible

## CLI Usage

```bash
# Basic validation
cwltool --validate process.cwl

# Validate with strict mode
cwltool --validate --strict process.cwl

# Validate and check requirements
cwltool --print-pre --validate process.cwl

# Validate workflow with dependencies
cwltool --validate workflow.cwl
```

## Validation Checks

### Syntax Validation

- CWL version compatibility
- YAML/JSON structure
- Required fields present
- Type definitions correct

### Semantic Validation

- Input/output types match
- Command line bindings valid
- File paths resolvable
- Expressions syntax correct

### Docker Validation

- DockerRequirement properly formatted
- Image names valid
- Tags specified (recommended)

### Workflow Validation

- Step names unique
- Input/output connections valid
- No circular dependencies
- All required inputs provided

## Common Issues and Fixes

### Issue: "Unknown field 'xyz'"

```yaml
# ❌ Wrong - typo in field name
DockerRequirment:  # Missing 'e'
  dockerPull: image

# ✅ Correct
DockerRequirement:
  dockerPull: image
```

### Issue: "Type mismatch"

```yaml
# ❌ Wrong - string where File expected
inputs:
  input_file: string
```

```yaml
# ✅ Correct
inputs:
  input_file: File
```

### Issue: "Missing required field"

```yaml
# ❌ Wrong - missing class
cwlVersion: v1.2
```

```yaml
# ✅ Correct
cwlVersion: v1.2
class: CommandLineTool
```

### Issue: "Invalid expression"

```yaml
# ❌ Wrong - incorrect JavaScript syntax
arguments: ["$(runtime.outdir"]  # Missing closing )
```

```yaml
# ✅ Correct
arguments: ["$(runtime.outdir)"]
```

## Example: Valid CWL Package

```yaml
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [echo]

requirements:
  DockerRequirement:
    dockerPull: debian:stable-slim

inputs:
  message:
    type: string
    inputBinding:
      position: 1

outputs:
  output:
    type: stdout

stdout: output.txt
```

## Validation Output

### Success

```
process.cwl is valid CWL
```

### Errors

```
ERROR process.cwl:5:1: Unknown field `DockerRequirment`
  Did you mean `DockerRequirement`?
```

## Advanced Validation

### Check Docker Images

```bash
# Verify Docker image exists
docker pull $(grep dockerPull process.cwl | cut -d: -f2-)
```

### Test Locally

```bash
# Run with sample inputs
cwltool process.cwl inputs.json
```

### Validate Against Schema

```bash
# Use CWL schema validator
schema-salad-tool --print-jsonld-context process.cwl
```

## Integration with Weaver

After validation, deploy to Weaver:

```bash
# 1. Validate locally
cwltool --validate process.cwl

# 2. Test with sample data
cwltool process.cwl test-inputs.json

# 3. Deploy to Weaver
weaver deploy -u $WEAVER_URL -p my-process -b process.cwl
```

## Related Skills

- [process-deploy](../process-deploy/) - Deploy validated package
- [cwl-debug-package](../cwl-debug-package/) - Debug validation failures
- [cwl-understand-docker](../cwl-understand-docker/) - Docker requirements
- [job-exceptions](../job-exceptions/) - Debug deployment errors

## Documentation

- [CWL Application Packages](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [CWL Specification](https://www.commonwl.org/v1.2/)
- [CWL User Guide](https://www.commonwl.org/user_guide/)
- [Process Deployment](https://pavics-weaver.readthedocs.io/en/latest/processes.html)

## Tools

- **cwltool**: Reference CWL implementation
- **schema-salad**: CWL schema validator
- **Docker**: For testing Docker-based packages

## Best Practices

1. **Always validate** before deploying to Weaver
2. **Use specific Docker tags** (not `latest`)
3. **Test locally** with sample data
4. **Document inputs/outputs** with descriptions
5. **Pin CWL version** explicitly (v1.0, v1.1, v1.2)
