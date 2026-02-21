#!/bin/bash
# Detect files requiring skill updates

SINCE_DATE=${1:-"1 month ago"}

echo "Changes since: $SINCE_DATE"
echo "================================"

# CLI changes
CLI_CHANGES=$(git log --since="$SINCE_DATE" --name-only --pretty=format: weaver/cli.py | sort -u | wc -l)
if [ $CLI_CHANGES -gt 0 ]; then
  echo "⚠️  CLI changes detected: $CLI_CHANGES"
  echo "   → Review all job-*, process-*, provider-* skills"
fi

# Makefile changes
MK_CHANGES=$(git log --since="$SINCE_DATE" --name-only --pretty=format: Makefile | sort -u | wc -l)
if [ $MK_CHANGES -gt 0 ]; then
  echo "⚠️  Makefile changes detected: $MK_CHANGES"
  echo "   → Update weaver-install skill"
fi

# API changes
API_CHANGES=$(git log --since="$SINCE_DATE" --name-only --pretty=format: weaver/wps_restapi/ | sort -u | wc -l)
if [ $API_CHANGES -gt 0 ]; then
  echo "⚠️  API changes detected: $API_CHANGES"
  echo "   → Review affected endpoint skills"
fi

# Documentation changes
DOC_CHANGES=$(git log --since="$SINCE_DATE" --name-only --pretty=format: docs/source/ | sort -u | wc -l)
if [ $DOC_CHANGES -gt 0 ]; then
  echo "⚠️  Documentation changes detected: $DOC_CHANGES"
  echo "   → Verify documentation links in skills"
fi

echo "================================"
echo "See .agents/skills/weaver-skills-update/SKILL.md for update procedures"
