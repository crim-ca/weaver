#!/bin/bash
# Validate Agent Skills YAML frontmatter and cross-references

echo "Validating Agent Skills..."
echo "=========================="

ERRORS=0

# Validate YAML frontmatter
echo ""
echo "Checking YAML frontmatter..."
for skill in .agents/skills/*/SKILL.md; do
  python3 -c "
import yaml
import sys
try:
    with open('$skill') as f:
        content = f.read()
        parts = content.split('---')
        if len(parts) >= 3:
            yaml.safe_load(parts[1])
            print('✓ $skill')
        else:
            print('✗ $skill: Invalid frontmatter')
            sys.exit(1)
except Exception as e:
    print('✗ $skill: ' + str(e))
    sys.exit(1)
" || ERRORS=$((ERRORS + 1))
done

# Check for broken cross-references
echo ""
echo "Checking cross-references..."
broken_refs=()
for skill in .agents/skills/*/SKILL.md; do
  while IFS= read -r ref; do
    target=$(echo "$ref" | sed 's/\.\.\/\([^/]*\).*/\1/')
    if [ ! -d ".agents/skills/$target" ]; then
      broken_refs+=("✗ Broken reference in $skill: $ref")
    fi
  done < <(grep -o '\.\./[^/)]*)' "$skill" 2>/dev/null)
done

ERRORS=${#broken_refs[@]}
if [ "$ERRORS" -gt 0 ]; then
  for ref in "${broken_refs[@]}"; do
    echo "$ref"
  done
fi

echo ""
echo "=========================="
if [ "$ERRORS" -eq 0 ]; then
  echo "✅ All validations passed"
  exit 0
else
  echo "❌ Found $ERRORS error(s)"
  exit 1
fi
