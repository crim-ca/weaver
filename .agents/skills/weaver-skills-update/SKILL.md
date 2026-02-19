---
name: weaver-skills-update
description: |
  Maintain and update Agent Skills documentation when Weaver codebase changes.
  Detect code modifications in weaver/cli.py, Makefile, docs/, and configuration files,
  then systematically update relevant skills to keep documentation synchronized.
  Use when contributing code changes or maintaining skills framework.
license: Apache-2.0
compatibility: Requires Python 3.10+, git, access to weaver repository.
metadata:
  category: setup-operations
  version: 1.0.0
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

Agent Skills must stay synchronized with the Weaver codebase. This skill provides systematic procedures to detect
changes and update relevant skills.

## Available Scripts

This skill provides three automation scripts to help maintain Agent Skills:

### 1. detect-skill-updates.sh

**Purpose**: Detect which files have changed and which skills need updating

**Usage**:

```bash
.agents/skills/weaver-skills-update/scripts/detect-skill-updates.sh "1 week ago"
```

**Output**: Reports CLI, Makefile, API, and documentation changes with recommendations

**See**: [Automated Detection Script](#automated-detection-script) section for details

### 2. validate-skills.sh

**Purpose**: Validate YAML frontmatter syntax and cross-references

**Usage**:

```bash
.agents/skills/weaver-skills-update/scripts/validate-skills.sh
```

**Output**: Checks YAML parsing and skill directory references

**See**: [Automated Validation](#automated-validation) section for details

### 3. check-frontmatter.py

**Purpose**: Verify YAML frontmatter uses proper multiline format

**Usage**:

```bash
python3 .agents/skills/weaver-skills-update/scripts/check-frontmatter.py
```

**Output**: Ensures all skills use `description: |` format

**See**: [YAML Frontmatter Format](#yaml-frontmatter-format) section for details

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
| ------------------------- | ------------------------- | --------------- |
| `weaver/cli.py`           | All CLI-referenced skills | **High**        |
| `weaver/wps_restapi/*.py` | API, job, process skills  | **Medium**      |
| `docs/source/*.rst`       | Documentation links       | **Medium**      |
| `config/*.example`        | Configuration examples    | **Medium**      |
| `weaver/processes/*.py`   | process-\* skills         | **Medium**      |
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

# 2. Identify changes since last update (optional - see what changed)
git log --since="LAST_UPDATE_DATE" --name-only --pretty=format: | sort -u

# 3. Detect changes and get recommendations
.agents/skills/weaver-skills-update/scripts/detect-skill-updates.sh "1 week ago"

# 4. For each change category reported, follow the corresponding procedure above
# - CLI changes → Procedure 1
# - Makefile changes → Procedure 2
# - API changes → Procedure 3
# - Documentation changes → Procedure 4
# - Configuration changes → Procedure 5

# 5. Verify all skills with validation scripts
.agents/skills/weaver-skills-update/scripts/validate-skills.sh
python3 .agents/skills/weaver-skills-update/scripts/check-frontmatter.py

# 6. Update skill count in README (if skills added/removed)
vim .agents/README.md

# 7. Commit changes
git add .agents/
git commit -m "Update Agent Skills to match code changes"

# 8. Create pull request
git push origin update-skills-$(date +%Y%m%d)
```

## Automated Detection Script

A script is provided to detect which files have changed and need skill updates. The script identifies changes but the
actual update procedures are documented in this SKILL.md file (see "Update Procedures" section above).

**Script**: [`scripts/detect-skill-updates.sh`](scripts/detect-skill-updates.sh)

**Usage**:

```bash
# Run from repository root
.agents/skills/weaver-skills-update/scripts/detect-skill-updates.sh

# Check changes since specific date
.agents/skills/weaver-skills-update/scripts/detect-skill-updates.sh "1 week ago"

# Check changes since last month (default)
.agents/skills/weaver-skills-update/scripts/detect-skill-updates.sh "1 month ago"
```

**What it does**:

- Analyzes git history for changes to key files
- Reports CLI changes (affects `job-*`, `process-*`, `provider-*` skills)
- Reports Makefile changes (affects weaver-install skill)
- Reports API changes (affects endpoint-related skills)
- Reports documentation changes (affects documentation links)
- Provides update recommendations based on detected changes

**Note**: This script only *detects* changes.
To perform the actual updates, follow the procedures documented in the
sections above (Procedure 1-5 under "Update Procedures").

## Skill Quality Checklist

When updating skills, verify:

- [ ] **YAML frontmatter** is valid
- [ ] **YAML description** uses multiline format with `description: |` (see YAML Frontmatter Format below)
- [ ] **Name** matches directory name
- [ ] **Description** is accurate (1-1024 chars)
- [ ] **Scripts** that require large set of commands are placed in dedicated `scripts/` and referenced by the skill
- [ ] **Returns** section has completeness note
- [ ] **Job IDs** are UUIDs (not simple strings)
- [ ] **Documentation links** work (base URLs without anchors)
- [ ] **Cross-references** point to existing skills
- [ ] **Steps** that are purely procedural without code use numbered lists instead of code blocks
- [ ] **Steps** that need code use code blocks only as needed, not for the entire step (avoid embedded comment list)
- [ ] **Code blocks** have proper syntax highlighting
- [ ] **Code blocks** do not repeat example keywords making their structure invalid
- [ ] **Python examples** use correct method signatures
- [ ] **CLI examples** use current syntax
- [ ] **API requests** use curl with `${WEAVER_URL}`
- [ ] **Examples** are tested and working if deemed necessary
- [ ] **Markdown** formatting is valid

### YAML Frontmatter Format

All skills must use proper YAML frontmatter with multiline descriptions to respect the limit of 120 characters per line.

**Required format**:

```yaml
---
name: skill-name
description: |
  Multi-line description that explains what the skill does.
  Use the pipe (|) symbol to enable multiline format.
  This prevents line wrapping issues and maintains readability.
license: Apache-2.0
compatibility: Requirements here
metadata:
  category: category-name
  version: "1.0.0"
  api_endpoint: GET /endpoint
  cli_command: weaver command
  author: CRIM
allowed-tools: tool1 tool2
---
```

**Key points**:

- **Always use `description: |`** for multiline format
- Indent description content with 2 spaces
- Keep description lines under 100 characters
- Ensure valid YAML syntax (no trailing commas, proper indentation)

**Validation script**: [`scripts/check-frontmatter.py`](scripts/check-frontmatter.py)

```bash
# Check YAML frontmatter format in all skills
python3 .agents/skills/weaver-skills-update/scripts/check-frontmatter.py
```

## Version-Specific Updates

### Major Version Updates (X.0.0)

Comprehensive review required:

1. Check all CLI command changes
2. Review API breaking changes
3. Update all version references
4. Review all examples for compatibility
5. Update configuration examples
6. Check for deprecated features

### Minor Version Updates (X.Y.0)

Focus on new features:

1. Check for new CLI commands → create skills
2. Check for new API endpoints → create skills
3. Update affected skills with new options
4. Add examples for new features

### Patch Version Updates (X.Y.Z)

Minimal updates usually needed:

1. Check CLI help text changes
2. Verify examples still work
3. Update error handling if changed

## Testing Updated Skills

### Manual Testing (optional)

> ⚠️ WARNING ️Unless a Weaver instance is running locally, the following tests will fail. Running an instance can be a
> timely process. Therefore, consider whether this is actually needed and there are no simpler workarounds. If required,
> ensure you have a test instance available before running these commands using [weaver-install](../weaver-install/)
> skill instructions.

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

A script is provided to validate YAML frontmatter and cross-references in all skills.

**Script**: [`scripts/validate-skills.sh`](scripts/validate-skills.sh)

**Usage**:

```bash
# Run from repository root
.agents/skills/weaver-skills-update/scripts/validate-skills.sh
```

**What it validates**:

- **YAML frontmatter**: Ensures all skills have valid YAML frontmatter between `---` markers
- **Cross-references**: Checks that all relative links to other skills (`../skill-name/`) point to existing skill directories

**Example output**:

```text
Validating Agent Skills...
==========================

Checking YAML frontmatter...
✓ .agents/skills/api-conformance/SKILL.md
✓ .agents/skills/api-info/SKILL.md
...

Checking cross-references...

==========================
✅ All validations passed
```

### Format Validation

Employ the `make check-md-only` target.
Similar command with `make fix-md-only` can be used to automatically formatting issues.
Remove the `-only` suffix if installation/updates of dependencies are needed.

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

# Validate skills (automated detection)
.agents/skills/weaver-skills-update/scripts/detect-skill-updates.sh "1 week ago"

# Update and test
# 1. Update affected skills
# 2. Test examples
# 3. Verify links
# 4. Commit changes
```

Keep skills synchronized with code to maintain their value for users and AI agents!
