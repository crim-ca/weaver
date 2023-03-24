#!/usr/bin/env bash

# transform long options to short options
for arg in "$@"; do
  shift
  case "$arg" in
    "--config") set -- "$@" "-c" ;;
    "--json") set -- "$@" "-j" ;;
    *) set -- "$@" "$arg"
  esac
done

# process short options
while getopts "c:dj" OPTION
do
  case "${OPTION}" in
    "c") CONFIG=${OPTARG} ;;
    "j") JSON=true ;;
    *) ;;
  esac
done
shift "$((OPTIND-1))"

if [ ! -f "${CONFIG}" ]; then
  echo "Invalid config not found: [${CONFIG}]"
  exit 1
fi

# extract all values and add them together with their respective weights
TOTAL=$( \
  cat "${CONFIG}" \
   |  yq '.inputs.* | {"value": (.value,.size), "weight": .weight} | select( .value != null ) | .value * .weight'
)
TOTAL=$(echo "${TOTAL:-0.0} * 1.0" | bc)  # ensure floating point value

if [ "${JSON}" = "true" ]; then
  echo "{\"total\": ${TOTAL}}"
else
  echo "total: ${TOTAL}"
fi
