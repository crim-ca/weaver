---
name: process-describe
description: Retrieve detailed information about a deployed process including inputs, outputs, metadata, and execution requirements. Use when you need to understand process capabilities or validate before execution.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: process-management
  version: "1.0.0"
  api_endpoint: GET /processes/{process_id}
  cli_command: weaver describe
  author: CRIM
allowed-tools: http_request
---

# Describe Process

Retrieve complete process description including inputs, outputs, and metadata.

## When to Use

- Understanding process capabilities before execution
- Discovering required and optional inputs
- Checking expected output formats
- Validating process availability
- Getting CWL package information

## Parameters

### Required
- **process_id** (string): Process identifier to describe

### Optional
- **provider** (string): Provider identifier for remote processes
- **schema** (string): Schema format ("OGC", "OLD", "WPS")

## CLI Usage

```bash
# Describe local process
weaver describe -u $WEAVER_URL -p my-process

# Describe remote provider process
weaver describe -u $WEAVER_URL -P my-provider -p remote-process

# Get specific schema format
weaver describe -u $WEAVER_URL -p my-process --schema OGC
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get description
description = client.describe(process_id="my-process")

# Print inputs
for input_id, input_spec in description.body["inputs"].items():
    print(f"{input_id}: {input_spec.get('title', input_id)}")
    print(f"  Type: {input_spec.get('format', {}).get('mediaType', 'literal')}")
    print(f"  Required: {input_spec.get('minOccurs', 0) > 0}")
```

## Returns

Process description includes:

- **id**: Process identifier
- **title**: Human-readable name
- **abstract**: Description of what it does
- **version**: Process version
- **inputs**: Input specifications with types and constraints
- **outputs**: Output specifications with formats
- **keywords**: Associated keywords/tags
- **metadata**: Additional metadata
- **jobControlOptions**: Supported execution modes (async, sync)
- **outputTransmission**: Supported output modes (reference, value)

## Example Response

```json
{
  "id": "ndvi-calculator",
  "title": "NDVI Calculator",
  "description": "Calculate Normalized Difference Vegetation Index from satellite imagery",
  "version": "1.0.0",
  "inputs": {
    "red_band": {
      "title": "Red Band Image",
      "minOccurs": 1,
      "maxOccurs": 1,
      "formats": [
        {"mediaType": "image/tiff"}
      ]
    },
    "nir_band": {
      "title": "Near-Infrared Band Image",
      "minOccurs": 1,
      "maxOccurs": 1,
      "formats": [
        {"mediaType": "image/tiff"}
      ]
    }
  },
  "outputs": {
    "ndvi": {
      "title": "NDVI Output",
      "formats": [
        {"mediaType": "image/tiff"}
      ]
    }
  }
}
```

## Related Skills

- [process-list](../process-list/) - Discover available processes
- [process-deploy](../process-deploy/) - Deploy new process
- [job-execute](../job-execute/) - Run the process

## Documentation

- [Process Description](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
