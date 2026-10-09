---
name: update-provenance-examples
description: |
  Regenerate the W3C PROV job provenance example files under weaver/wps_restapi/examples
  (job_prov.json, job_prov.jsonld, job_prov.xml, job_prov.ttl, job_prov.nt, job_prov.provn,
  job_prov_info.txt, job_prov_run.txt, job_prov_who.txt). Use after changes to weaver/provenance.py,
  cwltool/cwlprov integration, or the /jobs/{jobId}/prov endpoints that alter the PROV metadata
  structure or content, to keep OpenAPI documentation examples accurate and in sync.
license: Apache-2.0
compatibility: Requires a running Weaver instance with weaver.cwl_prov=true, a completed Job with
  provenance metadata, and curl/jq (via the provided script) or the weaver CLI.
metadata:
  category: setup-operations
  version: "1.1.0"
  keywords:
    - provenance
    - prov
    - examples
    - cwlprov
    - w3c-prov
    - openapi
    - documentation
    - echo
  author: dhdqa
  contributors:
    - fmigneault
---

# Update Provenance Examples

Regenerate the W3C PROV example files referenced by the OpenAPI documentation for the
`/jobs/{jobId}/prov` family of endpoints.

## When to Use

- After modifying `weaver/provenance.py` or the PROV generation logic
- After upgrading `cwltool`/`cwlprov` dependencies that change PROV document structure
- After adding/changing `weaver/wps_restapi/jobs/prov.py` response content
- When example files under `weaver/wps_restapi/examples/job_prov*` no longer reflect real output
- Before a release that touches provenance tracking (`weaver.cwl_prov`)

## Affected Files

All located in `weaver/wps_restapi/examples/`, loaded automatically at import time by
`SCHEMA_EXAMPLE_DIR`/`EXAMPLES` in `weaver/wps_restapi/swagger_definitions.py` and referenced by
`get_job_prov_responses` / `get_job_prov_metadata_responses`:

| File | Content | PROV format |
| - | - | - |
| `job_prov.json` | Main PROV document | `PROV-JSON` |
| `job_prov.jsonld` | Main PROV document | `PROV-JSONLD` |
| `job_prov.xml` | Main PROV document | `PROV-XML` |
| `job_prov.ttl` | Main PROV document | `PROV-TURTLE` |
| `job_prov.nt` | Main PROV document | `PROV-NT` |
| `job_prov.provn` | Main PROV document | `PROV-N` |
| `job_prov_info.txt` | `/prov/info` research object summary | plain text |
| `job_prov_run.txt` | `/prov/run` execution timeline | plain text |
| `job_prov_who.txt` | `/prov/who` agents summary | plain text |

## Prerequisites

1. A running Weaver instance with `weaver.cwl_prov = true` (default) in its configuration.
2. A `Job` executed to completion (`succeeded`) so that provenance metadata was collected during the
   run. The builtin `EchoProcess` (`weaver.processes.builtin.echo_process`) is the recommended
   candidate: it requires no deployment, and its wide range of input/output types produces
   representative `entity`/`activity`/`agent` relationships in the generated PROV documents.
3. `curl` and `jq` (used by the provided script), or alternatively the `weaver` CLI.

## Steps

1. Submit an execution of the builtin `EchoProcess` using the example request body
   [`echo_body.json`](../../../weaver/wps_restapi/examples/echo_body.json) (see
   [Generate a Job](#generate-a-job) below), and wait for it to reach `succeeded` status (see
   [job-monitor](../job-monitor/SKILL.md)).
2. From the `weaver/wps_restapi/examples/` directory, run the
   [`job_prov_examples.sh`](scripts/job_prov_examples.sh) script with the resulting `Job` ID to fetch
   every PROV representation and metadata view, overwriting the `job_prov*` example files in place
   (see [Regenerate the Examples](#regenerate-the-examples) below).
3. Review the generated files and replace any volatile, environment-specific values that are not
   already normalized by the script (random-looking UUIDs, `arcp://uuid,...` identifiers, and
   timestamps are expected and fine to keep as generated, but avoid leaking real internal
   hostnames/tokens not already covered by the script's `fix_urls` substitutions).
4. Confirm the files still parse correctly and the API documentation renders as expected.

## Generate a Job

```bash
export WEAVER_URL=http://localhost:4001

# Submit an execution of the builtin EchoProcess using the example request body.
JOB_URL=$(curl -s -i -X POST \
  -H "Content-Type: application/json" \
  -H "Prefer: respond-async" \
  -d @weaver/wps_restapi/examples/echo_body.json \
  "${WEAVER_URL}/processes/EchoProcess/execution" | grep -i "^Location:" | awk '{print $2}' | tr -d '\r')
JOB_ID=$(basename "$JOB_URL")

# Wait for the job to complete (see job-monitor skill for a more robust polling loop).
weaver monitor -u $WEAVER_URL -j $JOB_ID
```

## Regenerate the Examples

The [`job_prov_examples.sh`](scripts/job_prov_examples.sh) script fetches the main PROV document in
every supported format plus the three plain-text metadata views, normalizes the instance hostname, and
writes each result to the corresponding `job_prov*` file in the current directory.

```bash
cd weaver/wps_restapi/examples
sh /path/to/.github/skills/update-provenance-examples/scripts/job_prov_examples.sh "$JOB_ID"
```

> **Note**: The script targets `http://localhost:4001` and rewrites hostnames to
> `https://hirondelle.crim.ca/weaver` / `hirondelle.crim.ca` to match the existing examples. Adjust the
> `REST` variable and `fix_urls` substitutions inside the script if generating examples against a
> different instance.

### Manual Alternative (CLI/curl)

If the script cannot be used (e.g. no `jq` available, or only specific formats need refreshing),
equivalent individual requests can be issued with the `weaver` CLI:

```bash
weaver provenance -u $WEAVER_URL -j $JOB_ID -pF PROV-JSON   -F JSON --stdout > \
  weaver/wps_restapi/examples/job_prov.json
weaver provenance -u $WEAVER_URL -j $JOB_ID -pF PROV-JSONLD -F JSON --stdout > \
  weaver/wps_restapi/examples/job_prov.jsonld
weaver provenance -u $WEAVER_URL -j $JOB_ID -pF PROV-XML    -F XML  --stdout > \
  weaver/wps_restapi/examples/job_prov.xml
weaver provenance -u $WEAVER_URL -j $JOB_ID -pF PROV-TURTLE -F TEXT --stdout > \
  weaver/wps_restapi/examples/job_prov.ttl
weaver provenance -u $WEAVER_URL -j $JOB_ID -pF PROV-NT     -F TEXT --stdout > \
  weaver/wps_restapi/examples/job_prov.nt
weaver provenance -u $WEAVER_URL -j $JOB_ID -pF PROV-N      -F TEXT --stdout > \
  weaver/wps_restapi/examples/job_prov.provn
weaver provenance -u $WEAVER_URL -j $JOB_ID -pT info -F TEXT --stdout > \
  weaver/wps_restapi/examples/job_prov_info.txt
weaver provenance -u $WEAVER_URL -j $JOB_ID -pT run  -F TEXT --stdout > \
  weaver/wps_restapi/examples/job_prov_run.txt
weaver provenance -u $WEAVER_URL -j $JOB_ID -pT who  -F TEXT --stdout > \
  weaver/wps_restapi/examples/job_prov_who.txt
```

> **Note**: Exact media-type strings and relevant query parameter alternatives (`?f=json`, `?f=jsonld`,
> etc.) are defined by `ProvenanceFormat`/`ProvenancePathType` in `weaver/provenance.py`. Verify them
> against that module if a mismatch occurs, since media-types can evolve between versions.

## Validation

1. Reload the module and confirm the examples still load without error:

   ```bash
   python3 -c "from weaver.wps_restapi.swagger_definitions import EXAMPLES; \
     print(sorted(k for k in EXAMPLES if k.startswith('job_prov')))"
   ```

2. Run the provenance-related functional tests to confirm nothing else broke:

   ```bash
   pytest tests/functional/test_job_provenance.py -q
   ```

3. Validate formatting with the repository's Markdown/JSON lint targets if any surrounding
   documentation was also edited:

   ```bash
   make check-md-only
   ```

## Limitations

- Generated content includes non-deterministic identifiers (UUIDs, timestamps, hostnames). Re-running
  the generation steps will always produce a diff even without functional changes; only commit when the
  *structure* of the PROV metadata actually changed.
- Requires `weaver.cwl_prov=true` and a successfully completed `Job`; jobs executed while provenance was
  disabled, or that failed/are still running, will not return PROV metadata (see
  [job-provenance](../job-provenance/SKILL.md) limitations).
- The `job_prov_examples.sh` script assumes a POSIX shell (`sh`), and that `curl`/`jq` are installed and
  available on `PATH`.

## Related Skills

- [job-provenance](../job-provenance/SKILL.md) - Retrieve provenance metadata for a specific job
- [job-execute](../job-execute/SKILL.md) - Run a process/workflow to produce a job with provenance
- [job-monitor](../job-monitor/SKILL.md) - Wait for the job to reach a completed status
- [weaver-ci-validate](../weaver-ci-validate/SKILL.md) - Run lint/test targets after updating examples

## References

- [Provenance Tracking](https://pavics-weaver.readthedocs.io/en/latest/processes.html)
- [Configuration: weaver.cwl_prov](https://pavics-weaver.readthedocs.io/en/latest/configuration.html#weaver-cwl-prov)
- [W3C PROV Overview](https://www.w3.org/TR/prov-overview/)
- [CLI Reference](https://pavics-weaver.readthedocs.io/en/latest/cli.html)
