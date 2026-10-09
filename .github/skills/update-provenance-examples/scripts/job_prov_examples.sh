#!/bin/sh
# Fetch every W3C PROV representation and metadata view of a completed Weaver Job, and save them as the
# example files consumed by weaver/wps_restapi/swagger_definitions.py (EXAMPLES / SCHEMA_EXAMPLE_DIR).
#
# Usage: job_prov_examples.sh JOBID
#
# Run this script from the "weaver/wps_restapi/examples/" directory so that the generated
# "job_prov*" files land next to the other examples. Requires "curl" and "jq".

fix_urls() {
    sed -e s,$WEAVER_URL,https://hirondelle.crim.ca/weaver,g \
        -e s,localhost,hirondelle.crim.ca,g
}

# Fetch $1 (URL) into $2 (output file), optionally pretty-printing with "jq" when $3 is "jq".
# Aborts the whole script (rather than silently producing an empty/truncated example file) if the
# "curl" request fails (network error, or a non-2xx response because of "-f") or if "jq" cannot parse
# the result.
fetch() {
    url=$1
    out=$2
    jqfmt=$3
    tmp=$(mktemp) || { echo "ERROR: could not create a temporary file." >&2; exit 1; }
    if ! curl -sS -f "$url" -o "$tmp"; then
        echo "ERROR: curl request failed for [$url]" >&2
        rm -f "$tmp"
        exit 1
    fi
    if [ "$jqfmt" = "jq" ]; then
        if ! fix_urls < "$tmp" | jq . > "$out"; then
            echo "ERROR: jq formatting failed for [$url]" >&2
            rm -f "$tmp"
            exit 1
        fi
    else
        fix_urls < "$tmp" > "$out"
    fi
    rm -f "$tmp"
}

JOBID=${1??Usage: $0 JOBID [WEAVER_URL]}
WEAVER_URL=${2:-http://localhost:4001}
REST=$WEAVER_URL/jobs/$JOBID

fetch "$REST/prov/who" job_prov_who.txt
fetch "$REST/prov/info" job_prov_info.txt
fetch "$REST/prov/run" job_prov_run.txt
fetch "$REST/prov" job_prov.json jq
fetch "$REST/prov?f=PROV-JSONLD" job_prov.jsonld jq
fetch "$REST/prov?f=PROV-TURTLE" job_prov.ttl
fetch "$REST/prov?f=PROV-XML" job_prov.xml
fetch "$REST/prov?f=PROV-NT" job_prov.nt
fetch "$REST/prov?f=PROV-N" job_prov.provn

