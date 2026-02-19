---
name: api-conformance
description: Retrieve the OGC API - Processes conformance classes that the Weaver instance implements. Shows which parts of the OGC standard are supported. Use to verify compliance and feature availability.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: system-information
  version: "1.0.0"
  api_endpoint: GET /conformance
  cli_command: weaver conformance
  author: CRIM
allowed-tools: http_request
---

# Check Conformance

Retrieve OGC API - Processes conformance classes implemented by Weaver.

## When to Use

- Verifying OGC standards compliance
- Checking which features are supported
- Validating integration compatibility
- Testing interoperability
- Documenting system capabilities

## Parameters

None required.

## CLI Usage

```bash
# Get conformance classes
weaver conformance -u $WEAVER_URL

# Check specific feature support
weaver conformance -u $WEAVER_URL | grep -i "deploy"
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get conformance
conformance = client.conformance()

# Check supported conformance classes
for uri in conformance.body.get("conformsTo", []):
    print(uri)

# Check specific feature
if "http://www.opengis.net/spec/ogcapi-processes-2/1.0/conf/deploy-replace-undeploy" in conformance.body["conformsTo"]:
    print("Supports process deployment")
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/conformance"
```

## Returns

```json
{
  "conformsTo": [
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/ogc-process-description",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/job-list",
    "http://www.opengis.net/spec/ogcapi-processes-2/1.0/conf/deploy-replace-undeploy",
    "http://www.opengis.net/spec/ogcapi-processes-3/0.0/conf/workflows",
    "http://www.opengis.net/spec/ogcapi-processes-4/1.0/conf/job-management"
  ]
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Conformance Classes

### OGC API - Processes Part 1: Core
- **core**: Basic process execution
- **ogc-process-description**: Standard process descriptions
- **json**: JSON encoding support
- **job-list**: Job listing capability

### OGC API - Processes Part 2: Deploy, Replace, Undeploy (DRU)
- **deploy-replace-undeploy**: Dynamic process deployment
- **ogcapppkg**: OGC Application Package support
- **cwl**: Common Workflow Language support

### OGC API - Processes Part 3: Workflows and Chaining
- **workflows**: Workflow execution support
- **chaining**: Process chaining capabilities

### OGC API - Processes Part 4: Job Management
- **job-management**: Enhanced job operations
- **job-callback**: Notification callbacks
- **job-dismiss**: Job cancellation

## Feature Detection

### Check Process Deployment Support
```python
conformance = client.conformance()
conforms_to = conformance.body.get("conformsTo", [])

has_deployment = any("deploy" in uri for uri in conforms_to)
if has_deployment:
    print("This Weaver supports dynamic process deployment")
```

### Check Workflow Support
```bash
if weaver conformance -u $WEAVER_URL | grep -q "workflows"; then
    echo "Workflow chaining is supported"
else
    echo "Workflow chaining not available"
fi
```

### Check Job Management
```python
conforms_to = client.conformance().body["conformsTo"]

features = {
    "Job Listing": any("job-list" in uri for uri in conforms_to),
    "Job Dismissal": any("dismiss" in uri for uri in conforms_to),
    "Job Callbacks": any("callback" in uri for uri in conforms_to),
}

for feature, supported in features.items():
    status = "✓" if supported else "✗"
    print(f"{status} {feature}")
```

## Use Cases

### Compatibility Testing
```python
# Test if client and server are compatible
required_features = [
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json"
]

conformance = client.conformance()
supported = conformance.body.get("conformsTo", [])

compatible = all(feature in supported for feature in required_features)
if compatible:
    print("Server is compatible with client requirements")
```

### Feature Documentation
```bash
# Generate feature report
echo "Weaver Capabilities Report"
echo "========================="
weaver version -u $WEAVER_URL
echo ""
echo "Supported OGC Features:"
weaver conformance -u $WEAVER_URL | grep -o 'processes-[0-9]/.*' | sort -u
```

## Related Skills

- [api-info](../api-info/) - Get general API information
- [api-version](../api-version/) - Check version
- [process-list](../process-list/) - See what processes are available
- [process-deploy](../process-deploy/) - Use deployment if supported

## Documentation

- [OGC API - Processes Conformance](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Supported Features](https://pavics-weaver.readthedocs.io/en/latest/index.html#implementations)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
- [OGC API - Processes Specification](https://docs.ogc.org/is/18-062r2/18-062r2.html)
