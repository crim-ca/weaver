---
name: process-replace
description: |
  Replace or update an existing Weaver process, producing a new versioned revision (MAJOR.MINOR.PATCH)
  without redeploying it from scratch. Accepts granular metadata/capability fields, or a full body/CWL for
  complete replacement. Use when a deployed process must be modified while keeping its previous revisions.
license: Apache-2.0
compatibility: Requires Weaver API access with process revision support (Weaver >= 4.20). Supports CWL v1.0, v1.1, v1.2.
metadata:
  author: fmigneault
---

# Replace Process

Modify an already deployed process and register the result as a new revision. Unlike `process-deploy`,
which always takes the complete application package, this skill accepts only the fields to change. The HTTP
method and the required semantic version level are resolved from the fields provided.

## When to Use

- Editing title, description, keywords, metadata or links of a deployed process
- Changing execution capabilities (`jobControlOptions`, `outputTransmission`, `visibility`)
- Publishing a new application package or full definition under a new version

Do NOT use to create a process for the first time (use [process-deploy](../process-deploy/)) or to
remove one (use [process-undeploy](../process-undeploy/)).

## Parameters

### Required

- `process_id` (string): Identifier of the process to modify.
  - `my-process` targets the latest revision.
  - `my-process:1.2.3` targets that specific revision as the base
    (equivalent to `my-process` with `?version=1.2.3` in the request).
  - Must already exist. Otherwise use `process-deploy`.

At least one of `metadata`, `body`, or `cwl` must be provided.

### Optional

- `metadata` (repeatable): Fields to update, applied according to their semantic version level.

  Accepted formats (may be combined by repeating the option):

  1. `key=value` pairs for simple fields: `-m title='New Title' -m description='Updated'`
  2. Literal JSON string: `-m '{"title": "New", "keywords": ["tag1"]}'`
  3. File path (JSON): `-m /path/to/updates.json`

  | Level | Fields                                                  | Merge behavior                                                                                   |
  | ----- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
  | PATCH | `title`, `description`                                  | Replaced by the new string                                                                       |
  | PATCH | `keywords`                                              | **Appended** to existing (an empty list resets)                                                  |
  | PATCH | `metadata`                                              | **Appended**. Entries are either Link format (`rel` + `href`) or value format (`role` + `value`) |
  | PATCH | `links`                                                 | **Appended**. Each entry needs `rel` and `href`                                                  |
  | MINOR | `jobControlOptions`, `outputTransmission`, `visibility` | **Full override** (not appended)                                                                 |

  For `metadata` link entries, `rel` is required (an IANA relation or URL).
  An additional `role` using [schema.org](https://schema.org) definitions is recommended for semantic meaning.

- `body` / `cwl`: Complete definition or application package. This is the MAJOR-level path
  (full process replacement). Same semantics as `process-deploy`.

- `version` (string): Explicit version to assign to the new revision (e.g. `2.0.0`).
  If omitted, the version is bumped automatically based on the changes (see Versioning Rules).

- `http_method` (`PUT` | `PATCH`): Overrides the automatic method selection (see below).

- `auth` (auth handler): Authentication for protected endpoints.

## Operation Selection

When `http_method` is not specified:

| Fields provided | HTTP method             | Behavior                                                                                                            |
| --------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `body` / `cwl`  | `PUT /processes/{id}`   | Full replacement. The definition is taken **exactly as provided**. Nothing is inherited from the previous revision. |
| Only `metadata` | `PATCH /processes/{id}` | Partial update. Unspecified fields are **transferred** from the referenced revision.                                |

`PATCH` is Weaver-specific. OGC API - Processes Part 2 (DRU) only defines `PUT`. Explicitly forcing a method
that does not match the provided fields (e.g. `PUT` with metadata only, which lacks the full definition a
`PUT` requires) is likely to be rejected. Prefer the automatic selection.

## Versioning Rules

Weaver uses `MAJOR.MINOR.PATCH` semantic versioning for revisions.

**Level required by change** (when several apply, the highest wins):

| Level | Change                                               | Examples                                                                                                       |
| ----- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| PATCH | Metadata not impacting execution or definition       | `title`, `description`, `keywords`, `metadata`, `links`, input/output metadata                                 |
| MINOR | Impacts *how* it can be executed, not its definition | `jobControlOptions`, `outputTransmission`, `visibility`                                                        |
| MAJOR | Impacts *what* it executes                           | Any package change, any input/output format/occurs/type change or addition/removal, replaced Docker auth token |

**Resolving the new version:**

1. **`version` omitted**: inferred from the reference revision and the required level
   (`1.2.3` + PATCH → `1.2.4`; `1.2.4` + MINOR → `1.3.0`; MAJOR → `2.0.0`).
2. **`version` provided**: it is refused unless all of the following hold:
   - It does not conflict with an existing revision of the same process.
   - It is higher than the reference revision.
   - It matches the level of the change (`2.4.0` is refused for a MINOR change, as that implies MAJOR).
   - No higher version of the same level already exists. Skipping numbers is allowed
     (`1.4.0` instead of the inferred `1.3.0`), but `1.4.0` is refused if `1.5.0` exists.
3. Prefer omitting `version` unless specific numbering matters. Auto-resolution keeps levels consistent.

**Revision lifecycle:**

- The previous revision is **not deleted**. `{id}` is repointed to the new revision,
  and the old one stays reachable as `{id}:{old_version}`.
- Without an explicit `{id}:{version}` reference, the base is the latest revision.
  After a PATCH from `test-process:1.2.3`, a later request on plain `test-process` builds on the new `1.2.4`.
- Undeploying the latest revision makes the previous one, in semantic order, the latest again.
- A process cannot be *deployed* under a `{id}:{version}` identifier (deploy always creates the first
  revision). To start at a specific version, use replace with a full `body`/`cwl` and an explicit `version`.
- To fully start over, `DELETE` all existing revisions, then deploy again.

## CLI Usage

```bash
# PATCH level: simple fields (version inferred, e.g. 1.2.3 → 1.2.4)
weaver replace -u $WEAVER_URL -p my-process:1.2.3 \
  -m title='New Process Title' -m description='Updated description'

# PATCH level: appended keywords and structured metadata from JSON
weaver replace -u $WEAVER_URL -p my-process -m '{
  "keywords": ["climate", "weather"],
  "metadata": [
    {"role": "https://schema.org/author", "rel": "author",
     "href": "https://orcid.org/0000-0000-0000-0000", "title": "Author ORCID"},
    {"role": "https://schema.org/name", "value": "John Doe"}
  ]
}'

# PATCH level: updates loaded from a file
weaver replace -u $WEAVER_URL -p my-process -m /path/to/updates.json

# MINOR level (e.g. 1.2.4 → 1.3.0), explicit version variant
weaver replace -u $WEAVER_URL -p my-process -m jobControlOptions='["async-execute"]'
weaver replace -u $WEAVER_URL -p my-process -m '{"jobControlOptions": ["async-execute"]}' --version 1.4.0

# MAJOR level: full replacement with a new package (PUT selected automatically)
weaver replace -u $WEAVER_URL -p my-process --cwl process-v2.cwl --version 2.0.0
```

## Python Usage

> Signature mirrors the CLI options and is proposed. Confirm with the client implementation.

```python
from weaver.cli import WeaverClient

client = WeaverClient(url="https://weaver.example.com")

# PATCH level
result = client.replace(
    process_id="my-process:1.2.3",
    metadata={"title": "New Process Title", "keywords": ["climate"]},
)

# MINOR level with explicit version
result = client.replace(
    process_id="my-process",
    metadata={"jobControlOptions": ["async-execute"]},
    version="1.4.0",
)

# MAJOR level (PUT)
result = client.replace(process_id="my-process", cwl="process-v2.cwl", version="2.0.0")
```

## API Requests

```bash
# PATCH, PATCH level (version inferred → 1.2.4)
curl -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"description": "new description"}' \
  "${WEAVER_URL}/processes/my-process:1.2.3"

# PATCH, MINOR level with explicit version
curl -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"jobControlOptions": ["async-execute"], "version": "1.4.0"}' \
  "${WEAVER_URL}/processes/my-process"

# PUT, MAJOR level (full definition required)
curl -X PUT \
  -H "Content-Type: application/json" \
  -d '{
  "processDescription": {"process": {"id": "my-process", "version": "2.0.0"}},
  "executionUnit": [{"href": "https://example.com/process-v2.cwl"}]
}' \
  "${WEAVER_URL}/processes/my-process"
```

## Returns

The response describes the new revision. Replacement may respond with either `200 OK` or `201 Created`,
selected dynamically by whether the operation resulted in an in-place replacement or a distinct process
instance (Weaver >= 6.11.0). Treat both as success and read the resolved `version` from the body rather than
assuming it.

## Error Handling

- `400 Bad Request`: Invalid definition, or `version` inconsistent with the required update level.
- `401 Unauthorized`: Authentication required.
- `404 Not Found`: Process (or referenced `{id}:{version}`) does not exist.
- `409 Conflict`: The requested `version` conflicts with an existing revision.

Common causes of a rejected version: not higher than the base revision, level too high or too low for the
change (e.g. MAJOR bump for metadata-only edits), or a higher version of the same level already exists.

## Related Skills

- [process-deploy](../process-deploy/) - Create the first revision of a process
- [process-describe](../process-describe/) - Inspect a process, including specific revisions
- [process-undeploy](../process-undeploy/) - Remove a process or its latest revision
- [job-execute](../job-execute/) - Run a process (latest revision unless a version is specified)

## Documentation

- [Modify an Existing Process (Update, Replace, Undeploy)](https://pavics-weaver.readthedocs.io/en/latest/processes.html#modify-an-existing-process-update-replace-undeploy)
- [CWL Application Packages](https://pavics-weaver.readthedocs.io/en/latest/package.html)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
- [OGC API - Processes Part 2: Deploy, Replace, Undeploy](https://github.com/opengeospatial/ogcapi-processes/tree/master/extensions/deploy_replace_undeploy)
