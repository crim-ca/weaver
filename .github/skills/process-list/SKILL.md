---
name: process-list
description: |
  List all available processes with optional filtering by visibility or provider. Retrieve process
  summaries for discovery. Use when you need to find available processing capabilities or explore
  what Weaver can do.
license: Apache-2.0
compatibility: Requires Weaver API access.
metadata:
  author: fmigneault
---

# List Processes

List all available processes with optional filtering and pagination.

## When to Use

- Discovering available processes
- Finding processes by keyword or category
- Checking deployed processes
- Exploring remote provider capabilities

## Parameters

### Optional

- `provider` (string): Filter by provider ID
- `visibility` (string): Filter by visibility ("public", "private")
- `limit` (integer): Maximum number of results
- `page` (integer): Pagination offset
- `sort` (string): Sort order for results
- `detail` (boolean): Include detailed descriptions

## CLI Usage

```bash
# List all processes
weaver capabilities -u $WEAVER_URL

# List from specific provider
weaver capabilities -u $WEAVER_URL -P my-provider

# List with details
weaver capabilities -u $WEAVER_URL --detail
```

## API Search

`GET /processes` supports these additional parameters for locally registered public processes:

- **keywords** (string): Whole-keyword, case-insensitive matches. Use `,` for AND and `|` for OR within a group.
  Prefix a keyword with `!` or `~` for NOT.
- **title**, **description** (string): Case-insensitive literal substring searches.
- **q**, **query** (string): Partial terms searched across title, description and keywords, with `,` for OR,
  `+` for AND and `-` for NOT. Signs are operators only at the beginning or after whitespace or commas.
  Other signs are literal: `data-` matches `data-analysis` and `data-science`.
  Ordinary spaces join an ordered phrase and match one or more whitespace characters.
  Use `+-data` for a leading literal minus. Double quotes preserve literal punctuation.
- **version** (string): Exact version or inclusive `lower/upper` interval. Use `..` for an open bound.
  Add **revisions=true** to search older revisions.
- **sortby** (string): Signed, comma-separated sorting fields, such as `+id,-version`.
- **sort** (string): Deprecated alias of **sortby**. Cannot be combined with it.
- **datetime** (string): Instant or interval matched against the process `created` time.
- **type** (string): Comma-separated process types (case-insensitive) or Records resource type URIs.
- **license** (string): Href or title of a `license` link or metadata.
- **filter** (string): CQL2 expression, with optional **filter-lang**.

Different filters combine with AND and apply before pagination. They cannot be combined with `providers=true`.
Empty terms are invalid. URL-encode values, particularly `+` as `%2B`.
`GET /queryables/processes` describes the supported listing parameters as JSON Schema.

```bash
curl --get "${WEAVER_URL}/processes" \
  --data-urlencode "keywords=climate,netcdf|grib" \
  --data-urlencode "query=+climate +netcdf -grib,subset" \
  --data-urlencode "limit=10"
```

## Python Usage

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# List all
result = client.capabilities()

for process in result.body.get("processes", []):
    print(f"{process['id']}: {process.get('title', process['id'])}")
```

## Returns

```json
{
  "processes": [
    {
      "id": "process-1",
      "title": "Process 1",
      "description": "Brief description",
      "version": "1.0.0"
    }
  ],
  "total": 10,
  "limit": 10,
  "offset": 0
}
```

**Note**: Response may include additional fields. See
[API documentation](https://pavics-weaver.readthedocs.io/en/latest/api.html) for complete response schemas.

## Related Skills

- [process-describe](../process-describe/) - Get process details
- [process-deploy](../process-deploy/) - Add new process
- [job-execute](../job-execute/) - Run a process as a job with inputs

## Documentation

- [Process Listing](https://pavics-weaver.readthedocs.io/en/latest/processes.html#listing)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html#capabilities)
