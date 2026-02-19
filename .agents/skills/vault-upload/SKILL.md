---
name: vault-upload
description: Securely store files or credentials in Weaver's vault for use in process execution. The vault provides encrypted storage for sensitive data like authentication tokens, private files, or API keys. Use when you need to handle sensitive data securely.
license: Apache-2.0
compatibility: Requires Weaver API access with vault feature enabled.
metadata:
  category: vault
  version: "1.0.0"
  api_endpoint: POST /vault/{file_id}
  cli_command: weaver upload
  author: CRIM
allowed-tools: file_read http_request
---

# Upload to Vault

Securely store files or credentials in Weaver's encrypted vault.

## When to Use

- Storing API keys or authentication tokens
- Uploading private input files
- Managing sensitive credentials
- Sharing secrets between jobs securely

## Parameters

### Required
- **file_id** or **vault_token** (string): Unique vault identifier
- **file_path** (path): Local file to upload

### Optional
- **encrypted** (boolean): Whether to encrypt the file

## CLI Usage

```bash
# Upload credentials
weaver upload -u $WEAVER_URL -vT my-credentials -f api-key.txt

# Upload private data file
weaver upload -u $WEAVER_URL -vT private-data -f sensitive.nc
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")
result = client.upload(
    vault_token="my-credentials",
    file_path="api-key.txt"
)

print(f"Uploaded to vault: vault://{result.body['vault_id']}")
```

## Using Vault References in Execution

Once uploaded, reference vault content in job inputs:

```json
{
  "inputs": {
    "auth_token": {
      "href": "vault://my-credentials"
    },
    "private_file": {
      "href": "vault://private-data"
    }
  }
}
```

## Returns

- **vault_id**: Vault token for referencing
- **status**: Upload confirmation
- **reference**: `vault://` URL to use in inputs

## Security Features

- End-to-end encryption
- Access control per vault item
- Automatic cleanup after job completion (optional)
- Audit logging

## Related Skills

- [job-execute](../job-execute/) - Use vault references in execution

## Documentation

- [Vault Feature](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html#upload)
