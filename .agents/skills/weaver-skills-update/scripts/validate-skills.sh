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
for skill in .agents/skills/*/SKILL.md; do
  grep -o '\.\./[^/)]*)' "$skill" 2>/dev/null | while read ref; do
    target=$(echo "$ref" | sed 's/\.\.\/\([^/]*\).*/\1/')
    if [ ! -d ".agents/skills/$target" ]; then
      echo "✗ Broken reference in $skill: $ref"
      ERRORS=$((ERRORS + 1))
    fi
  done
done

echo ""
echo "=========================="
if [ $ERRORS -eq 0 ]; then
  echo "✅ All validations passed"
  exit 0
else
  echo "❌ Found $ERRORS error(s)"
  exit 1
fi
