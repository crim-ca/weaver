---
name: process-package
description: |
  Retrieve the CWL application package definition for a deployed process. Returns the complete
  Common Workflow Language document describing the process implementation. Use when you need to
  inspect, version control, or replicate process definitions.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
---
# Get Process Package

Retrieve the CWL application package definition for a deployed process.

## When to Use

- Inspecting process implementation details
- Version controlling process definitions
- Replicating processes to other Weaver instances
- Debugging process execution issues
- Understanding process requirements and dependencies

## Parameters

### Required

- **process\_id** (string): Process identifier

### Optional

- **provider** (string): Provider for remote processes
- **output** (file path): Save package to file

## CLI Usage

```bash
# View package in console
weaver package -u $WEAVER_URL -p my-process

# Save to file
weaver package -u $WEAVER_URL -p my-process -o process-package.cwl

# Get package from remote provider
weaver package -u $WEAVER_URL -P my-provider -p remote-process -o remote.cwl
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get package
package = client.package(process_id="my-process")

print(package.body)  # CWL document

# Save to file
with open("process.cwl", "w") as f:
    import yaml
    yaml.dump(package.body, f)
```

## API Request

```bash
GET /processes/my-process/package
Accept: application/cwl+yaml
```

## Returns

CWL application package in YAML or JSON format:

```yaml
cwlVersion: v1.2
class: CommandLineTool
baseCommand: process-command
inputs:
  input1:
    type: File
    inputBinding:
      position: 1
outputs:
  output1:
    type: File
    outputBinding:
      glob: "*.out"
requirements:
  DockerRequirement:
    dockerPull: myimage:latest
```

## Error Handling

- **404 Not Found**: Process does not exist
- **403 Forbidden**: Insufficient permissions

## Related Skills

- [process-deploy](../process-deploy/) - Deploy CWL package
- [process-describe](../process-describe/) - Get process metadata
- [job-execute](../job-execute/) - Run the process

## Documentation

- [Process Package](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [CWL Specification](https://www.commonwl.org/v1.0/)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
