---
name: provider-register
description: Register an external WPS or OGC API - Processes service as a remote provider, making its processes available through Weaver. Enables federation of services and distributed workflow execution. Use when integrating remote processing services.
license: Apache-2.0
compatibility: Requires Weaver API access with provider registration permissions.
metadata:
  category: provider-management
  version: "1.0.0"
  api_endpoint: POST /providers
  cli_command: weaver register
  author: CRIM
allowed-tools: http_request
---

# Register Provider

Register an external WPS or OGC API - Processes service as a remote provider.

## When to Use

- Integrating external WPS services
- Connecting to remote OGC API - Processes instances
- Building federated processing networks
- Enabling distributed workflow execution
- Accessing specialized remote processing capabilities
- Implementing multi-organization collaborations

## Parameters

### Required

- **provider\_id** (string): Unique provider identifier
- **url** (string): Provider service URL

### Optional

- **type** (string): Provider type
  - `wps`: WPS 1.0/2.0 service
  - `ogcapi`: OGC API - Processes
  - `esgf`: ESGF processing service
- **public** (boolean): Whether provider is publicly accessible (default: true)
- **auth** (object): Authentication credentials (if required)

## CLI Usage

```bash
# Register WPS provider
weaver register -u $WEAVER_URL -n my-wps-provider -w https://remote-wps.example.com/wps

# Register OGC API - Processes provider
weaver register -u $WEAVER_URL -n my-ogc-provider -w https://remote-ogc.example.com/processes

# Register with authentication
weaver register -u $WEAVER_URL -n secure-provider -w https://secure.example.com/wps --auth token:SECRET_TOKEN
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Register provider
result = client.register(
    provider_id="my-provider",
    url="https://remote.example.com/wps",
    type="wps",
    public=True
)

if result.success:
    print(f"Provider registered: {result.body['id']}")
```

## API Request

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
  "id": "my-provider",
  "url": "https://remote.example.com/wps",
  "type": "wps",
  "public": true
}' \
  "${WEAVER_URL}/providers"
```

## Returns

```json
{
  "id": "my-provider",
  "url": "https://remote.example.com/wps",
  "type": "wps",
  "public": true,
  "status": "registered"
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Provider Types

### WPS (Web Processing Service)

- Supports WPS 1.0.0 and 2.0.0
- Automatic process discovery via GetCapabilities
- Execute operations via WPS Execute

### OGC API - Processes

- Modern RESTful API
- JSON-based communication
- Standardized endpoints

### ESGF

- Earth System Grid Federation services
- Climate data processing
- Specialized scientific workflows

## After Registration

Once registered, you can:

```bash
# List processes from provider
weaver capabilities -u $WEAVER_URL -P my-provider

# Describe remote process
weaver describe -u $WEAVER_URL -P my-provider -p remote-process

# Execute remote process
weaver execute -u $WEAVER_URL -P my-provider -p remote-process -I inputs.json
```

## Use Cases

### Federated Workflows

```python
# Register multiple providers
for provider_name, provider_url in providers.items():
    client.register(provider_id=provider_name, url=provider_url)

# Execute distributed workflow
step1 = client.execute(provider="provider1", process_id="preprocess", ...)
step2 = client.execute(provider="provider2", process_id="analyze", ...)
```

### Service Integration

```bash
# Register institutional services
weaver register -u $WEAVER_URL -n institution-a -w https://inst-a.org/wps
weaver register -u $WEAVER_URL -n institution-b -w https://inst-b.org/processes

# Access all services through single endpoint
weaver capabilities -u $WEAVER_URL -P institution-a
weaver capabilities -u $WEAVER_URL -P institution-b
```

## Error Handling

- **409 Conflict**: Provider ID already exists
- **400 Bad Request**: Invalid URL or parameters
- **503 Service Unavailable**: Cannot connect to provider URL

## Related Skills

- [provider-unregister](../provider-unregister/) - Remove provider
- [provider-list](../provider-list/) - View registered providers
- [job-execute](../job-execute/) - Run remote processes
- [process-describe](../process-describe/) - Get remote process details

## Documentation

- [Remote Providers](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Provider Types](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
