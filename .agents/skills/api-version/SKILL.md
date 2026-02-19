---
name: api-version
description: Retrieve detailed version information including Weaver version, database schema version, and deployed commit hash. Use for version verification, troubleshooting, and ensuring compatibility.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  category: system-information
  version: "1.0.0"
  api_endpoint: GET /versions
  cli_command: weaver version
  author: CRIM
allowed-tools: http_request
---

# Get Version

Retrieve detailed version information for the Weaver instance.

## When to Use

- Verifying Weaver version before deployment
- Troubleshooting compatibility issues
- Checking for available updates
- Bug reporting and support requests
- Ensuring feature availability
- Documenting system configuration

## Parameters

None required.

## CLI Usage

```bash
# Get version information
weaver version -u $WEAVER_URL

# Check specific version
weaver version -u https://weaver.example.com
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# Get version
version = client.version()

print(f"Version: {version.body['version']}")
print(f"Database: {version.body['db_version']}")
print(f"Commit: {version.body.get('commit', 'N/A')}")
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/versions"
```

## Returns

```json
{
  "versions": [
    {
      "version": "6.8.3",
      "type": "api",
      "db_version": "3.31.0",
      "commit": "abc123def456"
    }
  ]
}
```

**Note**: Response may include additional fields. See [API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Version Information

### version
Weaver application version (e.g., "6.8.3")
- Major version: Breaking changes
- Minor version: New features
- Patch version: Bug fixes

### db_version
Database schema version
- Used for migration compatibility
- Important for upgrades

### commit
Git commit hash of deployed version
- Useful for exact version identification
- Helps with debugging and support

## Use Cases

### Version Check
```bash
# Check if running latest version
CURRENT=$(weaver version -u $WEAVER_URL -f json | jq -r '.versions[0].version')
echo "Running Weaver v$CURRENT"

# Compare with required version
if [[ "$CURRENT" < "6.0.0" ]]; then
    echo "Version too old, upgrade required"
fi
```

### Compatibility Verification
```python
# Check if feature is available
version_info = client.version()
version = version_info.body["versions"][0]["version"]

major, minor, patch = map(int, version.split('.'))

# Check for provenance feature (added in 4.0.0)
if major >= 4:
    print("Provenance tracking available")
else:
    print("Upgrade to 4.0.0+ for provenance")
```

### Bug Reporting
```bash
# Collect version info for bug report
echo "Weaver Version Information:"
weaver version -u $WEAVER_URL
weaver info -u $WEAVER_URL | jq '.configuration'
```

## Version History

Major versions and key features:
- **6.x**: Enhanced OGC API - Processes Part 4, improved quotation
- **5.x**: Workflow improvements, vault enhancements
- **4.x**: W3C PROV provenance tracking
- **3.x**: OGC API - Processes Part 2 (DRU)
- **2.x**: Enhanced job management
- **1.x**: Initial OGC API - Processes implementation

## Related Skills

- [api-info](../api-info/) - Get general API information
- [api-conformance](../api-conformance/) - Check OGC compliance
- [process-describe](../process-describe/) - Check process availability

## Documentation

- [Version Information](https://pavics-weaver.readthedocs.io/en/latest/api.html)
- [Release Notes](https://pavics-weaver.readthedocs.io/en/latest/changes.html)
- [Installation](https://pavics-weaver.readthedocs.io/en/latest/installation.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
