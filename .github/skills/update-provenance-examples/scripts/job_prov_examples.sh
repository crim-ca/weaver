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

JOBID=${1??Usage: $0 JOBID [WEAVER_URL]}
WEAVER_URL=${2:-http://localhost:4001}
REST=$WEAVER_URL/jobs/$JOBID

curl $REST/prov/who | fix_urls  > job_prov_who.txt
curl $REST/prov/info | fix_urls  > job_prov_info.txt
curl $REST/prov/run | fix_urls  > job_prov_run.txt
curl $REST/prov | fix_urls | jq > job_prov.json
curl $REST/prov?f=PROV-JSONLD | fix_urls | jq > job_prov.jsonld
curl $REST/prov?f=PROV-TURTLE | fix_urls > job_prov.ttl
curl $REST/prov?f=PROV-XML | fix_urls > job_prov.xml
curl $REST/prov?f=PROV-NT | fix_urls > job_prov.nt
curl $REST/prov?f=PROV-N | fix_urls > job_prov.provn

