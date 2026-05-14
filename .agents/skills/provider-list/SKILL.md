---
name: provider-list
description: |
  List all registered remote providers including WPS and OGC API - Processes services. Shows
  provider URLs, types, and availability status. Use to discover available external services
  integrated with Weaver.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
---

# List Providers

List all registered remote providers and their capabilities.

## When to Use

- Discovering available external services
- Checking provider connectivity
- Auditing registered integrations
- Finding providers for specific capabilities
- Troubleshooting federation issues

## Parameters

### Optional

- **detail** (boolean): Include detailed provider information
- **check** (boolean): Verify provider connectivity

## CLI Usage

```bash
# List all providers
weaver capabilities -u $WEAVER_URL --providers

# List with details
weaver capabilities -u $WEAVER_URL --providers --detail

# Check specific provider's processes
weaver capabilities -u $WEAVER_URL -P my-provider
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# List providers
result = client.capabilities(providers=True)

for provider in result.body.get("providers", []):
    print(f"{provider['id']}: {provider['url']}")
    print(f"  Type: {provider['type']}")
    print(f"  Public: {provider['public']}")

# Get processes from specific provider
processes = client.capabilities(provider="my-provider")
for process in processes.body.get("processes", []):
    print(f"  - {process['id']}: {process.get('title', '')}")
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/providers"
```

## Returns

```json
{
  "providers": [
    {
      "id": "remote-wps",
      "url": "https://remote.example.com/wps",
      "type": "wps",
      "public": true,
      "description": "Remote WPS processing service"
    },
    {
      "id": "ogc-api-provider",
      "url": "https://ogc.example.com/processes",
      "type": "ogcapi",
      "public": true,
      "description": "OGC API - Processes instance"
    }
  ],
  "total": 2
}
```

**Note**: Response may include additional fields. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Provider Information

Each provider includes:

- **id**: Unique provider identifier
- **url**: Service endpoint URL
- **type**: Service type (wps, ogcapi, esgf)
- **public**: Public accessibility flag
- **description**: Provider description
- **status**: Connectivity status (if checked)

## Provider Types

### WPS

- Web Processing Service 1.0/2.0
- XML-based protocols
- GetCapabilities, DescribeProcess, Execute

### OGC API - Processes

- RESTful JSON API
- Modern OGC standard
- /processes, /jobs endpoints

### ESGF

- Earth System Grid Federation
- Climate data processing
- Specialized scientific workflows

## Use Cases

### Service Discovery

```bash
# Find all available providers
weaver capabilities -u $WEAVER_URL --providers

# Check what processes each provider offers
for provider in $(weaver capabilities -u $WEAVER_URL --providers -f json | jq -r '.providers[].id'); do
    echo "Provider: $provider"
    weaver capabilities -u $WEAVER_URL -P $provider
done
```

### Provider Health Check

```python
# Check all providers
providers = client.capabilities(providers=True)

for provider in providers.body.get("providers", []):
    try:
        processes = client.capabilities(provider=provider["id"])
        print(f"✓ {provider['id']}: {len(processes.body.get('processes', []))} processes")
    except Exception as e:
        print(f"✗ {provider['id']}: Unavailable - {e}")
```

### Federation Management

```python
# List providers by type
providers = client.capabilities(providers=True)

wps_providers = [p for p in providers.body["providers"] if p["type"] == "wps"]
ogc_providers = [p for p in providers.body["providers"] if p["type"] == "ogcapi"]

print(f"WPS providers: {len(wps_providers)}")
print(f"OGC API providers: {len(ogc_providers)}")
```

## Related Skills

- [provider-register](../provider-register/) - Add new provider
- [provider-unregister](../provider-unregister/) - Remove provider
- [process-describe](../process-describe/) - Get provider process details
- [job-execute](../job-execute/) - Run provider processes

## Documentation

- [Remote Providers](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Provider Types](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
