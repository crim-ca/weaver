---
name: api-info
description: |
  Retrieve general API information including server details, supported endpoints, API version, and
  contact information. Use to verify Weaver instance availability and get basic service metadata.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
---
# Get API Information

Retrieve general API information and server metadata.

## When to Use

- Verifying Weaver instance availability
- Getting API endpoints and capabilities
- Checking server configuration
- Discovering supported features
- Integration and connectivity testing

## Parameters

None required - operates on the base API URL.

## CLI Usage

```bash
# Get API information
weaver info -u $WEAVER_URL

# Check if server is responding
weaver info -u https://weaver.example.com
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get API info
info = client.info()

print(f"API Title: {info.body.get('title')}")
print(f"Description: {info.body.get('description')}")
print(f"Contact: {info.body.get('contact')}")

# Check available endpoints
for link in info.body.get("links", []):
    print(f"{link['rel']}: {link['href']}")
```

## API Request

```bash
GET /
Accept: application/json
```

## Returns

```json
{
  "title": "Weaver",
  "description": "Weaver: OGC API - Processes with Workflow Capabilities",
  "attribution": "© 2020-2026 CRIM",
  "type": "application",
  "configuration": "HYBRID",
  "contact": {
    "name": "CRIM",
    "url": "https://crim.ca"
  },
  "links": [
    {
      "rel": "service-desc",
      "type": "application/openapi+json;version=3.0",
      "title": "OpenAPI definition",
      "href": "https://weaver.example.com/api"
    },
    {
      "rel": "processes",
      "type": "application/json",
      "title": "List of processes",
      "href": "https://weaver.example.com/processes"
    },
    {
      "rel": "jobs",
      "type": "application/json",
      "title": "List of jobs",
      "href": "https://weaver.example.com/jobs"
    },
    {
      "rel": "providers",
      "type": "application/json",
      "title": "List of providers",
      "href": "https://weaver.example.com/providers"
    }
  ]
}
```

**Note**: Response may include additional fields. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Response Fields

### Server Information

- **title**: Service title
- **description**: Service description
- **attribution**: Copyright and attribution
- **configuration**: Weaver mode (EMS, ADES, HYBRID)

### Contact Information

- **name**: Organization name
- **url**: Organization website
- **email**: Contact email (if provided)

### Links

- **service-desc**: OpenAPI specification
- **processes**: Process listing endpoint
- **jobs**: Job listing endpoint
- **providers**: Provider listing endpoint
- **conformance**: Conformance declaration

## Configuration Modes

- **EMS**: Execution Management Service (orchestrates remote ADES)
- **ADES**: Application Deployment and Execution Service (local execution)
- **HYBRID**: Both EMS and ADES capabilities

## Use Cases

### Health Check

```bash
# Quick availability check
if weaver info -u $WEAVER_URL > /dev/null 2>&1; then
    echo "Weaver is available"
else
    echo "Weaver is not responding"
fi
```

### Service Discovery

```python
# Discover available endpoints
info = client.info()

endpoints = {link["rel"]: link["href"] for link in info.body["links"]}
print(f"Processes endpoint: {endpoints.get('processes')}")
print(f"Jobs endpoint: {endpoints.get('jobs')}")
```

### Configuration Check

```python
# Verify Weaver mode
info = client.info()
config = info.body.get("configuration")

if config == "HYBRID":
    print("This Weaver supports both local and remote execution")
elif config == "EMS":
    print("This Weaver orchestrates remote ADES instances")
elif config == "ADES":
    print("This Weaver performs local execution only")
```

## Related Skills

- [api-version](../api-version/) - Get detailed version information
- [api-conformance](../api-conformance/) - Check OGC conformance
- [process-list](../process-list/) - Browse available processes
- [provider-list](../provider-list/) - View registered providers

## Documentation

- [API Root](https://pavics-weaver.readthedocs.io/en/latest/api.html)
- [Configuration](https://pavics-weaver.readthedocs.io/en/latest/configuration.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
