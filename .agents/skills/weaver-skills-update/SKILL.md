---
name: weaver-skills-update
description: Maintain and update Agent Skills documentation when Weaver codebase changes. Detect code modifications in weaver/cli.py, Makefile, docs/, and configuration files, then systematically update relevant skills to keep documentation synchronized. Use when contributing code changes or maintaining skills framework.
license: Apache-2.0
compatibility: Requires Python 3.10+, git, access to weaver repository.
metadata:
  category: setup-operations
  version: "1.0.0"
  author: CRIM
allowed-tools: run_command file_read file_write grep_search
---

# Update Weaver Agent Skills

Maintain and update Agent Skills documentation when Weaver codebase changes.

## When to Use

- After modifying Weaver CLI commands (`weaver/cli.py`)
- After updating Makefile targets
- After changing configuration options
- After updating API endpoints in `weaver/wps_restapi/`
- After modifying process operations
- When documentation falls out of sync with code
- During major version releases

## Overview

Agent Skills must stay synchronized with the Weaver codebase. This skill provides systematic procedures to detect changes and update relevant skills.

## Change Detection Strategy

### 1. Identify Changed Files

```bash
# Check git status for modified files
git status --porcelain

# Compare with upstream
git diff origin/master --name-only

# Check specific areas
git diff origin/master -- weaver/cli.py
git diff origin/master -- Makefile
git diff origin/master -- docs/source/
git diff origin/master -- weaver/wps_restapi/
```

### 2. Analyze Impact Areas

Based on changed files, determine affected skill categories:

| Changed File              | Affected Skills           | Update Priority |
|---------------------------|---------------------------|-----------------|
| `weaver/cli.py`           | All CLI-referenced skills | **High**        |
| `weaver/wps_restapi/*.py` | API, job, process skills  | **Medium**      |
| `docs/source/*.rst`       | Documentation links       | **Medium**      |
| `config/*.example`        | Configuration examples    | **Medium**      |
| `weaver/processes/*.py`   | process-* skills          | **Medium**      |
| `Makefile`                | weaver-install            | **Medium**      |
| `CHANGES.rst`             | All depending on change   | **Low**         |

## Update Procedures

### Procedure 1: CLI Command Changes

**When**: `weaver/cli.py` is modified

**Steps**:

#### 1. Extract CLI methods
```bash
# List all CLI commands
grep -E "^def (.*)\(.*\):" weaver/cli.py | grep -v "^def _"

# Check for new commands
git diff origin/master weaver/cli.py | grep "^+.*def " | grep -v "^+.*def _"

# Check for modified command signatures
git diff origin/master weaver/cli.py | grep -A5 "def "
```

#### 2. Identify affected skills
```bash
# Map CLI commands to skills
# deploy        → process-deploy
# execute       → job-execute
# status        → job-status
# logs          → job-logs
# results       → job-results
# etc.
```

#### 3. Update skill documentation

For each affected skill:

```bash
# a. Update CLI Usage section
# - Review command signature changes
# - Update parameter descriptions
# - Update example commands

# b. Update Python Usage section
# - Check WeaverClient method changes
# - Update parameter names
# - Update return value handling

# c. Verify examples still work
weaver <command> --help
# Test command with example from skill
```

#### 4. Check for new CLI commands
```bash
# If new command found, create new skill:
# - Determine category (job-*, process-*, provider-*, etc.)
# - Create skill directory and SKILL.md
# - Follow existing skill template
# - Add cross-references
# - Update .agents/README.md
```

### Procedure 2: Makefile Target Changes

**When**: `Makefile` is modified

**Steps**:

#### 1. Detect changed targets
```bash
# List all make targets
grep -E "^[a-z-]+:" Makefile | cut -d: -f1

# Check for new or modified targets
git diff origin/master Makefile | grep "^+.*:" | grep -v "^+##"
```

#### 2. Update weaver-install skill
```bash
# Update sections:
# - "Install with Makefile Targets"
# - "Makefile Reference"
# - Installation procedure examples

# Verify each target description:
make help | grep "install"
```

#### 3. Test installation procedures
```bash
# Verify each documented procedure still works
cd /tmp && git clone https://github.com/crim-ca/weaver.git test-install
cd test-install
make install-all  # Test documented procedure
```

### Procedure 3: API Endpoint Changes

**When**: `weaver/wps_restapi/*.py` files are modified

**Steps**:

#### 1. Identify endpoint changes
```bash
# Check route definitions
git diff origin/master weaver/wps_restapi/api.py | grep "@.*route"

# Check new endpoints
git diff origin/master weaver/wps_restapi/ | grep -E "@.*\.(get|post|put|delete)"
```

#### 2. Map endpoints to skills
```markdown
GET /processes              → process-list
GET /processes/{id}         → process-describe
POST /processes             → process-deploy
DELETE /processes/{id}      → process-undeploy
POST /processes/{id}/execution → job-execute
GET /jobs/{id}              → job-status
GET /jobs/{id}/results      → job-results
GET /jobs/{id}/logs         → job-logs
etc.
```

#### 3. Update affected skills

For each affected skill:

```bash
# a. Update API Request section
# - Verify endpoint path
# - Check request parameters
# - Update request body examples

# b. Update Returns section
# - Check response schema changes
# - Update example responses
# - Note new fields

# c. Test endpoint
curl -X GET "${WEAVER_URL}/endpoint" | jq
```

### Procedure 4: Documentation Link Changes

**When**: `docs/source/*.rst` files are modified

**Steps**:

#### 1. Check for restructured docs
```bash
# Find moved or renamed files
git diff origin/master --name-status docs/source/

# Check for changed anchors
git diff origin/master docs/source/*.rst | grep -E "^\+.*\.\. _"
```

#### 2. Update documentation links in skills
```bash
# Find all documentation links
grep -r "https://pavics-weaver.readthedocs.io" .agents/skills/*/SKILL.md

# For each skill with doc links:
# - Verify link still works
# - Update path if file moved
# - Keep base URLs without anchors (anchors are auto-generated)
```

#### 3. Verify links
```bash
# Check each link returns 200
for skill in .agents/skills/*/SKILL.md; do
  echo "Checking $skill"
  grep -o "https://pavics-weaver[^)]*" "$skill" | while read url; do
    curl -s -o /dev/null -w "%{http_code} $url\n" "$url"
  done
done
```

### Procedure 5: Configuration Changes

**When**: `config/*.example` files are modified

**Steps**:

#### 1. Identify configuration changes
```bash
# Check example configs
git diff origin/master config/weaver.ini.example
git diff origin/master config/data_sources.yml.example
```

#### 2. Update weaver-install skill
```bash
# Update "Configuration" section
# - New configuration options
# - Changed defaults
# - Deprecated options

# Update "Key Configuration Options" examples
```

## Systematic Update Workflow

### Complete Update Process

```bash
# 1. Create update branch
git checkout -b update-skills-$(date +%Y%m%d)

# 2. Identify all changes since last skill update
git log --since="LAST_UPDATE_DATE" --name-only --pretty=format: | sort -u

# 3. Categorize changes
echo "Changed files:" > /tmp/skills-update-checklist.txt
echo "- CLI: $(git diff origin/master --name-only | grep cli.py | wc -l)"
echo "- Makefile: $(git diff origin/master --name-only | grep Makefile | wc -l)"
echo "- API: $(git diff origin/master --name-only | grep wps_restapi | wc -l)"
echo "- Docs: $(git diff origin/master --name-only | grep docs/ | wc -l)"

# 4. For each change category, follow procedure above

# 5. Verify all skills
for skill in .agents/skills/*/SKILL.md; do
  echo "Validating $skill"
  # Check YAML frontmatter
  # Check markdown formatting
  # Check code block syntax
  # Verify cross-references
done

# 6. Test examples
# Randomly test CLI examples from updated skills
# Verify curl commands work
# Check Python examples

# 7. Update skill count in README
vim .agents/README.md
# Update total count if new skills added

# 8. Commit changes
git add .agents/
git commit -m "Update Agent Skills to match code changes"

# 9. Create pull request
git push origin update-skills-$(date +%Y%m%d)
```

## Automated Detection Script

Save as `.agents/scripts/detect-skill-updates.sh`:

```bash
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
echo "Run: .agents/scripts/update-skills.sh to begin updates"
```

## Skill Quality Checklist

When updating skills, verify:

- [ ] **YAML frontmatter** is valid
- [ ] **Name** matches directory name
- [ ] **Description** is accurate (1-1024 chars)
- [ ] **CLI examples** use current syntax
- [ ] **API requests** use curl with `${WEAVER_URL}`
- [ ] **Python examples** use correct method signatures
- [ ] **Returns** section has completeness note
- [ ] **Job IDs** are UUIDs (not simple strings)
- [ ] **Documentation links** work (base URLs without anchors)
- [ ] **Cross-references** point to existing skills
- [ ] **Code blocks** have proper syntax highlighting
- [ ] **Examples** are tested and working

## Version-Specific Updates

### Major Version Updates (X.0.0)

```bash
# Comprehensive review required
# 1. Check all CLI command changes
# 2. Review API breaking changes
# 3. Update all version references
# 4. Review all examples for compatibility
# 5. Update configuration examples
# 6. Check for deprecated features
```

### Minor Version Updates (X.Y.0)

```bash
# Focus on new features
# 1. Check for new CLI commands → create skills
# 2. Check for new API endpoints → create skills
# 3. Update affected skills with new options
# 4. Add examples for new features
```

### Patch Version Updates (X.Y.Z)

```bash
# Minimal updates usually needed
# 1. Check CLI help text changes
# 2. Verify examples still work
# 3. Update error handling if changed
```

## Testing Updated Skills

### Manual Testing

> ⚠️ WARNING
> ️Unless a Weaver instance is running locally, the following tests will fail.
> Running an instance can be a timely process.
> Therefore, consider whether this is actually needed and there are no simpler workarounds.
> If required, ensure you have a test instance available before running these commands
> using [weaver-install](../weaver-install/) skill instructions.

```bash
# Test CLI examples
weaver info -u http://localhost:4001

# Test curl commands
export WEAVER_URL=http://localhost:4001
curl -X GET "${WEAVER_URL}/processes" | jq

# Test Python examples
python << EOF
from weaver.cli import WeaverClient
client = WeaverClient(url="http://localhost:4001")
print(client.capabilities())
EOF
```

### Automated Validation

```bash
# Validate YAML frontmatter
for skill in .agents/skills/*/SKILL.md; do
  python -c "
import yaml
with open('$skill') as f:
    content = f.read()
    parts = content.split('---')
    if len(parts) >= 3:
        yaml.safe_load(parts[1])
        print('✓ $skill')
    else:
        print('✗ $skill: Invalid frontmatter')
"
done

# Check for broken cross-references
for skill in .agents/skills/*/SKILL.md; do
  grep -o '\.\./[^/)]*)' "$skill" | while read ref; do
    target=$(echo "$ref" | sed 's/\.\.\/\([^/]*\).*/\1/')
    if [ ! -d ".agents/skills/$target" ]; then
      echo "✗ Broken reference in $skill: $ref"
    fi
  done
done
```

## Best Practices

1. **Update skills immediately** after code changes
2. **Test examples** before committing
3. **Use git diff** to identify all impacts
4. **Maintain consistency** across similar skills
5. **Document breaking changes** prominently
6. **Version control** skills with code
7. **Review related skills** when updating one
8. **Keep examples simple** and focused
9. **Verify links** after documentation restructure
10. **Update skill count** in README when adding/removing skills

## Related Skills

- [weaver-install](../weaver-install/) - Keep installation procedures current
- All skills - Any skill may need updates based on code changes

## Documentation

- [Agent Skills Specification](https://agentskills.io/specification)
- [Weaver Contributing Guide](https://pavics-weaver.readthedocs.io/en/latest/contributing.html)
- [Git Workflow](https://pavics-weaver.readthedocs.io/en/latest/contributing.html)

## Quick Reference

```bash
# Detect changes
git diff origin/master --name-only

# Check CLI changes
git diff origin/master weaver/cli.py | grep "def "

# Check API changes
git diff origin/master weaver/wps_restapi/

# Validate skills
.agents/scripts/detect-skill-updates.sh "1 week ago"

# Update and test
# 1. Update affected skills
# 2. Test examples
# 3. Verify links
# 4. Commit changes
```

Keep skills synchronized with code to maintain their value for users and AI agents!
