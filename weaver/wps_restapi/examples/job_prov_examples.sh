#!/bin/sh

fix_urls() {
    sed -e s,http://localhost:4001,https://hirondelle.crim.ca/weaver,g \
        -e s,localhost,hirondelle.crim.ca,g
}

JOBID=${1??Usage: $0 JOBID}
REST=http://localhost:4001/jobs/$JOBID
curl $REST/prov/who | fix_urls  > job_prov_who.txt
curl $REST/prov/info | fix_urls  > job_prov_info.txt
curl $REST/prov/run | fix_urls  > job_prov_run.txt
curl $REST/prov | fix_urls | jq > job_prov.json
curl $REST/prov?f=PROV-JSONLD | fix_urls | jq > job_prov.jsonld
curl $REST/prov?f=PROV-TURTLE | fix_urls > job_prov.ttl
curl $REST/prov?f=PROV-XML | fix_urls > job_prov.xml
curl $REST/prov?f=PROV-NT | fix_urls > job_prov.nt
curl $REST/prov?f=PROV-N | fix_urls > job_prov.provn

