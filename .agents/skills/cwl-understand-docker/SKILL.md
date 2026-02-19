---
name: cwl-understand-docker
description: |
  Understand Docker requirements in CWL packages including DockerRequirement configuration, image
  selection, networking, and volume mounting. Learn best practices for containerized process
  execution in Weaver. Use when creating Docker-based CWL packages or troubleshooting Docker-related
  issues.
license: Apache-2.0
compatibility: Requires Docker understanding and CWL v1.0+. Docker must be available for local testing.
metadata:
---
# Understand Docker in CWL

Master Docker requirements and configuration in CWL packages for containerized process execution.

## When to Use

- Creating Docker-based CWL packages
- Selecting appropriate Docker images
- Troubleshooting Docker-related failures
- Optimizing Docker image usage
- Understanding container execution in Weaver
- Configuring volume mounts and networking

## DockerRequirement Basics

### Simple Docker Requirement

```yaml
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, script.py]

requirements:
  DockerRequirement:
    dockerPull: python:3.12-slim
```

### Docker with Specific Tag

```yaml
requirements:
  DockerRequirement:
    dockerPull: ubuntu:20.04  # Specific version, not 'latest'
```

### Custom Docker Image

```yaml
requirements:
  DockerRequirement:
    dockerPull: myregistry.io/myimage:v1.2.3
```

## Docker Image Selection

### Official Images (Recommended)

```yaml
DockerRequirement:
  dockerPull: python:3.12-slim      # Python
  dockerPull: node:16-alpine       # Node.js
  dockerPull: openjdk:11-jre-slim  # Java
  dockerPull: debian:bullseye-slim # Debian
  dockerPull: ubuntu:22.04         # Ubuntu
```

### Scientific Images

```yaml
DockerRequirement:
  dockerPull: continuumio/miniconda3:latest  # Conda
  dockerPull: jupyter/scipy-notebook:latest   # Scientific Python
  dockerPull: rocker/r-ver:4.2.0             # R
```

### Geospatial Images

```yaml
DockerRequirement:
  dockerPull: osgeo/gdal:ubuntu-small-latest  # GDAL
  dockerPull: ghcr.io/osgeo/proj:9.1.0        # PROJ
```

## Docker Image Best Practices

### Use Specific Tags

```yaml
# ❌ Bad - unpredictable
dockerPull: python:latest

# ✅ Good - reproducible
dockerPull: python:3.12.16-slim
```

### Prefer Slim/Alpine Variants

```yaml
# ❌ Large image (~1GB)
dockerPull: python:3.12

# ✅ Smaller image (~150MB)
dockerPull: python:3.12-slim

# ✅ Even smaller (~50MB, but may lack libraries)
dockerPull: python:3.12-alpine
```

### Pin Versions for Reproducibility

```yaml
# ✅ Exact version
dockerPull: myorg/myimage:1.2.3

# ✅ SHA256 digest (most precise)
dockerPull: myorg/myimage@sha256:abc123...
```

## Advanced Docker Configuration

### Environment Variables

```yaml
requirements:
  DockerRequirement:
    dockerPull: myimage:latest
  
  EnvVarRequirement:
    envDef:
      PYTHONUNBUFFERED: "1"
      TZ: "UTC"
      DATA_PATH: "/data"
```

### Network Access

```yaml
requirements:
  DockerRequirement:
    dockerPull: myimage:latest
  
  NetworkAccess:
    networkAccess: true  # Allow internet access
```

### Resource Limits

```yaml
requirements:
  DockerRequirement:
    dockerPull: myimage:latest
  
  ResourceRequirement:
    coresMin: 2
    coresMax: 4
    ramMin: 4096  # MB
    ramMax: 8192
    tmpdirMin: 1024
    outdirMin: 2048
```

## Working with Files in Docker

### Input Files

```yaml
# Files are automatically mounted into container
inputs:
  input_file:
    type: File
    inputBinding:
      position: 1
      # File will be available at: /tmp/path/filename
```

### Output Files

```yaml
outputs:
  output_file:
    type: File
    outputBinding:
      glob: "output.txt"  # Looked for in $(runtime.outdir)
```

### Directory Inputs

```yaml
inputs:
  input_dir:
    type: Directory
    inputBinding:
      position: 1
```

## Common Docker Patterns

### Python Script Execution

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
          print(f"Processing {sys.argv[1]}")

arguments:
  - script.py
  - $(inputs.input_file.path)

inputs:
  input_file: File

outputs:
  stdout_log:
    type: stdout
```

### Installing Dependencies

```yaml
requirements:
  DockerRequirement:
    dockerPull: python:3.12-slim
  
  InitialWorkDirRequirement:
    listing:
      - entryname: requirements.txt
        entry: |
          numpy==1.24.0
          pandas==1.5.3
      - entryname: install-deps.sh
        entry: |
          #!/bin/bash
          pip install -r requirements.txt

baseCommand: [bash, install-deps.sh, "&&", python, script.py]
```

### Running Shell Scripts

```yaml
requirements:
  DockerRequirement:
    dockerPull: bash:5.1

  InitialWorkDirRequirement:
    listing:
      - entryname: script.sh
        entry: |
          #!/bin/bash
          set -e
          echo "Processing..."
          # Your script here

baseCommand: [bash, script.sh]
```

## Docker Troubleshooting

### Image Pull Failures

**Problem**: Cannot pull image

```
Error: Failed to pull image 'myimage:latest'
```

**Solutions**:

```yaml
# 1. Check image exists
docker pull myimage:latest

# 2. Use full registry path
dockerPull: docker.io/library/myimage:latest

# 3. Check authentication (for private images)
# Weaver needs registry credentials configured
```

### Permission Issues

**Problem**: Cannot write files

```
Error: Permission denied writing to /output
```

**Solution**:

```yaml
# Run as specific user
requirements:
  DockerRequirement:
    dockerPull: myimage:latest
    # Note: User specification is environment-dependent
```

### Missing Dependencies

**Problem**: Command not found in container

```
Error: bash: mycommand: command not found
```

**Solutions**:

```yaml
# 1. Use image with command included
dockerPull: image-with-mycommand:latest

# 2. Install in InitialWorkDirRequirement
InitialWorkDirRequirement:
  listing:
    - entryname: install.sh
      entry: |
        apt-get update && apt-get install -y mycommand

# 3. Use conda/pip to install packages
```

### Network Access Issues

**Problem**: Cannot download files

```
Error: Unable to connect to remote server
```

**Solution**:

```yaml
requirements:
  NetworkAccess:
    networkAccess: true  # Enable network
```

## Docker Security Considerations

### Use Trusted Images

```yaml
# ✅ Official images
dockerPull: python:3.12-slim

# ✅ Verified publishers
dockerPull: bitnami/python:3.12

# ⚠️ Be cautious with unknown sources
dockerPull: randomuser/unknownimage:latest
```

### Minimize Image Size

```yaml
# Use multi-stage builds in your Dockerfile
FROM python:3.12 AS builder
# Install dependencies

FROM python:3.12-slim
# Copy only what's needed
```

### Keep Images Updated

```bash
# Regularly update pinned versions
dockerPull: python:3.12.17-slim  # Update from 3.9.16
```

## Integration with Weaver

### Deploy Docker-based Process

```bash
# 1. Create CWL with DockerRequirement
cat > process.cwl << 'EOF'
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, -c]
requirements:
  DockerRequirement:
    dockerPull: python:3.12-slim
arguments:
  - "print('Hello from Docker')"
outputs:
  stdout: stdout
EOF

# 2. Validate
cwltool --validate process.cwl

# 3. Deploy to Weaver
weaver deploy -u $WEAVER_URL -p docker-hello -b process.cwl
```

### Monitor Docker Execution

```bash
# Execute process
JOB_ID=$(weaver execute -u $WEAVER_URL -p docker-hello -f json | jq -r .jobID)

# Check logs (shows Docker execution)
weaver logs -u $WEAVER_URL -j $JOB_ID
```

## Related Skills

- [process-deploy](../process-deploy/) - Deploy Docker-based packages
- [cwl-validate-package](../cwl-validate-package/) - Validate Docker config
- [job-logs](../job-logs/) - Debug Docker execution
- [job-exceptions](../job-exceptions/) - Handle Docker errors
- [cwl-debug-package](../cwl-debug-package/) - Troubleshoot Docker issues

## Documentation

- [CWL DockerRequirement](https://www.commonwl.org/v1.2/CommandLineTool.html#DockerRequirement)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Weaver Docker Support](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [Docker Hub](https://hub.docker.com/)

## Tools

- **docker pull**: Test image availability
- **docker run**: Test container locally
- **dive**: Analyze image layers
- **trivy**: Scan for vulnerabilities

## Best Practices Summary

1. ✅ Use specific image tags (not `latest`)
2. ✅ Prefer official and verified images
3. ✅ Use slim/alpine variants when possible
4. ✅ Pin versions for reproducibility
5. ✅ Test locally before deploying
6. ✅ Enable NetworkAccess if needed
7. ✅ Handle file permissions appropriately
8. ✅ Keep images updated and secure
9. ✅ Document why specific images are chosen
10. ✅ Consider image size and pull time
