#!/bin/sh
# Submit an execution of the builtin EchoProcess using the example request body
# (weaver/wps_restapi/examples/echo_body.json), producing a completed Job suitable as input to
# job_prov_examples.sh.
#
# Usage: submit_echo_job.sh [WEAVER_URL] [ECHO_BODY]
#
# Prints the resulting JOBID to stdout once the submission is accepted (HTTP 201); the job still
# needs to be monitored/waited on separately (see the "job-monitor" skill, or "weaver monitor") before
# its provenance can be retrieved.

WEAVER_URL=${1:-http://localhost:4001}
ECHO_BODY=${2:-weaver/wps_restapi/examples/echo_body.json}

JOB_URL=$(curl -s -i -X POST \
    -H "Content-Type: application/json" \
    -H "Prefer: respond-async" \
    -d "@$ECHO_BODY" \
    "$WEAVER_URL/processes/EchoProcess/execution" \
    | grep -i "^Location:" | awk '{print $2}' | tr -d '\r')

if [ -z "$JOB_URL" ]; then
    echo "Failed to submit EchoProcess execution: no Location header returned." >&2
    exit 1
fi

basename "$JOB_URL"
